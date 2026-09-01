from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable, Optional

INTEGER_COUNTERS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
    "active_ms",
    "requests",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def default_pricing_path() -> Path:
    return Path(__file__).with_name("pricing.json")


def resolve_rate(
    model: str, pricing: dict[str, Any]
) -> tuple[str, dict[str, float], str]:
    models = pricing["models"]
    lowered = model.lower()
    exact = next(
        (key for key in models if key != "default" and lowered == key.lower()), None
    )
    if exact:
        return exact, models[exact], "exact"

    aliases = {
        str(alias).lower(): target
        for alias, target in pricing.get("aliases", {}).items()
    }
    alias_target = aliases.get(lowered)
    if alias_target:
        if alias_target not in models:
            raise ValueError(
                f"Pricing alias for {model!r} references missing model key {alias_target!r}"
            )
        return alias_target, models[alias_target], "alias"

    matches = [
        key for key in models if key != "default" and lowered.startswith(key.lower())
    ]
    if matches:
        key = max(matches, key=len)
        return key, models[key], "prefix"
    return "default", models["default"], "default"


def normalize_input(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        return {
            "schemaVersion": 1,
            "generatedAt": utc_now(),
            "scope": {"repository": "unspecified", "sessionCount": None},
            "totals": {},
            "models": value,
        }
    if not isinstance(value, dict):
        raise ValueError("Snapshot must be a JSON object or an array of model rows")
    rows = value.get("models", value.get("per_model"))
    if not isinstance(rows, list):
        raise ValueError("Snapshot object must contain a models array")
    normalized = dict(value)
    normalized["models"] = rows
    normalized.setdefault("scope", {"repository": "unspecified", "sessionCount": None})
    normalized.setdefault("totals", {})
    return normalized


def aggregate_models(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for raw in rows:
        if not isinstance(raw, dict):
            raise ValueError("Every model row must be a JSON object")
        model = str(raw.get("model") or "unknown")
        row = merged.setdefault(
            model, {"model": model, **{counter: 0 for counter in INTEGER_COUNTERS}}
        )
        for counter in INTEGER_COUNTERS:
            value = int(raw.get(counter, 0) or 0)
            if value < 0:
                raise ValueError(f"{model}.{counter} must be non-negative")
            row[counter] += value
    return sorted(merged.values(), key=lambda row: row["input_tokens"], reverse=True)


def price_snapshot(snapshot_value: Any, pricing: dict[str, Any]) -> dict[str, Any]:
    snapshot = normalize_input(snapshot_value)
    priced_models = []
    fallbacks: list[str] = []
    prefix_rated: list[str] = []
    for row in aggregate_models(snapshot["models"]):
        model = row["model"]
        rate_key, rate, rate_match = resolve_rate(model, pricing)
        if rate_match == "default":
            fallbacks.append(model)
        elif rate_match == "prefix":
            prefix_rated.append(model)
        fresh = row["input_tokens"] - row["cache_read_tokens"] - row["cache_write_tokens"]
        if fresh < 0:
            raise ValueError(
                f"{model} cache buckets exceed total input tokens; inspect the telemetry export"
            )
        cost_parts = {
            "freshInput": fresh * rate["input"] / 1_000_000,
            "cacheRead": row["cache_read_tokens"] * rate["cacheRead"] / 1_000_000,
            "cacheWrite": row["cache_write_tokens"] * rate["cacheWrite"] / 1_000_000,
            "output": row["output_tokens"] * rate["output"] / 1_000_000,
        }
        priced_models.append(
            {
                **row,
                "fresh_input_tokens": fresh,
                "rate_key": rate_key,
                "rate_match": rate_match,
                "used_fallback_rate": rate_match == "default",
                "cost": {**cost_parts, "total": sum(cost_parts.values())},
            }
        )

    totals = {
        counter: sum(int(row[counter]) for row in priced_models)
        for counter in INTEGER_COUNTERS
    }
    totals["model_requests"] = totals.pop("requests")
    totals["ai_requests"] = int(
        snapshot.get("scope", {}).get("requestCount") or totals["model_requests"]
    )
    totals["fresh_input_tokens"] = sum(row["fresh_input_tokens"] for row in priced_models)
    totals["cost_usd"] = sum(row["cost"]["total"] for row in priced_models)
    source_totals = snapshot.get("totals", {})
    premium_credits = source_totals.get("premium_credits")
    if premium_credits is None:
        premium_credits = snapshot.get("premium_credits")
    totals["premium_credits"] = premium_credits

    return {
        "schemaVersion": 1,
        "generatedAt": utc_now(),
        "sourceGeneratedAt": snapshot.get("generatedAt"),
        "scope": snapshot["scope"],
        "evidence": {
            "tokens": "measured",
            "activeTime": "measured",
            "premiumCredits": "measured" if premium_credits is not None else "unavailable",
            "computeCost": "modeled",
        },
        "rateCard": {
            "version": pricing.get("version", "unversioned"),
            "currency": pricing.get("currency", "USD"),
            "fingerprint": hashlib.sha256(
                json.dumps(pricing, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
            "fallbackRatedModels": sorted(fallbacks),
            "prefixRatedModels": sorted(prefix_rated),
        },
        "totals": totals,
        "models": priced_models,
    }


def _state_projection(report: dict[str, Any]) -> dict[str, float]:
    totals = report["totals"]
    fields = (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "fresh_input_tokens",
        "reasoning_tokens",
        "active_ms",
        "ai_requests",
        "model_requests",
        "cost_usd",
    )
    return {field: float(totals.get(field, 0) or 0) for field in fields}


def _last_ledger_projection(path: Path) -> Optional[dict[str, float]]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    latest = rows[-1]
    return {
        key.removeprefix("cumulative_"): float(value)
        for key, value in latest.items()
        if key.startswith("cumulative_") and value not in (None, "")
    }


def _last_ledger_identity_hash(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None
    return rows[-1].get("identity_hash") or None


def _ledger_has_checkpoint(path: Path, checkpoint_id: str) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8", newline="") as handle:
        return any(
            row.get("checkpoint_id") == checkpoint_id for row in csv.DictReader(handle)
        )


def _checkpoint_identity(report: dict[str, Any]) -> dict[str, Any]:
    scope = report.get("scope", {})
    return {
        "repository": scope.get("repository"),
        "filter": scope.get("filter", {}),
        "rateCardVersion": report.get("rateCard", {}).get("version"),
        "rateCardFingerprint": report.get("rateCard", {}).get("fingerprint"),
    }


def _identity_hash(identity: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@contextmanager
def _file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _archive_ledger(ledger_dir: Path) -> list[Path]:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archived: list[Path] = []
    for name in ("aic-state.json", "aic-ledger.csv", "aic-report.json"):
        source = ledger_dir / name
        if source.exists():
            destination = ledger_dir / f"{source.stem}.{timestamp}{source.suffix}"
            shutil.copy2(source, destination)
            archived.append(destination)
    return archived


def append_checkpoint(
    report: dict[str, Any],
    ledger_dir: Path,
    label: str,
    reset: bool = False,
    allow_scope_change: bool = False,
) -> dict[str, Any]:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    with _file_lock(ledger_dir / ".aic.lock"):
        _recover_pending_locked(ledger_dir)
        return _append_checkpoint_locked(
            report, ledger_dir, label, reset, allow_scope_change
        )


def recover_checkpoint(ledger_dir: Path) -> bool:
    ledger_dir.mkdir(parents=True, exist_ok=True)
    with _file_lock(ledger_dir / ".aic.lock"):
        return _recover_pending_locked(ledger_dir)


def _recover_pending_locked(ledger_dir: Path) -> bool:
    pending_path = ledger_dir / ".aic-pending.json"
    if not pending_path.exists():
        return False
    pending = read_json(pending_path)
    checkpoint_id = pending.get("checkpointId")
    if checkpoint_id and _ledger_has_checkpoint(
        ledger_dir / "aic-ledger.csv", checkpoint_id
    ):
        write_json(ledger_dir / "aic-state.json", pending["state"])
        write_json(ledger_dir / "aic-report.json", pending["report"])
    pending_path.unlink(missing_ok=True)
    return True


def _append_checkpoint_locked(
    report: dict[str, Any],
    ledger_dir: Path,
    label: str,
    reset: bool,
    allow_scope_change: bool,
) -> dict[str, Any]:
    state_path = ledger_dir / "aic-state.json"
    ledger_path = ledger_dir / "aic-ledger.csv"
    archived: list[Path] = []
    new_baseline = reset
    if reset:
        archived = _archive_ledger(ledger_dir)

    previous = (
        None
        if new_baseline
        else read_json(state_path)
        if state_path.exists()
        else None
    )
    current_projection = _state_projection(report)
    identity = _checkpoint_identity(report)
    identity_hash = _identity_hash(identity)
    previous_identity_hash = (
        None if new_baseline else _last_ledger_identity_hash(ledger_path)
    )
    if previous_identity_hash is None and previous:
        previous_identity_hash = previous.get("identityHash")
    identity_changed = bool(
        previous_identity_hash and previous_identity_hash != identity_hash
    )
    if identity_changed:
        if not allow_scope_change:
            raise ValueError(
                "Checkpoint scope or rate card changed. Use --allow-scope-change "
                "or --reset to archive the old ledger and start a new baseline."
            )
        archived = _archive_ledger(ledger_dir)
        new_baseline = True
        previous = None

    previous_projection = (
        None if new_baseline else _last_ledger_projection(ledger_path)
    )
    if previous_projection is None:
        previous_projection = previous.get("projection", {}) if previous else {}
    delta = {
        key: value - float(previous_projection.get(key, 0) or 0)
        for key, value in current_projection.items()
    }
    regressions = [key for key, value in delta.items() if value < -1e-9]
    if regressions:
        if not allow_scope_change:
            raise ValueError(
                "Cumulative snapshot regressed for: "
                + ", ".join(regressions)
                + ". Use --allow-scope-change or --reset to archive the old ledger and start a new baseline."
            )
        archived = _archive_ledger(ledger_dir)
        new_baseline = True
        previous = None
        previous_projection = {}
        delta = dict(current_projection)

    checkpoint = {
        "id": uuid.uuid4().hex,
        "timestamp": utc_now(),
        "label": label,
        "cumulative": current_projection,
        "delta": delta,
        "scopeChange": bool(archived),
        "archivedFiles": [str(path) for path in archived],
    }
    is_new = new_baseline or not ledger_path.exists()
    existing = (
        ""
        if new_baseline
        else ledger_path.read_text(encoding="utf-8")
        if ledger_path.exists()
        else ""
    )
    state = {
        "updatedAt": checkpoint["timestamp"],
        "label": label,
        "checkpointId": checkpoint["id"],
        "scope": report["scope"],
        "identity": identity,
        "identityHash": identity_hash,
        "projection": current_projection,
    }
    pending_path = ledger_dir / ".aic-pending.json"
    write_json(
        pending_path,
        {"checkpointId": checkpoint["id"], "state": state, "report": report},
    )
    descriptor, temp_name = tempfile.mkstemp(
        prefix=".aic-ledger.", suffix=".tmp", dir=ledger_dir
    )
    try:
        with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
            if existing:
                handle.write(existing)
                if not existing.endswith("\n"):
                    handle.write("\n")
            writer = csv.writer(handle)
            headers = [
                "checkpoint_id",
                "timestamp",
                "label",
                "scope_change",
                "identity_hash",
            ] + [
                f"cumulative_{key}" for key in current_projection
            ] + [f"delta_{key}" for key in current_projection]
            if is_new:
                writer.writerow(headers)
            writer.writerow(
                [
                    checkpoint["id"],
                    checkpoint["timestamp"],
                    label,
                    str(bool(archived)).lower(),
                    identity_hash,
                ]
                + [current_projection[key] for key in current_projection]
                + [delta[key] for key in current_projection]
            )
        os.replace(temp_name, ledger_path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise
    write_json(state_path, state)
    write_json(ledger_dir / "aic-report.json", report)
    pending_path.unlink(missing_ok=True)
    return checkpoint


def human_duration(milliseconds: float) -> str:
    seconds = int(round(milliseconds / 1000))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def money(value: float) -> str:
    return f"${value:,.4f}" if abs(value) < 1 else f"${value:,.2f}"


def console_summary(
    report: dict[str, Any], checkpoint: Optional[dict[str, Any]] = None
) -> str:
    totals = report["totals"]
    lines = [
        f"AIC report: {report['scope'].get('repository', 'unspecified')}",
        f"Modeled compute: {money(totals['cost_usd'])}",
        f"Input: {int(totals['input_tokens']):,} "
        f"(fresh {int(totals['fresh_input_tokens']):,}, "
        f"cache-read {int(totals['cache_read_tokens']):,}, "
        f"cache-write {int(totals['cache_write_tokens']):,})",
        f"Output: {int(totals['output_tokens']):,}",
        f"AI requests: {int(totals['ai_requests']):,}",
        f"Active generation: {human_duration(totals['active_ms'])}",
        "Premium credits: "
        + (
            f"{float(totals['premium_credits']):,.2f}"
            if totals.get("premium_credits") is not None
            else "unavailable"
        ),
    ]
    if report["rateCard"]["fallbackRatedModels"]:
        lines.append(
            "Fallback-priced models: "
            + ", ".join(report["rateCard"]["fallbackRatedModels"])
        )
    if report["rateCard"].get("prefixRatedModels"):
        lines.append(
            "Prefix-priced models (verify mapping): "
            + ", ".join(report["rateCard"]["prefixRatedModels"])
        )
    if checkpoint:
        lines.append(
            f"Since last checkpoint: {money(checkpoint['delta']['cost_usd'])}, "
            f"{int(checkpoint['delta']['input_tokens']):,} input tokens"
        )
        if checkpoint["archivedFiles"]:
            lines.append(
                "Archived prior ledger: " + ", ".join(checkpoint["archivedFiles"])
            )
    return os.linesep.join(lines)

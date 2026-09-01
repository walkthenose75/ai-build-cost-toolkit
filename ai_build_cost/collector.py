from __future__ import annotations

import datetime as dt
import hashlib
import os
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, Optional

from .core import utc_now


def default_store_path() -> Path:
    return Path.home() / ".copilot" / "session-store.db"


def _connect_readonly(store: Path) -> sqlite3.Connection:
    """Open the Copilot store read-only so collection never mutates it."""
    return sqlite3.connect(f"{store.as_uri()}?mode=ro", uri=True)


def _normalized(path: Any) -> str:
    value = str(Path(path).resolve()).rstrip("\\/")
    return value.casefold() if os.name == "nt" else value


def _is_same_or_child(candidate: Any, root: Path) -> bool:
    candidate_key = _normalized(candidate)
    root_key = _normalized(root)
    if candidate_key == root_key:
        return True
    if root.parent == root:
        return False
    return candidate_key.startswith(root_key + os.sep)


def _normalized_repository(value: Optional[str]) -> str:
    if not value:
        return ""
    cleaned = value.strip().removesuffix(".git").replace("\\", "/")
    if cleaned.startswith("git@github.com:"):
        cleaned = cleaned.split(":", 1)[1]
    if "github.com/" in cleaned:
        cleaned = cleaned.split("github.com/", 1)[1]
    return cleaned.casefold()


def _normalize_since(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    candidate = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(candidate)
    except ValueError as error:
        raise ValueError(
            f"Invalid --since timestamp {value!r}; use ISO 8601, for example 2026-08-31T00:00:00Z"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _repository_label(root: Path) -> str:
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        cleaned = remote.removesuffix(".git").replace("\\", "/")
        if cleaned.startswith("git@github.com:"):
            return cleaned.split(":", 1)[1]
        marker = "github.com/"
        if marker in cleaned:
            return cleaned.split(marker, 1)[1]
    except (OSError, subprocess.CalledProcessError):
        pass
    return root.name


def _validate_schema(connection: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    required = {"sessions", "assistant_usage_events"}
    missing = required - tables
    if missing:
        raise ValueError(
            "Unsupported Copilot session store; missing table(s): " + ", ".join(sorted(missing))
        )
    usage_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(assistant_usage_events)")
    }
    required_columns = {
        "session_id",
        "agent_id",
        "turn_index",
        "model",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "reasoning_tokens",
        "request_multiplier",
        "duration_ms",
        "created_at",
    }
    missing_columns = required_columns - usage_columns
    if missing_columns:
        raise ValueError(
            "Unsupported assistant_usage_events schema; missing column(s): "
            + ", ".join(sorted(missing_columns))
        )


def collect_project(
    repository_root: Path,
    store_path: Optional[Path] = None,
    since: Optional[str] = None,
    session_id: Optional[str] = None,
    match_mode: str = "cwd",
) -> dict[str, Any]:
    root = repository_root.resolve()
    store = (store_path or default_store_path()).expanduser().resolve()
    if not store.exists():
        raise FileNotFoundError(f"Copilot session store not found: {store}")

    connection = _connect_readonly(store)
    connection.row_factory = sqlite3.Row
    try:
        _validate_schema(connection)
        sessions = connection.execute(
            "SELECT id, cwd, repository, created_at, updated_at FROM sessions"
        ).fetchall()
        if match_mode not in {"cwd", "repository", "both"}:
            raise ValueError("--match must be cwd, repository, or both")
        repository_label = _repository_label(root)
        repository_key = _normalized_repository(repository_label)
        matched = []
        for row in sessions:
            if session_id and row["id"] != session_id:
                continue
            cwd = row["cwd"]
            cwd_match = bool(cwd and _is_same_or_child(cwd, root))
            repository_match = bool(
                repository_key
                and _normalized_repository(row["repository"]) == repository_key
            )
            selected = (
                cwd_match
                if match_mode == "cwd"
                else repository_match
                if match_mode == "repository"
                else cwd_match or repository_match
            )
            if session_id or selected:
                matched.append(row)
        if not matched:
            raise ValueError(
                f"No Copilot CLI sessions matched {root} (match mode: {match_mode}). "
                "Retry with --match both, confirm --repo points at the directory you "
                "ran Copilot CLI from, and run 'aic doctor' to confirm telemetry exists. "
                "VS Code Copilot Chat sessions are not recorded in this store."
            )

        ids = [row["id"] for row in matched]
        placeholders = ",".join("?" for _ in ids)
        params: list[Any] = list(ids)
        date_filter = ""
        normalized_since = _normalize_since(since)
        if normalized_since:
            date_filter = " AND datetime(created_at) >= datetime(?)"
            params.append(normalized_since)
        events = connection.execute(
            f"""
            SELECT session_id, COALESCE(agent_id, '') AS agent_id, turn_index, model,
                   COALESCE(input_tokens, 0) AS input_tokens,
                   COALESCE(output_tokens, 0) AS output_tokens,
                   COALESCE(cache_read_tokens, 0) AS cache_read_tokens,
                   COALESCE(cache_write_tokens, 0) AS cache_write_tokens,
                   COALESCE(reasoning_tokens, 0) AS reasoning_tokens,
                   COALESCE(duration_ms, 0) AS duration_ms,
                   request_multiplier, created_at
            FROM assistant_usage_events
            WHERE session_id IN ({placeholders}){date_filter}
            """,
            params,
        ).fetchall()
        if not events:
            raise ValueError(
                f"{len(matched)} session(s) matched {root} but none contain usage "
                "telemetry. The Copilot CLI store may have rotated, usage may predate "
                "telemetry, or these were VS Code Copilot Chat sessions (not recorded "
                "here). Try --match both or a different --repo, and run 'aic doctor'."
            )

        by_model: dict[str, dict[str, Any]] = {}
        credit_by_turn: dict[tuple[str, str, int], float] = {}
        all_turns: set[tuple[str, str, int]] = set()
        requests_by_model: dict[str, set[tuple[str, str, int]]] = {}
        timestamps = []
        for event in events:
            model = event["model"]
            row = by_model.setdefault(
                model,
                {
                    "model": model,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_read_tokens": 0,
                    "cache_write_tokens": 0,
                    "reasoning_tokens": 0,
                    "active_ms": 0,
                    "requests": 0,
                },
            )
            for field in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_write_tokens",
                "reasoning_tokens",
            ):
                row[field] += event[field]
            row["active_ms"] += event["duration_ms"]
            turn = (event["session_id"], event["agent_id"], event["turn_index"])
            all_turns.add(turn)
            requests_by_model.setdefault(model, set()).add(turn)
            multiplier = event["request_multiplier"]
            if multiplier is not None:
                credit_by_turn[turn] = max(credit_by_turn.get(turn, 0), float(multiplier))
            if event["created_at"]:
                timestamps.append(event["created_at"])

        for model, turns in requests_by_model.items():
            by_model[model]["requests"] = len(turns)

        first = min(timestamps) if timestamps else None
        last = max(timestamps) if timestamps else None
        contributing_sessions = {row["session_id"] for row in events}
        calendar_days = None
        if first and last:
            try:
                first_date = dt.datetime.fromisoformat(first.replace("Z", "+00:00"))
                last_date = dt.datetime.fromisoformat(last.replace("Z", "+00:00"))
                calendar_days = max(1, (last_date.date() - first_date.date()).days + 1)
            except ValueError:
                pass

        models = sorted(by_model.values(), key=lambda item: item["input_tokens"], reverse=True)
        return {
            "schemaVersion": 1,
            "generatedAt": utc_now(),
            "scope": {
                "repository": repository_label,
                "sessionCount": len(contributing_sessions),
                "requestCount": len(
                    all_turns
                ),
                "creditKnownRequestCount": len(credit_by_turn),
                "firstActivity": first,
                "lastActivity": last,
                "calendarDays": calendar_days,
                "filter": {
                    "since": normalized_since,
                    "match": match_mode,
                    "sessionScope": "single" if session_id else "project",
                    "sessionFingerprint": (
                        hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:12]
                        if session_id
                        else None
                    ),
                },
            },
            "totals": {
                "premium_credits": (
                    sum(credit_by_turn.values())
                    if all_turns and len(credit_by_turn) == len(all_turns)
                    else None
                ),
            },
            "models": models,
        }
    finally:
        connection.close()


def doctor(store_path: Optional[Path] = None) -> dict[str, Any]:
    store = (store_path or default_store_path()).expanduser().resolve()
    result: dict[str, Any] = {
        "store": str(store),
        "exists": store.exists(),
        "supported": False,
        "sessionCount": 0,
        "usageEventCount": 0,
    }
    if not store.exists():
        return result
    connection = _connect_readonly(store)
    try:
        _validate_schema(connection)
        result["supported"] = True
        result["sessionCount"] = connection.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        result["usageEventCount"] = connection.execute(
            "SELECT COUNT(*) FROM assistant_usage_events"
        ).fetchone()[0]
        return result
    finally:
        connection.close()

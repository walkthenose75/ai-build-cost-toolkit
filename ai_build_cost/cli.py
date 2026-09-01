from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Optional

from .collector import collect_project, default_store_path, doctor
from .core import (
    append_checkpoint,
    console_summary,
    default_pricing_path,
    price_snapshot,
    read_json,
    recover_checkpoint,
    write_json,
)
from .dashboard import render_dashboard


def _path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def _load_pricing(path: Path) -> dict[str, Any]:
    value = read_json(path)
    if "models" not in value or "default" not in value["models"]:
        raise ValueError("Pricing file must contain models.default")
    return value


def _typescript_data_module(
    report: dict[str, Any], baseline: Optional[dict[str, Any]]
) -> str:
    current_json = json.dumps(report, indent=2, ensure_ascii=True)
    baseline_value = (
        json.dumps(baseline, indent=2, ensure_ascii=True)
        if baseline is not None
        else "undefined"
    )
    return (
        "import type { AicReport } from './AiBuildCostPage'\n\n"
        f"export const AIC_CURRENT_REPORT: AicReport = {current_json}\n\n"
        "export const AIC_BASELINE_REPORT: AicReport | undefined = "
        f"{baseline_value}\n"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aic",
        description="Measure Copilot CLI consumption and publish an AI build-cost report.",
    )
    parser.add_argument("--version", action="version", version="aic 1.0.0")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_parser = sub.add_parser("doctor", help="Verify the local Copilot telemetry store")
    doctor_parser.add_argument("--store", type=_path, default=default_store_path())

    init = sub.add_parser(
        "init",
        help="Set up AI Build Cost in the current project (creates .aic/pricing.json)",
    )
    init.add_argument("--dir", type=_path, default=_path(".aic"))
    init.add_argument("--force", action="store_true")

    collect = sub.add_parser("collect", help="Collect cumulative project telemetry")
    collect.add_argument("--repo", type=_path, default=Path.cwd())
    collect.add_argument("--store", type=_path, default=default_store_path())
    collect.add_argument("--since", help="ISO timestamp lower bound")
    collect.add_argument("--session-id", help="Collect exactly one Copilot CLI session")
    collect.add_argument(
        "--match",
        choices=["cwd", "repository", "both"],
        default="cwd",
        help="How project sessions are matched (default: cwd)",
    )
    collect.add_argument("-o", "--output", type=_path, required=True)

    calculate = sub.add_parser("calculate", help="Apply cache-aware pricing to a snapshot")
    calculate.add_argument("-i", "--input", type=_path, required=True)
    calculate.add_argument("--pricing", type=_path, default=default_pricing_path())
    calculate.add_argument("-o", "--output", type=_path, required=True)

    checkpoint = sub.add_parser(
        "checkpoint",
        help="Collect, calculate, append a ledger row, and save the current report",
    )
    checkpoint.add_argument("--repo", type=_path, default=Path.cwd())
    checkpoint.add_argument("--store", type=_path, default=default_store_path())
    checkpoint.add_argument("--since", help="ISO timestamp lower bound")
    checkpoint.add_argument("--session-id", help="Collect exactly one Copilot CLI session")
    checkpoint.add_argument(
        "--match",
        choices=["cwd", "repository", "both"],
        default="cwd",
        help="How project sessions are matched (default: cwd)",
    )
    checkpoint.add_argument("--pricing", type=_path, default=None)
    checkpoint.add_argument("--dir", type=_path, default=_path(".aic"))
    checkpoint.add_argument("--label", default="checkpoint")
    checkpoint.add_argument("--reset", action="store_true")
    checkpoint.add_argument(
        "--allow-scope-change",
        action="store_true",
        help="Archive the prior ledger and start a new baseline if counters regress",
    )

    dashboard = sub.add_parser("dashboard", help="Generate a self-contained HTML report")
    dashboard.add_argument(
        "--report", type=_path, default=_path(".aic/aic-report.json")
    )
    dashboard.add_argument("--baseline", type=_path)
    dashboard.add_argument("--ledger", type=_path)
    dashboard.add_argument("--title", default="AI Build Cost")
    dashboard.add_argument(
        "-o", "--output", type=_path, default=_path("reports/ai-build-cost.html")
    )

    validate = sub.add_parser("validate", help="Validate a priced report")
    validate.add_argument("--report", type=_path, required=True)

    install_skill = sub.add_parser(
        "install-skill", help="Install the bundled aic-tracker Copilot skill"
    )
    install_skill.add_argument(
        "--destination",
        type=_path,
        default=_path(Path.home() / ".copilot" / "skills" / "aic-tracker"),
    )
    install_skill.add_argument("--force", action="store_true")

    install_code_app = sub.add_parser(
        "install-code-app-page",
        help="Install a typed AI Build Cost page into a Power Apps Code App",
    )
    install_code_app.add_argument("--report", type=_path, required=True)
    install_code_app.add_argument("--baseline", type=_path)
    install_code_app.add_argument("--target", type=_path, required=True)
    install_code_app.add_argument("--force", action="store_true")
    return parser


def _validate_report(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if report.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    if not isinstance(report.get("models"), list):
        errors.append("models must be an array")
    totals = report.get("totals", {})
    for field in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "fresh_input_tokens",
        "active_ms",
        "ai_requests",
        "model_requests",
        "cost_usd",
    ):
        value = totals.get(field)
        if not isinstance(value, (int, float)) or value < 0:
            errors.append(f"totals.{field} must be a non-negative number")
    if report.get("rateCard", {}).get("fallbackRatedModels") is None:
        errors.append("rateCard.fallbackRatedModels must be disclosed")
    if report.get("rateCard", {}).get("prefixRatedModels") is None:
        errors.append("rateCard.prefixRatedModels must be disclosed")
    if not report.get("rateCard", {}).get("fingerprint"):
        errors.append("rateCard.fingerprint is required")
    models = report.get("models", [])
    if isinstance(models, list):
        counter_fields = (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "fresh_input_tokens",
            "reasoning_tokens",
            "active_ms",
        )
        for index, model in enumerate(models):
            if not isinstance(model, dict):
                errors.append(f"models[{index}] must be an object")
                continue
            if model.get("rate_match") not in {"exact", "alias", "prefix", "default"}:
                errors.append(f"models[{index}].rate_match is invalid")
            if not isinstance(model.get("cost", {}).get("total"), (int, float)):
                errors.append(f"models[{index}].cost.total must be numeric")
        for field in counter_fields:
            expected = sum(
                model.get(field, 0) for model in models if isinstance(model, dict)
            )
            if totals.get(field) != expected:
                errors.append(f"totals.{field} does not equal the per-model sum")
        expected_cost = sum(
            model.get("cost", {}).get("total", 0)
            for model in models
            if isinstance(model, dict)
        )
        if abs(float(totals.get("cost_usd", 0) or 0) - expected_cost) > 0.000001:
            errors.append("totals.cost_usd does not equal the per-model sum")
        expected_model_requests = sum(
            model.get("requests", 0)
            for model in models
            if isinstance(model, dict)
        )
        if totals.get("model_requests") != expected_model_requests:
            errors.append("totals.model_requests does not equal the per-model sum")
        if float(totals.get("ai_requests", 0) or 0) > float(
            totals.get("model_requests", 0) or 0
        ):
            errors.append("totals.ai_requests cannot exceed totals.model_requests")
    premium_credits = totals.get("premium_credits")
    if premium_credits is not None and (
        not isinstance(premium_credits, (int, float)) or premium_credits < 0
    ):
        errors.append("totals.premium_credits must be null or a non-negative number")
    return errors


def _baseline_compatibility_errors(
    baseline: dict[str, Any], current: dict[str, Any]
) -> list[str]:
    errors: list[str] = []
    if baseline["scope"].get("repository") != current["scope"].get("repository"):
        errors.append("reports belong to different repositories")
    if baseline["scope"].get("filter", {}) != current["scope"].get("filter", {}):
        errors.append("reports use different collection filters")
    if baseline["rateCard"].get("fingerprint") != current["rateCard"].get(
        "fingerprint"
    ) or baseline["rateCard"].get("version") != current["rateCard"].get("version"):
        errors.append("reports use different rate cards")

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
    for field in fields:
        if float(baseline["totals"].get(field, 0) or 0) > float(
            current["totals"].get(field, 0) or 0
        ) + 0.000001:
            errors.append(f"baseline totals.{field} exceeds current")

    current_models = {model["model"]: model for model in current["models"]}
    for baseline_model in baseline["models"]:
        model_name = baseline_model["model"]
        current_model = current_models.get(model_name)
        if current_model is None:
            errors.append(f"baseline model {model_name} is missing from current")
            continue
        for field in (
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_write_tokens",
            "fresh_input_tokens",
            "reasoning_tokens",
            "active_ms",
            "requests",
        ):
            if float(baseline_model.get(field, 0) or 0) > float(
                current_model.get(field, 0) or 0
            ):
                errors.append(f"baseline {model_name}.{field} exceeds current")
        if float(baseline_model.get("cost", {}).get("total", 0) or 0) > float(
            current_model.get("cost", {}).get("total", 0) or 0
        ) + 0.000001:
            errors.append(f"baseline {model_name}.cost.total exceeds current")
    return errors


def run(args: argparse.Namespace) -> int:
    if args.command == "doctor":
        result = doctor(args.store)
        print(json.dumps(result, indent=2))
        return 0 if result["supported"] else 1

    if args.command == "init":
        args.dir.mkdir(parents=True, exist_ok=True)
        pricing_path = args.dir / "pricing.json"
        if pricing_path.exists() and not args.force:
            raise ValueError(
                f"{pricing_path} already exists; re-run with --force to overwrite it"
            )
        shutil.copy2(default_pricing_path(), pricing_path)
        gitignore = args.dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text(
                "# AI Build Cost: ignore mutable local state.\n"
                "# Keep pricing.json, aic-ledger.csv, and reviewed reports.\n"
                "aic-state.json\n"
                ".aic-pending.json\n"
                ".aic.lock\n"
                "*.snapshot.json\n",
                encoding="utf-8",
            )
        print(f"Initialized AI Build Cost in {args.dir}")
        print(f"1. Verify and date the example rate card: {pricing_path}")
        print('2. Measure this project:   aic checkpoint --label "initial build"')
        print("3. Publish the dashboard:  aic dashboard")
        return 0

    if args.command == "collect":
        snapshot = collect_project(
            args.repo, args.store, args.since, args.session_id, args.match
        )
        write_json(args.output, snapshot)
        print(f"Snapshot written to {args.output}")
        return 0

    if args.command == "calculate":
        report = price_snapshot(read_json(args.input), _load_pricing(args.pricing))
        write_json(args.output, report)
        print(console_summary(report))
        print(f"Report written to {args.output}")
        return 0

    if args.command == "checkpoint":
        snapshot = collect_project(
            args.repo, args.store, args.since, args.session_id, args.match
        )
        project_pricing = args.dir / "pricing.json"
        pricing_path = args.pricing or (
            project_pricing if project_pricing.exists() else default_pricing_path()
        )
        report = price_snapshot(snapshot, _load_pricing(pricing_path))
        checkpoint = append_checkpoint(
            report,
            args.dir,
            args.label,
            args.reset,
            args.allow_scope_change,
        )
        report_path = args.dir / "aic-report.json"
        print(console_summary(report, checkpoint))
        print(f"Report written to {report_path}")
        return 0

    if args.command == "dashboard":
        if (
            args.report.name == "aic-report.json"
            and (args.report.parent / ".aic-pending.json").exists()
        ):
            recover_checkpoint(args.report.parent)
        if not args.report.exists():
            raise ValueError(
                f"No report found at {args.report}. Run 'aic checkpoint' first in "
                "this project, or pass --report <path>."
            )
        report = read_json(args.report)
        baseline = read_json(args.baseline) if args.baseline else None
        ledger = args.ledger
        if ledger is None:
            candidate = args.report.parent / "aic-ledger.csv"
            if candidate.exists():
                ledger = candidate
        report_errors = _validate_report(report)
        if report_errors:
            raise ValueError("Current report is invalid: " + "; ".join(report_errors))
        if baseline:
            baseline_errors = _validate_report(baseline)
            if baseline_errors:
                raise ValueError(
                    "Baseline report is invalid: " + "; ".join(baseline_errors)
                )
            compatibility_errors = _baseline_compatibility_errors(baseline, report)
            if compatibility_errors:
                raise ValueError(
                    "Baseline is not compatible with the current report: "
                    + "; ".join(compatibility_errors)
                )
        render_dashboard(report, args.output, baseline, ledger, args.title)
        print(f"Dashboard written to {args.output}")
        return 0

    if args.command == "validate":
        if (
            args.report.name == "aic-report.json"
            and (args.report.parent / ".aic-pending.json").exists()
        ):
            recover_checkpoint(args.report.parent)
        errors = _validate_report(read_json(args.report))
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print(f"Valid AIC report: {args.report}")
        return 0

    if args.command == "install-skill":
        source = Path(__file__).with_name("skill") / "SKILL.md"
        if args.destination.exists() and not args.force:
            raise ValueError(
                f"Skill already exists at {args.destination}; use --force to update it"
            )
        args.destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, args.destination / "SKILL.md")
        print(f"Installed aic-tracker skill to {args.destination}")
        return 0

    if args.command == "install-code-app-page":
        report = read_json(args.report)
        baseline = read_json(args.baseline) if args.baseline else None
        report_errors = _validate_report(report)
        if report_errors:
            raise ValueError("Current report is invalid: " + "; ".join(report_errors))
        if baseline:
            baseline_errors = _validate_report(baseline)
            if baseline_errors:
                raise ValueError(
                    "Baseline report is invalid: " + "; ".join(baseline_errors)
                )
            compatibility_errors = _baseline_compatibility_errors(baseline, report)
            if compatibility_errors:
                raise ValueError(
                    "Baseline is not compatible with the current report: "
                    + "; ".join(compatibility_errors)
                )

        source = Path(__file__).with_name("templates") / "power_apps_code_app"
        managed_names = {
            "AiBuildCostPage.tsx",
            "AiBuildCostPage.css",
            "index.ts",
            "README.md",
            "aic-data.ts",
        }
        existing = [name for name in managed_names if (args.target / name).exists()]
        if existing and not args.force:
            raise ValueError(
                f"Code App integration already exists at {args.target}; "
                "use --force to update it"
            )

        args.target.mkdir(parents=True, exist_ok=True)
        for name in managed_names - {"aic-data.ts"}:
            shutil.copy2(source / name, args.target / name)
        (args.target / "aic-data.ts").write_text(
            _typescript_data_module(report, baseline),
            encoding="utf-8",
        )
        print(f"Installed Power Apps Code App page to {args.target}")
        return 0
    raise ValueError(f"Unsupported command: {args.command}")


def main() -> int:
    try:
        return run(build_parser().parse_args())
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

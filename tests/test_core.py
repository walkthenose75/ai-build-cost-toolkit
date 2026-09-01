import json
import multiprocessing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import ai_build_cost.core as core
from ai_build_cost.core import (
    append_checkpoint,
    price_snapshot,
    read_json,
    recover_checkpoint,
)
from ai_build_cost.dashboard import render_dashboard


PRICING = {
    "version": "test-v1",
    "currency": "USD",
    "models": {
        "model-pro": {
            "input": 10,
            "output": 20,
            "cacheRead": 1,
            "cacheWrite": 12,
        },
        "default": {
            "input": 2,
            "output": 4,
            "cacheRead": 0.2,
            "cacheWrite": 2,
        },
    },
}


def snapshot(input_tokens=1000):
    return {
        "schemaVersion": 1,
        "generatedAt": "2026-08-31T20:00:00Z",
        "scope": {"repository": "owner/repo", "sessionCount": 1},
        "totals": {"premium_credits": 3.5},
        "models": [
            {
                "model": "model-pro-v2",
                "input_tokens": input_tokens,
                "output_tokens": 100,
                "cache_read_tokens": 700,
                "cache_write_tokens": 200,
                "reasoning_tokens": 10,
                "active_ms": 5000,
                "requests": 2,
            }
        ],
    }


def append_worker(report, directory, label):
    report["scope"]["marker"] = label
    append_checkpoint(report, Path(directory), label)


class CoreTests(unittest.TestCase):
    def test_prices_each_cache_bucket(self):
        report = price_snapshot(snapshot(), PRICING)
        model = report["models"][0]
        self.assertEqual(model["fresh_input_tokens"], 100)
        self.assertAlmostEqual(model["cost"]["freshInput"], 0.001)
        self.assertAlmostEqual(model["cost"]["cacheRead"], 0.0007)
        self.assertAlmostEqual(model["cost"]["cacheWrite"], 0.0024)
        self.assertAlmostEqual(model["cost"]["output"], 0.002)
        self.assertAlmostEqual(report["totals"]["cost_usd"], 0.0061)
        self.assertEqual(report["totals"]["premium_credits"], 3.5)
        self.assertEqual(report["totals"]["ai_requests"], 2)
        self.assertEqual(report["totals"]["model_requests"], 2)

    def test_aggregates_duplicate_model_rows(self):
        value = snapshot()
        value["models"].append(dict(value["models"][0]))
        report = price_snapshot(value, PRICING)
        self.assertEqual(len(report["models"]), 1)
        self.assertEqual(report["totals"]["input_tokens"], 2000)

    def test_discloses_fallback_models(self):
        value = snapshot()
        value["models"][0]["model"] = "unknown-model"
        report = price_snapshot(value, PRICING)
        self.assertEqual(report["rateCard"]["fallbackRatedModels"], ["unknown-model"])
        self.assertTrue(report["models"][0]["used_fallback_rate"])

    def test_marks_coarse_prefix_rates_for_review(self):
        value = snapshot()
        value["models"][0]["model"] = "model-pro-special"
        report = price_snapshot(value, PRICING)
        self.assertEqual(report["rateCard"]["prefixRatedModels"], ["model-pro-special"])
        self.assertEqual(report["models"][0]["rate_match"], "prefix")

    def test_ledger_reports_delta_and_rejects_regression(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            first = price_snapshot(snapshot(), PRICING)
            first_checkpoint = append_checkpoint(first, ledger, "first")
            self.assertAlmostEqual(
                first_checkpoint["delta"]["cost_usd"], first["totals"]["cost_usd"]
            )

            second = price_snapshot(snapshot(input_tokens=1100), PRICING)
            second_checkpoint = append_checkpoint(second, ledger, "second")
            self.assertGreater(second_checkpoint["delta"]["input_tokens"], 0)
            self.assertEqual(len((ledger / "aic-ledger.csv").read_text().splitlines()), 3)

            lower = price_snapshot(snapshot(input_tokens=900), PRICING)
            with self.assertRaisesRegex(ValueError, "regressed"):
                append_checkpoint(lower, ledger, "bad")

            reset_checkpoint = append_checkpoint(lower, ledger, "reset", reset=True)
            self.assertTrue(reset_checkpoint["scopeChange"])
            self.assertTrue(reset_checkpoint["archivedFiles"])
            self.assertTrue(
                all(Path(path).exists() for path in reset_checkpoint["archivedFiles"])
            )

    def test_ledger_rejects_scope_or_rate_card_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            first = price_snapshot(snapshot(), PRICING)
            append_checkpoint(first, ledger, "first")

            changed_scope = price_snapshot(snapshot(input_tokens=1200), PRICING)
            changed_scope["scope"]["filter"] = {"since": "2026-08-01T00:00:00Z"}
            with self.assertRaisesRegex(ValueError, "scope or rate card changed"):
                append_checkpoint(changed_scope, ledger, "bad scope")

            changed_rate = price_snapshot(snapshot(input_tokens=1200), PRICING)
            changed_rate["rateCard"]["version"] = "different"
            with self.assertRaisesRegex(ValueError, "scope or rate card changed"):
                append_checkpoint(changed_rate, ledger, "bad rate")

            accepted = append_checkpoint(
                changed_scope, ledger, "new scope", allow_scope_change=True
            )
            self.assertTrue(accepted["scopeChange"])

    def test_concurrent_checkpoints_do_not_lose_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            report = price_snapshot(snapshot(), PRICING)
            context = multiprocessing.get_context("spawn")
            processes = [
                context.Process(
                    target=append_worker, args=(report, directory, f"worker-{index}")
                )
                for index in range(4)
            ]
            for process in processes:
                process.start()
            for process in processes:
                process.join(15)
                self.assertEqual(process.exitcode, 0)
            lines = (Path(directory) / "aic-ledger.csv").read_text().splitlines()
            self.assertEqual(len(lines), 5)
            import csv

            with (Path(directory) / "aic-ledger.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                last_row = list(csv.DictReader(handle))[-1]
            latest_report = read_json(Path(directory) / "aic-report.json")
            self.assertEqual(latest_report["scope"]["marker"], last_row["label"])

    def test_recovers_interrupted_report_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            report = price_snapshot(snapshot(), PRICING)
            real_write_json = core.write_json

            def fail_report_once(path, value):
                if path.name == "aic-report.json":
                    raise OSError("simulated interruption")
                return real_write_json(path, value)

            with patch("ai_build_cost.core.write_json", side_effect=fail_report_once):
                with self.assertRaisesRegex(OSError, "simulated interruption"):
                    append_checkpoint(report, ledger, "interrupted")

            self.assertTrue((ledger / ".aic-pending.json").exists())
            self.assertTrue(recover_checkpoint(ledger))
            self.assertFalse((ledger / ".aic-pending.json").exists())
            import csv

            with (ledger / "aic-ledger.csv").open(
                encoding="utf-8", newline=""
            ) as handle:
                ledger_checkpoint_id = list(csv.DictReader(handle))[-1][
                    "checkpoint_id"
                ]
            self.assertEqual(
                read_json(ledger / "aic-state.json")["checkpointId"],
                ledger_checkpoint_id,
            )
            self.assertEqual(
                read_json(ledger / "aic-report.json")["totals"],
                report["totals"],
            )

    def test_interrupted_reset_preserves_active_checkpoint_set(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory)
            original = price_snapshot(snapshot(), PRICING)
            append_checkpoint(original, ledger, "original")
            original_state = read_json(ledger / "aic-state.json")
            real_replace = core.os.replace

            def fail_ledger_replace(source, destination):
                if Path(destination).name == "aic-ledger.csv":
                    raise OSError("simulated reset interruption")
                return real_replace(source, destination)

            replacement = price_snapshot(snapshot(input_tokens=900), PRICING)
            with patch("ai_build_cost.core.os.replace", side_effect=fail_ledger_replace):
                with self.assertRaisesRegex(OSError, "simulated reset interruption"):
                    append_checkpoint(replacement, ledger, "replacement", reset=True)

            self.assertTrue((ledger / ".aic-pending.json").exists())
            self.assertTrue(recover_checkpoint(ledger))
            self.assertEqual(
                read_json(ledger / "aic-state.json")["checkpointId"],
                original_state["checkpointId"],
            )
            self.assertEqual(
                read_json(ledger / "aic-report.json")["totals"],
                original["totals"],
            )
            self.assertEqual(
                len((ledger / "aic-ledger.csv").read_text().splitlines()), 2
            )

    def test_dashboard_is_self_contained_and_theme_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.html"
            report = price_snapshot(snapshot(), PRICING)
            report["models"][0]["model"] = '</SCRIPT><img src=x onerror=alert(1)>'
            render_dashboard(report, output, baseline=report, title="Test Report")
            content = output.read_text(encoding="utf-8")
            self.assertIn('new URLSearchParams(window.location.search).get("scoutTheme")', content)
            self.assertIn("--cp-accent:", content)
            self.assertIn("Test Report", content)
            self.assertNotIn('src="http', content)
            self.assertIn("esc(model.model)", content)
            self.assertNotIn("${model.model}", content)
            self.assertNotIn("</SCRIPT>", content)
            self.assertIn("\\u003c/SCRIPT\\u003e", content)

    def test_report_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            report = price_snapshot(snapshot(), PRICING)
            path.write_text(json.dumps(report), encoding="utf-8")
            self.assertEqual(read_json(path)["schemaVersion"], 1)


if __name__ == "__main__":
    unittest.main()

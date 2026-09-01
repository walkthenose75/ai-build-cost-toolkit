import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ai_build_cost.core import price_snapshot


PRICING = {
    "version": "test",
    "models": {
        "test-model": {
            "input": 1,
            "output": 2,
            "cacheRead": 0.1,
            "cacheWrite": 1,
        },
        "default": {
            "input": 1,
            "output": 2,
            "cacheRead": 0.1,
            "cacheWrite": 1,
        },
    },
}


def report(repository="owner/repo", version="test"):
    value = {
        "scope": {"repository": repository, "sessionCount": 1, "requestCount": 1},
        "totals": {"premium_credits": None},
        "models": [
            {
                "model": "test-model",
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_read_tokens": 80,
                "cache_write_tokens": 10,
                "reasoning_tokens": 0,
                "active_ms": 1000,
                "requests": 1,
            }
        ],
    }
    result = price_snapshot(value, PRICING)
    result["rateCard"]["version"] = version
    return result


class CliTests(unittest.TestCase):
    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "ai_build_cost", *arguments],
            capture_output=True,
            text=True,
        )

    def test_validate_rejects_inconsistent_totals(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            value = report()
            value["totals"]["input_tokens"] += 1
            path.write_text(json.dumps(value), encoding="utf-8")
            result = self.run_cli("validate", "--report", str(path))
            self.assertEqual(result.returncode, 1)
            self.assertIn("per-model sum", result.stderr)

    def test_dashboard_rejects_mismatched_rate_cards(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current = root / "current.json"
            baseline = root / "baseline.json"
            output = root / "report.html"
            current.write_text(json.dumps(report(version="v2")), encoding="utf-8")
            baseline.write_text(json.dumps(report(version="v1")), encoding="utf-8")
            result = self.run_cli(
                "dashboard",
                "--report",
                str(current),
                "--baseline",
                str(baseline),
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("different rate cards", result.stderr)
            self.assertFalse(output.exists())

    def test_dashboard_rejects_baseline_that_exceeds_current(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_value = report()
            baseline_value = report()
            baseline_value["totals"]["input_tokens"] += 1
            baseline_value["models"][0]["input_tokens"] += 1
            baseline_value["models"][0]["fresh_input_tokens"] += 1
            baseline_value["totals"]["fresh_input_tokens"] += 1
            current = root / "current.json"
            baseline = root / "baseline.json"
            output = root / "report.html"
            current.write_text(json.dumps(current_value), encoding="utf-8")
            baseline.write_text(json.dumps(baseline_value), encoding="utf-8")
            result = self.run_cli(
                "dashboard",
                "--report",
                str(current),
                "--baseline",
                str(baseline),
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("exceeds current", result.stderr)

    def test_install_skill_is_cross_platform(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "skill"
            result = self.run_cli(
                "install-skill", "--destination", str(destination)
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((destination / "SKILL.md").exists())

    def test_installs_power_apps_code_app_page_and_typed_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            target = root / "src" / "features" / "ai-build-cost"
            report_path.write_text(json.dumps(report()), encoding="utf-8")

            result = self.run_cli(
                "install-code-app-page",
                "--report",
                str(report_path),
                "--target",
                str(target),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                {path.name for path in target.iterdir()},
                {
                    "AiBuildCostPage.tsx",
                    "AiBuildCostPage.css",
                    "aic-data.ts",
                    "index.ts",
                    "README.md",
                },
            )
            data_source = (target / "aic-data.ts").read_text(encoding="utf-8")
            self.assertIn("AIC_CURRENT_REPORT: AicReport", data_source)
            self.assertIn("AIC_BASELINE_REPORT: AicReport | undefined = undefined", data_source)

            duplicate = self.run_cli(
                "install-code-app-page",
                "--report",
                str(report_path),
                "--target",
                str(target),
            )
            self.assertEqual(duplicate.returncode, 2)
            self.assertIn("--force", duplicate.stderr)

    def test_installs_compatible_baseline_into_code_app_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_path = root / "current.json"
            baseline_path = root / "baseline.json"
            target = root / "feature"
            current_path.write_text(json.dumps(report()), encoding="utf-8")
            baseline_path.write_text(json.dumps(report()), encoding="utf-8")

            result = self.run_cli(
                "install-code-app-page",
                "--report",
                str(current_path),
                "--baseline",
                str(baseline_path),
                "--target",
                str(target),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            data_source = (target / "aic-data.ts").read_text(encoding="utf-8")
            self.assertNotIn(
                "AIC_BASELINE_REPORT: AicReport | undefined = undefined",
                data_source,
            )
            self.assertGreater(data_source.count('"schemaVersion": 1'), 1)

    def test_code_app_template_has_no_project_specific_assumptions(self):
        template = (
            Path(__file__).parents[1]
            / "ai_build_cost"
            / "templates"
            / "power_apps_code_app"
            / "AiBuildCostPage.tsx"
        ).read_text(encoding="utf-8")
        self.assertNotIn("HLS", template)
        self.assertNotIn("$175", template)
        self.assertNotIn("localStorage", template)
        self.assertIn('aria-label="Reporting period"', template)
        self.assertIn("not an invoice", template)


if __name__ == "__main__":
    unittest.main()

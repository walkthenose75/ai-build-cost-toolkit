import sqlite3
import tempfile
import unittest
from pathlib import Path

from ai_build_cost.collector import collect_project, doctor


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        self.store = Path(self.temp.name) / "session-store.db"
        connection = sqlite3.connect(self.store)
        connection.executescript(
            """
            CREATE TABLE sessions (
              id TEXT PRIMARY KEY, cwd TEXT, repository TEXT, host_type TEXT,
              branch TEXT, summary TEXT, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE assistant_usage_events (
              id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, agent_id TEXT,
              turn_index INTEGER,
              model TEXT NOT NULL, input_tokens INTEGER, output_tokens INTEGER,
              cache_read_tokens INTEGER, cache_write_tokens INTEGER,
              reasoning_tokens INTEGER, request_multiplier REAL,
              duration_ms INTEGER, created_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO sessions (id,cwd,repository,created_at,updated_at) VALUES (?,?,?,?,?)",
            ("s1", str(self.root), "owner/repo", "2026-08-01", "2026-08-02"),
        )
        connection.execute(
            "INSERT INTO sessions (id,cwd,repository,created_at,updated_at) VALUES (?,?,?,?,?)",
            ("other", str(Path(self.temp.name) / "other"), "owner/other", "2026-08-01", "2026-08-02"),
        )
        rows = [
            ("s1", None, 0, "model-a", 100, 10, 80, 10, 0, 2.0, 1000, "2026-08-01T10:00:00Z"),
            ("s1", None, 0, "model-a", 50, 5, 40, 5, 0, 2.0, 500, "2026-08-01T10:00:01Z"),
            ("s1", None, 1, "model-b", 200, 20, 100, 0, 4, 1.5, 2000, "2026-08-02T10:00:00Z"),
            ("s1", "agent-1", 0, "model-a", 20, 2, 10, 0, 0, 0.5, 300, "2026-08-02T10:05:00Z"),
            ("other", None, 0, "model-x", 999, 99, 0, 0, 0, 9.0, 9999, "2026-08-01T10:00:00Z"),
        ]
        connection.executemany(
            """
            INSERT INTO assistant_usage_events (
              session_id,agent_id,turn_index,model,input_tokens,output_tokens,
              cache_read_tokens,cache_write_tokens,reasoning_tokens,
              request_multiplier,duration_ms,created_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            rows,
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def test_collects_only_project_sessions(self):
        result = collect_project(self.root, self.store)
        self.assertEqual(result["scope"]["sessionCount"], 1)
        self.assertEqual(result["scope"]["requestCount"], 3)
        self.assertEqual(result["totals"]["premium_credits"], 4.0)
        self.assertEqual(sum(row["input_tokens"] for row in result["models"]), 370)
        self.assertEqual(sum(row["active_ms"] for row in result["models"]), 3800)

    def test_deduplicates_credit_within_turn(self):
        result = collect_project(self.root, self.store)
        self.assertEqual(result["totals"]["premium_credits"], 4.0)

    def test_partial_credit_telemetry_is_unavailable(self):
        connection = sqlite3.connect(self.store)
        connection.execute(
            "UPDATE assistant_usage_events SET request_multiplier = NULL "
            "WHERE session_id = 's1' AND agent_id = 'agent-1'"
        )
        connection.commit()
        connection.close()
        result = collect_project(self.root, self.store)
        self.assertIsNone(result["totals"]["premium_credits"])
        self.assertEqual(result["scope"]["creditKnownRequestCount"], 2)
        self.assertEqual(result["scope"]["requestCount"], 3)

    def test_rejects_invalid_since_timestamp(self):
        with self.assertRaisesRegex(ValueError, "Invalid --since"):
            collect_project(self.root, self.store, since="not-a-date")

    def test_rejects_store_missing_reasoning_tokens_column(self):
        store = Path(self.temp.name) / "legacy-store.db"
        connection = sqlite3.connect(store)
        connection.executescript(
            """
            CREATE TABLE sessions (id TEXT PRIMARY KEY, cwd TEXT, repository TEXT);
            CREATE TABLE assistant_usage_events (
              id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, agent_id TEXT,
              turn_index INTEGER, model TEXT NOT NULL, input_tokens INTEGER,
              output_tokens INTEGER, cache_read_tokens INTEGER,
              cache_write_tokens INTEGER, request_multiplier REAL,
              duration_ms INTEGER, created_at TEXT
            );
            """
        )
        connection.commit()
        connection.close()
        with self.assertRaisesRegex(ValueError, "reasoning_tokens"):
            doctor(store)

    def test_doctor_reports_supported_store(self):
        result = doctor(self.store)
        self.assertTrue(result["supported"])
        self.assertEqual(result["sessionCount"], 2)
        self.assertEqual(result["usageEventCount"], 5)


if __name__ == "__main__":
    unittest.main()

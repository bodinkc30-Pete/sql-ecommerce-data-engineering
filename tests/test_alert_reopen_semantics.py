from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUALITY_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "04_run_quality_checks.py"
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "05_run_pipeline.py"


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE pipeline_alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key TEXT NOT NULL UNIQUE,
    alert_fingerprint TEXT UNIQUE,
    source_type TEXT NOT NULL,
    alert_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    pipeline_name TEXT NOT NULL,
    run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    first_detected_at TEXT NOT NULL,
    last_detected_at TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    acknowledged_at TEXT,
    resolved_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pipeline_alert_occurrences (
    occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id INTEGER NOT NULL,
    run_id TEXT NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    detected_at TEXT NOT NULL,
    error_type TEXT,
    raw_error_message TEXT,
    normalized_error_signature TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (alert_id)
        REFERENCES pipeline_alerts(alert_id)
        ON DELETE CASCADE
);
"""


def load_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load module: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlertReopenSemanticsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.quality_runner = load_module(
            QUALITY_SCRIPT_PATH,
            "quality_runner_for_alert_reopen_test",
        )
        cls.pipeline_runner = load_module(
            PIPELINE_SCRIPT_PATH,
            "pipeline_runner_for_alert_reopen_test",
        )

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_directory.name)
            / "alert_reopen_semantics.db"
        )

        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.executescript(SCHEMA_SQL)

        self.original_quality_database_path = (
            self.quality_runner.DATABASE_PATH
        )
        self.original_pipeline_database_path = (
            self.pipeline_runner.DATABASE_PATH
        )

        self.quality_runner.DATABASE_PATH = self.database_path
        self.pipeline_runner.DATABASE_PATH = self.database_path

    def tearDown(self) -> None:
        self.quality_runner.DATABASE_PATH = (
            self.original_quality_database_path
        )
        self.pipeline_runner.DATABASE_PATH = (
            self.original_pipeline_database_path
        )
        self.temp_directory.cleanup()

    def fetch_alert(self) -> sqlite3.Row:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row

        try:
            row = connection.execute(
                """
                SELECT *
                FROM pipeline_alerts
                ORDER BY alert_id
                LIMIT 1;
                """
            ).fetchone()
        finally:
            connection.close()

        if row is None:
            raise AssertionError("Expected one alert row.")

        return row

    def fetch_occurrences(self) -> list[sqlite3.Row]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row

        try:
            return connection.execute(
                """
                SELECT *
                FROM pipeline_alert_occurrences
                ORDER BY occurrence_id;
                """
            ).fetchall()
        finally:
            connection.close()

    def mark_only_alert_resolved(self) -> None:
        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute(
                """
                UPDATE pipeline_alerts
                SET
                    status = 'RESOLVED',
                    acknowledged_at = '2026-08-24 04:00:00',
                    resolved_at = '2026-08-24 04:01:00',
                    updated_at = '2026-08-24 04:01:00';
                """
            )
            connection.commit()

    def make_quality_failure(self) -> dict:
        return {
            "outcome": "FAIL",
            "critical_count": 1,
            "error_count": 0,
            "warning_count": 0,
            "issue_count": 1,
            "evaluated_rows": 100,
            "error_rate_percent": 0.0,
            "reason": "CRITICAL issue detected: 1",
        }

    def test_quality_alert_recurrence_reopens_resolved_alert(self) -> None:
        self.quality_runner.record_quality_alert(
            run_id="quality-run-01",
            step_name="03_referential_integrity",
            evaluation=self.make_quality_failure(),
            detected_at="2026-08-24 04:02:00",
        )

        first_alert = self.fetch_alert()
        first_alert_id = first_alert["alert_id"]
        first_fingerprint = first_alert["alert_fingerprint"]

        self.mark_only_alert_resolved()

        self.quality_runner.record_quality_alert(
            run_id="quality-run-02",
            step_name="03_referential_integrity",
            evaluation=self.make_quality_failure(),
            detected_at="2026-08-24 04:03:00",
        )

        alert = self.fetch_alert()
        occurrences = self.fetch_occurrences()

        self.assertEqual(first_alert_id, alert["alert_id"])
        self.assertEqual(
            first_fingerprint,
            alert["alert_fingerprint"],
        )
        self.assertEqual("OPEN", alert["status"])
        self.assertIsNone(alert["acknowledged_at"])
        self.assertIsNone(alert["resolved_at"])
        self.assertEqual(2, alert["occurrence_count"])
        self.assertEqual(
            "2026-08-24 04:03:00",
            alert["last_detected_at"],
        )
        self.assertEqual(2, len(occurrences))
        self.assertEqual(
            "quality-run-02",
            occurrences[-1]["run_id"],
        )

    def test_pipeline_alert_recurrence_reopens_resolved_alert(self) -> None:
        common = {
            "pipeline_name": "ecommerce_pipeline",
            "step_name": "LOAD_RAW_DATA",
            "attempt_number": 1,
            "step_status": "FAILED",
            "sla_status": "ON_TIME",
            "error_type": "ValueError",
            "error_message": "Recurring deterministic failure",
        }

        self.pipeline_runner.record_step_alert(
            **common,
            run_id="pipeline-run-01",
            detected_at="2026-08-24 04:04:00",
        )

        first_alert = self.fetch_alert()
        first_alert_id = first_alert["alert_id"]
        first_fingerprint = first_alert["alert_fingerprint"]

        self.mark_only_alert_resolved()

        self.pipeline_runner.record_step_alert(
            **common,
            run_id="pipeline-run-02",
            detected_at="2026-08-24 04:05:00",
        )

        alert = self.fetch_alert()
        occurrences = self.fetch_occurrences()

        self.assertEqual(first_alert_id, alert["alert_id"])
        self.assertEqual(
            first_fingerprint,
            alert["alert_fingerprint"],
        )
        self.assertEqual("OPEN", alert["status"])
        self.assertIsNone(alert["acknowledged_at"])
        self.assertIsNone(alert["resolved_at"])
        self.assertEqual(2, alert["occurrence_count"])
        self.assertEqual(
            "2026-08-24 04:05:00",
            alert["last_detected_at"],
        )
        self.assertEqual(2, len(occurrences))
        self.assertEqual(
            "pipeline-run-02",
            occurrences[-1]["run_id"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

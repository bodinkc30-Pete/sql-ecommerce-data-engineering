from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUALITY_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "04_run_quality_checks.py"


def load_quality_module():
    spec = importlib.util.spec_from_file_location(
        "quality_runner_for_alert_runtime_test",
        QUALITY_SCRIPT_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load quality module: {QUALITY_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityAlertRuntimeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.quality_runner = load_quality_module()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_directory.name)
            / "quality_alert_runtime.db"
        )

        self.original_database_path = self.quality_runner.DATABASE_PATH
        self.quality_runner.DATABASE_PATH = self.database_path

        connection = sqlite3.connect(self.database_path)
        try:
            connection.executescript(
                """
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
            )
            connection.commit()
        finally:
            connection.close()

    def tearDown(self) -> None:
        self.quality_runner.DATABASE_PATH = self.original_database_path
        self.temp_directory.cleanup()

    def make_evaluation(
        self,
        *,
        outcome: str,
        critical_count: int = 0,
        error_count: int = 0,
        warning_count: int = 0,
        reason: str,
    ) -> dict:
        return {
            "outcome": outcome,
            "critical_count": critical_count,
            "error_count": error_count,
            "warning_count": warning_count,
            "issue_count": (
                critical_count
                + error_count
                + warning_count
            ),
            "evaluated_rows": 100,
            "error_rate_percent": float(error_count),
            "reason": reason,
        }

    def fetch_alerts(self) -> list[sqlite3.Row]:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(
                """
                SELECT *
                FROM pipeline_alerts
                ORDER BY alert_id;
                """
            ).fetchall()
        finally:
            connection.close()

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

    def record(
        self,
        *,
        run_id: str,
        step_name: str,
        evaluation: dict,
        detected_at: str,
    ) -> None:
        self.quality_runner.record_quality_alert(
            run_id=run_id,
            step_name=step_name,
            evaluation=evaluation,
            detected_at=detected_at,
        )

    def test_pass_does_not_create_quality_alert(self) -> None:
        self.record(
            run_id="run-pass",
            step_name="01_null_checks",
            evaluation=self.make_evaluation(
                outcome="PASS",
                reason="No data quality issues detected",
            ),
            detected_at="2026-08-23 16:00:00",
        )

        self.assertEqual([], self.fetch_alerts())
        self.assertEqual([], self.fetch_occurrences())

    def test_warn_creates_quality_warning_alert_and_occurrence(self) -> None:
        self.record(
            run_id="run-warn-1",
            step_name="02_duplicate_checks",
            evaluation=self.make_evaluation(
                outcome="WARN",
                warning_count=2,
                reason=(
                    "Issues detected within tolerance: "
                    "ERROR=0, WARNING=2, error_rate=0.0000%"
                ),
            ),
            detected_at="2026-08-23 16:01:00",
        )

        alerts = self.fetch_alerts()
        occurrences = self.fetch_occurrences()

        self.assertEqual(1, len(alerts))
        self.assertEqual(1, len(occurrences))

        alert = alerts[0]
        occurrence = occurrences[0]

        self.assertEqual("QUALITY_GATE", alert["source_type"])
        self.assertEqual("DATA_QUALITY_WARNING", alert["alert_type"])
        self.assertEqual("WARNING", alert["severity"])
        self.assertEqual("OPEN", alert["status"])
        self.assertEqual(1, alert["occurrence_count"])
        self.assertTrue(alert["alert_fingerprint"])

        self.assertEqual(alert["alert_id"], occurrence["alert_id"])
        self.assertEqual("run-warn-1", occurrence["run_id"])
        self.assertEqual(1, occurrence["attempt_number"])
        self.assertEqual(
            "DataQualityWarning",
            occurrence["error_type"],
        )
        self.assertTrue(
            occurrence["normalized_error_signature"]
        )

    def test_fail_with_critical_issue_creates_critical_quality_alert(
        self,
    ) -> None:
        self.record(
            run_id="run-critical-1",
            step_name="03_referential_integrity",
            evaluation=self.make_evaluation(
                outcome="FAIL",
                critical_count=1,
                reason="CRITICAL issue detected: 1",
            ),
            detected_at="2026-08-23 16:02:00",
        )

        alert = self.fetch_alerts()[0]

        self.assertEqual("QUALITY_GATE", alert["source_type"])
        self.assertEqual("DATA_QUALITY_FAILURE", alert["alert_type"])
        self.assertEqual("CRITICAL", alert["severity"])

    def test_fail_from_error_threshold_creates_error_quality_alert(
        self,
    ) -> None:
        self.record(
            run_id="run-error-1",
            step_name="05_business_rule_checks",
            evaluation=self.make_evaluation(
                outcome="FAIL",
                error_count=6,
                reason=(
                    "ERROR threshold exceeded: "
                    "count=6/5, rate=6.0000%/1.0000%"
                ),
            ),
            detected_at="2026-08-23 16:03:00",
        )

        alert = self.fetch_alerts()[0]

        self.assertEqual("QUALITY_GATE", alert["source_type"])
        self.assertEqual("DATA_QUALITY_FAILURE", alert["alert_type"])
        self.assertEqual("ERROR", alert["severity"])

    def test_same_quality_warning_across_runs_deduplicates_alert(
        self,
    ) -> None:
        evaluation = self.make_evaluation(
            outcome="WARN",
            warning_count=2,
            reason=(
                "Issues detected within tolerance: "
                "ERROR=0, WARNING=2, error_rate=0.0000%"
            ),
        )

        self.record(
            run_id="run-warn-a",
            step_name="02_duplicate_checks",
            evaluation=evaluation,
            detected_at="2026-08-23 16:04:00",
        )
        self.record(
            run_id="run-warn-b",
            step_name="02_duplicate_checks",
            evaluation=evaluation,
            detected_at="2026-08-23 16:05:00",
        )

        alerts = self.fetch_alerts()
        occurrences = self.fetch_occurrences()

        self.assertEqual(1, len(alerts))
        self.assertEqual(2, len(occurrences))
        self.assertEqual(2, alerts[0]["occurrence_count"])

        self.assertEqual(
            {"run-warn-a", "run-warn-b"},
            {row["run_id"] for row in occurrences},
        )
        self.assertEqual(
            1,
            len(
                {
                    row["normalized_error_signature"]
                    for row in occurrences
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()

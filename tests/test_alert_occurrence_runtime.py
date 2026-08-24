from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "05_run_pipeline.py"
CORE_SCHEMA_PATH = PROJECT_ROOT / "schema" / "02_create_core_tables.sql"


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location(
        "pipeline_runner_for_alert_occurrence_runtime_test",
        PIPELINE_SCRIPT_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load pipeline module: {PIPELINE_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlertOccurrenceRuntimeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline_runner = load_pipeline_module()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_directory.name)
            / "alert_occurrence_runtime.db"
        )

        connection = sqlite3.connect(self.database_path)
        try:
            connection.execute("PRAGMA foreign_keys = ON;")
            connection.executescript(
                CORE_SCHEMA_PATH.read_text(encoding="utf-8")
            )
        finally:
            connection.close()

        self.original_database_path = self.pipeline_runner.DATABASE_PATH
        self.pipeline_runner.DATABASE_PATH = self.database_path

    def tearDown(self) -> None:
        self.pipeline_runner.DATABASE_PATH = self.original_database_path
        self.temp_directory.cleanup()

    def record_failure(
        self,
        *,
        run_id: str,
        attempt_number: int = 1,
        step_name: str = "LOAD_RAW_DATA",
        error_type: str = "OperationalError",
        error_message: str = "database is locked after 1.02 sec",
        detected_at: str = "2026-08-23 14:00:00",
    ) -> None:
        self.pipeline_runner.record_step_alert(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            run_id=run_id,
            step_name=step_name,
            attempt_number=attempt_number,
            step_status="FAILED",
            sla_status="ON_TIME",
            error_type=error_type,
            error_message=error_message,
            detected_at=detected_at,
        )

    def record_sla_breach(
        self,
        *,
        run_id: str,
        attempt_number: int = 1,
        step_name: str = "LOAD_RAW_DATA",
        detected_at: str = "2026-08-23 14:00:00",
    ) -> None:
        self.pipeline_runner.record_step_alert(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            run_id=run_id,
            step_name=step_name,
            attempt_number=attempt_number,
            step_status="SUCCESS",
            sla_status="BREACHED",
            error_type=None,
            error_message=None,
            detected_at=detected_at,
        )

    def fetch_scalar(self, sql: str, params: tuple = ()) -> int:
        connection = sqlite3.connect(self.database_path)
        try:
            row = connection.execute(sql, params).fetchone()
            if row is None:
                raise AssertionError("Expected one scalar row.")
            return int(row[0])
        finally:
            connection.close()

    def fetch_all(self, sql: str, params: tuple = ()):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(sql, params).fetchall()
        finally:
            connection.close()

    def test_same_failure_across_runs_is_one_alert_with_two_occurrences(
        self,
    ) -> None:
        self.record_failure(
            run_id="run-a",
            error_message="database is locked after 1.02 sec",
            detected_at="2026-08-23 14:00:00",
        )
        self.record_failure(
            run_id="run-b",
            error_message="database is locked after 1.97 sec",
            detected_at="2026-08-23 14:05:00",
        )

        self.assertEqual(
            1,
            self.fetch_scalar("SELECT COUNT(*) FROM pipeline_alerts;"),
        )
        self.assertEqual(
            2,
            self.fetch_scalar(
                "SELECT COUNT(*) FROM pipeline_alert_occurrences;"
            ),
        )

        alert = self.fetch_all(
            """
            SELECT
                alert_fingerprint,
                occurrence_count,
                first_detected_at,
                last_detected_at
            FROM pipeline_alerts;
            """
        )[0]

        self.assertIsNotNone(alert["alert_fingerprint"])
        self.assertEqual(2, alert["occurrence_count"])
        self.assertEqual(
            "2026-08-23 14:00:00",
            alert["first_detected_at"],
        )
        self.assertEqual(
            "2026-08-23 14:05:00",
            alert["last_detected_at"],
        )

        occurrences = self.fetch_all(
            """
            SELECT
                run_id,
                attempt_number,
                error_type,
                normalized_error_signature
            FROM pipeline_alert_occurrences
            ORDER BY occurrence_id;
            """
        )

        self.assertEqual(
            ["run-a", "run-b"],
            [row["run_id"] for row in occurrences],
        )
        self.assertEqual(
            ["OperationalError", "OperationalError"],
            [row["error_type"] for row in occurrences],
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

    def test_same_failure_across_attempts_is_same_alert(self) -> None:
        self.record_failure(
            run_id="run-a",
            attempt_number=1,
        )
        self.record_failure(
            run_id="run-a",
            attempt_number=2,
            detected_at="2026-08-23 14:01:00",
        )

        self.assertEqual(
            1,
            self.fetch_scalar("SELECT COUNT(*) FROM pipeline_alerts;"),
        )
        self.assertEqual(
            2,
            self.fetch_scalar(
                "SELECT COUNT(*) FROM pipeline_alert_occurrences;"
            ),
        )

    def test_different_error_types_create_different_alerts(self) -> None:
        self.record_failure(
            run_id="run-a",
            error_type="OperationalError",
            error_message="database is locked",
        )
        self.record_failure(
            run_id="run-b",
            error_type="ValueError",
            error_message="database is locked",
        )

        self.assertEqual(
            2,
            self.fetch_scalar("SELECT COUNT(*) FROM pipeline_alerts;"),
        )

    def test_different_steps_do_not_deduplicate(self) -> None:
        self.record_failure(
            run_id="run-a",
            step_name="LOAD_RAW_DATA",
        )
        self.record_failure(
            run_id="run-b",
            step_name="RUN_TRANSFORMATIONS",
        )

        self.assertEqual(
            2,
            self.fetch_scalar("SELECT COUNT(*) FROM pipeline_alerts;"),
        )

    def test_same_sla_breach_across_runs_is_one_alert_with_two_occurrences(
        self,
    ) -> None:
        self.record_sla_breach(
            run_id="run-a",
            detected_at="2026-08-23 14:00:00",
        )
        self.record_sla_breach(
            run_id="run-b",
            detected_at="2026-08-23 14:05:00",
        )

        self.assertEqual(
            1,
            self.fetch_scalar("SELECT COUNT(*) FROM pipeline_alerts;"),
        )
        self.assertEqual(
            2,
            self.fetch_scalar(
                "SELECT COUNT(*) FROM pipeline_alert_occurrences;"
            ),
        )


if __name__ == "__main__":
    unittest.main()

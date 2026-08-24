from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "05_run_pipeline.py"


ALERT_SCHEMA_SQL = """
CREATE TABLE pipeline_alerts (
    alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key TEXT NOT NULL UNIQUE,
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
"""


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location(
        "pipeline_runner_for_alert_runtime_test",
        PIPELINE_SCRIPT_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load pipeline module: {PIPELINE_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PipelineAlertRuntimeTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline_runner = load_pipeline_module()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_directory.name)
            / "alert_runtime_test.db"
        )

        connection = sqlite3.connect(self.database_path)
        try:
            connection.executescript(ALERT_SCHEMA_SQL)
        finally:
            connection.close()

        self.original_database_path = (
            self.pipeline_runner.DATABASE_PATH
        )
        self.pipeline_runner.DATABASE_PATH = self.database_path

    def tearDown(self) -> None:
        self.pipeline_runner.DATABASE_PATH = (
            self.original_database_path
        )
        self.temp_directory.cleanup()

    def require_runtime_contract(self):
        required_functions = (
            "build_alert_key",
            "record_step_alert",
        )

        for function_name in required_functions:
            self.assertTrue(
                hasattr(self.pipeline_runner, function_name),
                f"{function_name} is missing from 05_run_pipeline.py",
            )

        return (
            self.pipeline_runner.build_alert_key,
            self.pipeline_runner.record_step_alert,
        )

    def fetch_alerts(self) -> list[sqlite3.Row]:
        connection = sqlite3.connect(self.database_path)
        try:
            connection.row_factory = sqlite3.Row
            return connection.execute(
                """
                SELECT *
                FROM pipeline_alerts
                ORDER BY alert_id;
                """
            ).fetchall()
        finally:
            connection.close()

    def test_build_alert_key_is_deterministic(self) -> None:
        build_alert_key, _ = self.require_runtime_contract()

        first = build_alert_key(
            pipeline_name="ecommerce_pipeline",
            run_id="run-001",
            step_name="LOAD_RAW_DATA",
            attempt_number=1,
            alert_type="STEP_FAILURE",
        )
        second = build_alert_key(
            pipeline_name="ecommerce_pipeline",
            run_id="run-001",
            step_name="LOAD_RAW_DATA",
            attempt_number=1,
            alert_type="STEP_FAILURE",
        )
        different_type = build_alert_key(
            pipeline_name="ecommerce_pipeline",
            run_id="run-001",
            step_name="LOAD_RAW_DATA",
            attempt_number=1,
            alert_type="SLA_BREACH",
        )

        self.assertEqual(first, second)
        self.assertNotEqual(first, different_type)
        self.assertTrue(first)

    def test_step_failure_creates_one_critical_alert(self) -> None:
        _, record_step_alert = self.require_runtime_contract()

        record_step_alert(
            pipeline_name="ecommerce_pipeline",
            run_id="run-failed",
            step_name="LOAD_RAW_DATA",
            attempt_number=1,
            step_status="FAILED",
            sla_status="ON_TIME",
            error_type="ValueError",
            error_message="Synthetic failure",
            detected_at="2026-08-23T03:00:00",
        )

        alerts = self.fetch_alerts()

        self.assertEqual(1, len(alerts))
        self.assertEqual("ORCHESTRATOR", alerts[0]["source_type"])
        self.assertEqual("STEP_FAILURE", alerts[0]["alert_type"])
        self.assertEqual("CRITICAL", alerts[0]["severity"])
        self.assertEqual("OPEN", alerts[0]["status"])
        self.assertEqual(1, alerts[0]["occurrence_count"])

    def test_failed_step_with_sla_breach_is_single_critical_alert(
        self,
    ) -> None:
        _, record_step_alert = self.require_runtime_contract()

        record_step_alert(
            pipeline_name="ecommerce_pipeline",
            run_id="run-failed-breached",
            step_name="RUN_TRANSFORMATIONS",
            attempt_number=1,
            step_status="FAILED",
            sla_status="BREACHED",
            error_type="RuntimeError",
            error_message="Transformation failed",
            detected_at="2026-08-23T03:01:00",
        )

        alerts = self.fetch_alerts()

        self.assertEqual(1, len(alerts))
        self.assertEqual("STEP_FAILURE", alerts[0]["alert_type"])
        self.assertEqual("CRITICAL", alerts[0]["severity"])
        self.assertIn(
            "BREACHED",
            alerts[0]["message"].upper(),
        )

    def test_successful_sla_breach_creates_warning_alert(
        self,
    ) -> None:
        _, record_step_alert = self.require_runtime_contract()

        record_step_alert(
            pipeline_name="ecommerce_pipeline",
            run_id="run-sla",
            step_name="RUN_QUALITY_CHECKS",
            attempt_number=1,
            step_status="SUCCESS",
            sla_status="BREACHED",
            error_type=None,
            error_message=None,
            detected_at="2026-08-23T03:02:00",
        )

        alerts = self.fetch_alerts()

        self.assertEqual(1, len(alerts))
        self.assertEqual("SLA_BREACH", alerts[0]["alert_type"])
        self.assertEqual("WARNING", alerts[0]["severity"])

    def test_successful_on_time_step_creates_no_alert(self) -> None:
        _, record_step_alert = self.require_runtime_contract()

        record_step_alert(
            pipeline_name="ecommerce_pipeline",
            run_id="run-ok",
            step_name="LOAD_RAW_DATA",
            attempt_number=1,
            step_status="SUCCESS",
            sla_status="ON_TIME",
            error_type=None,
            error_message=None,
            detected_at="2026-08-23T03:03:00",
        )

        self.assertEqual([], self.fetch_alerts())

    def test_repeated_same_alert_is_deduplicated(self) -> None:
        _, record_step_alert = self.require_runtime_contract()

        common_arguments = {
            "pipeline_name": "ecommerce_pipeline",
            "run_id": "run-repeat",
            "step_name": "LOAD_RAW_DATA",
            "attempt_number": 1,
            "step_status": "FAILED",
            "sla_status": "ON_TIME",
            "error_type": "ValueError",
            "error_message": "Repeated deterministic failure",
        }

        record_step_alert(
            **common_arguments,
            detected_at="2026-08-23T03:04:00",
        )
        record_step_alert(
            **common_arguments,
            detected_at="2026-08-23T03:05:00",
        )

        alerts = self.fetch_alerts()

        self.assertEqual(1, len(alerts))
        self.assertEqual(2, alerts[0]["occurrence_count"])
        self.assertEqual(
            "2026-08-23T03:04:00",
            alerts[0]["first_detected_at"],
        )
        self.assertEqual(
            "2026-08-23T03:05:00",
            alerts[0]["last_detected_at"],
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import importlib.util
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "05_run_pipeline.py"


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location(
        "pipeline_runner_for_alert_resilience_test",
        PIPELINE_SCRIPT_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load pipeline module: {PIPELINE_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PipelineAlertResilienceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline_runner = load_pipeline_module()

    def call_record_step_alert(
        self,
        *,
        step_status: str,
        sla_status: str,
        error_type: str | None,
        error_message: str | None,
    ) -> None:
        self.pipeline_runner.record_step_alert(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            run_id="run-alert-resilience",
            step_name="LOAD_RAW_DATA",
            attempt_number=1,
            step_status=step_status,
            sla_status=sla_status,
            error_type=error_type,
            error_message=error_message,
            detected_at="2026-08-23 13:10:00",
        )

    def test_step_failure_alert_write_failure_is_non_blocking(self) -> None:
        with patch.object(
            self.pipeline_runner.sqlite3,
            "connect",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            self.call_record_step_alert(
                step_status="FAILED",
                sla_status="ON_TIME",
                error_type="ValueError",
                error_message="Synthetic step failure",
            )

    def test_sla_breach_alert_write_failure_is_non_blocking(self) -> None:
        with patch.object(
            self.pipeline_runner.sqlite3,
            "connect",
            side_effect=sqlite3.OperationalError("database is locked"),
        ):
            self.call_record_step_alert(
                step_status="SUCCESS",
                sla_status="BREACHED",
                error_type=None,
                error_message=None,
            )


if __name__ == "__main__":
    unittest.main()

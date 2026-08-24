from __future__ import annotations

import importlib.util
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "05_run_pipeline.py"


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location(
        "pipeline_runner_for_alert_hook_test",
        PIPELINE_SCRIPT_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load pipeline module: {PIPELINE_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PipelineAlertHookTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline_runner = load_pipeline_module()

    def base_patches(self):
        runner = self.pipeline_runner

        return (
            patch.object(runner, "validate_script_exists"),
            patch.object(runner, "insert_step_log_start", return_value=101),
            patch.object(
                runner,
                "collect_step_metrics",
                return_value={
                    "rows_read": 10,
                    "rows_written": 9,
                    "rows_rejected": 1,
                },
            ),
            patch.object(runner, "update_step_log_end"),
            patch.object(runner, "insert_sla_metric"),
            patch.object(runner, "insert_pipeline_audit_record"),
            patch.object(runner, "record_lineage_events_for_step"),
            patch.object(runner, "write_log"),
            patch.object(runner, "record_step_alert"),
        )

    def run_with_patches(
        self,
        *,
        returncode: int,
        sla_status: str,
    ):
        (
            validate_script_exists_patch,
            insert_step_log_start_patch,
            collect_step_metrics_patch,
            update_step_log_end_patch,
            insert_sla_metric_patch,
            insert_pipeline_audit_record_patch,
            record_lineage_events_patch,
            write_log_patch,
            record_step_alert_patch,
        ) = self.base_patches()

        process = subprocess.CompletedProcess(
            args=["python", "dummy.py"],
            returncode=returncode,
            stdout="",
            stderr=(
                "Synthetic step failure"
                if returncode != 0
                else ""
            ),
        )

        with (
            validate_script_exists_patch,
            insert_step_log_start_patch,
            collect_step_metrics_patch,
            update_step_log_end_patch,
            insert_sla_metric_patch,
            insert_pipeline_audit_record_patch,
            record_lineage_events_patch,
            write_log_patch,
            record_step_alert_patch as record_step_alert_mock,
            patch.object(
                self.pipeline_runner.subprocess,
                "run",
                return_value=process,
            ),
            patch.object(
                self.pipeline_runner,
                "determine_sla_status",
                return_value=sla_status,
            ),
            patch.object(
                self.pipeline_runner,
                "current_utc_time",
                side_effect=(
                    "2026-08-23 03:20:00",
                    "2026-08-23 03:20:05",
                ),
            ),
        ):
            if returncode == 0:
                self.pipeline_runner.run_script(
                    step_number=2,
                    step_name="LOAD_RAW_DATA",
                    script_name="02_load_raw_data.py",
                    description="Load raw data",
                    run_id="run-hook-test",
                    pipeline_mode="demo",
                    sla_enabled=True,
                    sla_threshold_seconds=5.0,
                    attempt_number=1,
                )
            else:
                with self.assertRaises(RuntimeError):
                    self.pipeline_runner.run_script(
                        step_number=2,
                        step_name="LOAD_RAW_DATA",
                        script_name="02_load_raw_data.py",
                        description="Load raw data",
                        run_id="run-hook-test",
                        pipeline_mode="demo",
                        sla_enabled=True,
                        sla_threshold_seconds=5.0,
                        attempt_number=1,
                    )

        return record_step_alert_mock

    def test_failed_step_calls_runtime_alert_hook(self) -> None:
        alert_mock = self.run_with_patches(
            returncode=1,
            sla_status="ON_TIME",
        )

        alert_mock.assert_called_once()

        call_kwargs = alert_mock.call_args.kwargs
        self.assertEqual("FAILED", call_kwargs["step_status"])
        self.assertEqual("ON_TIME", call_kwargs["sla_status"])
        self.assertEqual("run-hook-test", call_kwargs["run_id"])
        self.assertEqual("LOAD_RAW_DATA", call_kwargs["step_name"])
        self.assertEqual(1, call_kwargs["attempt_number"])
        self.assertEqual(
            "2026-08-23 03:20:05",
            call_kwargs["detected_at"],
        )

    def test_failed_sla_breach_calls_single_runtime_alert_hook(
        self,
    ) -> None:
        alert_mock = self.run_with_patches(
            returncode=1,
            sla_status="BREACHED",
        )

        alert_mock.assert_called_once()

        call_kwargs = alert_mock.call_args.kwargs
        self.assertEqual("FAILED", call_kwargs["step_status"])
        self.assertEqual("BREACHED", call_kwargs["sla_status"])

    def test_successful_sla_breach_calls_runtime_alert_hook(
        self,
    ) -> None:
        alert_mock = self.run_with_patches(
            returncode=0,
            sla_status="BREACHED",
        )

        alert_mock.assert_called_once()

        call_kwargs = alert_mock.call_args.kwargs
        self.assertEqual("SUCCESS", call_kwargs["step_status"])
        self.assertEqual("BREACHED", call_kwargs["sla_status"])
        self.assertIsNone(call_kwargs["error_type"])
        self.assertIsNone(call_kwargs["error_message"])

    def test_successful_on_time_step_still_uses_central_alert_decision(
        self,
    ) -> None:
        alert_mock = self.run_with_patches(
            returncode=0,
            sla_status="ON_TIME",
        )

        alert_mock.assert_called_once()

        call_kwargs = alert_mock.call_args.kwargs
        self.assertEqual("SUCCESS", call_kwargs["step_status"])
        self.assertEqual("ON_TIME", call_kwargs["sla_status"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

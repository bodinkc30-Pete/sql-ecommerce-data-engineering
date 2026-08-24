from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "05_run_pipeline.py"


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location(
        "pipeline_runner_for_alert_fingerprint_test",
        PIPELINE_SCRIPT_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load pipeline module: {PIPELINE_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AlertFingerprintTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline_runner = load_pipeline_module()

    def test_dynamic_database_lock_values_normalize_to_same_signature(
        self,
    ) -> None:
        first = self.pipeline_runner.normalize_alert_error_signature(
            error_type="OperationalError",
            error_message="database is locked after 1.02 sec",
        )
        second = self.pipeline_runner.normalize_alert_error_signature(
            error_type="OperationalError",
            error_message="database is locked after 1.97 sec",
        )

        self.assertEqual(first, second)
        self.assertEqual(
            "operationalerror::database is locked",
            first,
        )

    def test_same_failure_across_runs_has_same_fingerprint(self) -> None:
        first = self.pipeline_runner.build_alert_fingerprint(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            step_name="LOAD_RAW_DATA",
            alert_type="STEP_FAILURE",
            error_type="OperationalError",
            error_message="database is locked after 1.02 sec",
        )
        second = self.pipeline_runner.build_alert_fingerprint(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            step_name="LOAD_RAW_DATA",
            alert_type="STEP_FAILURE",
            error_type="OperationalError",
            error_message="database is locked after 1.97 sec",
        )

        self.assertEqual(first, second)

    def test_different_error_types_have_different_fingerprints(self) -> None:
        operational_error = self.pipeline_runner.build_alert_fingerprint(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            step_name="LOAD_RAW_DATA",
            alert_type="STEP_FAILURE",
            error_type="OperationalError",
            error_message="database is locked",
        )
        value_error = self.pipeline_runner.build_alert_fingerprint(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            step_name="LOAD_RAW_DATA",
            alert_type="STEP_FAILURE",
            error_type="ValueError",
            error_message="database is locked",
        )

        self.assertNotEqual(operational_error, value_error)

    def test_different_steps_have_different_fingerprints(self) -> None:
        load_raw = self.pipeline_runner.build_alert_fingerprint(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            step_name="LOAD_RAW_DATA",
            alert_type="STEP_FAILURE",
            error_type="OperationalError",
            error_message="database is locked",
        )
        transform = self.pipeline_runner.build_alert_fingerprint(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            step_name="RUN_TRANSFORMATIONS",
            alert_type="STEP_FAILURE",
            error_type="OperationalError",
            error_message="database is locked",
        )

        self.assertNotEqual(load_raw, transform)

    def test_different_alert_types_have_different_fingerprints(self) -> None:
        failure = self.pipeline_runner.build_alert_fingerprint(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            step_name="LOAD_RAW_DATA",
            alert_type="STEP_FAILURE",
            error_type="OperationalError",
            error_message="database is locked",
        )
        sla_breach = self.pipeline_runner.build_alert_fingerprint(
            pipeline_name="hybrid_ecommerce_data_pipeline",
            step_name="LOAD_RAW_DATA",
            alert_type="SLA_BREACH",
            error_type=None,
            error_message=None,
        )

        self.assertNotEqual(failure, sla_breach)

    def test_fingerprint_is_deterministic(self) -> None:
        kwargs = {
            "pipeline_name": "hybrid_ecommerce_data_pipeline",
            "step_name": "LOAD_RAW_DATA",
            "alert_type": "STEP_FAILURE",
            "error_type": "ValueError",
            "error_message": (
                "orders.csv contains unexpected_column at 2026-08-23 13:00:01"
            ),
        }

        first = self.pipeline_runner.build_alert_fingerprint(**kwargs)
        second = self.pipeline_runner.build_alert_fingerprint(**kwargs)

        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()

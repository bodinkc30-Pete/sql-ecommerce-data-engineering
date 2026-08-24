from __future__ import annotations

import importlib.util
import io
import sqlite3
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUALITY_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "04_run_quality_checks.py"


def load_quality_module():
    spec = importlib.util.spec_from_file_location(
        "quality_alert_resilience_module",
        QUALITY_SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load quality module: {QUALITY_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class QualityAlertResilienceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_quality_module()

    def test_pass_outcome_does_not_attempt_alert_write(self) -> None:
        evaluation = {
            "outcome": "PASS",
            "critical_count": 0,
            "error_count": 0,
            "warning_count": 0,
            "error_rate_percent": 0.0,
            "reason": "No issues detected.",
        }

        with patch.object(
            self.module.sqlite3,
            "connect",
        ) as connect_mock:
            self.module.record_quality_alert(
                run_id="quality-resilience-pass",
                step_name="01_null_checks",
                evaluation=evaluation,
                detected_at="2026-08-23 20:00:00",
            )

        connect_mock.assert_not_called()

    def test_warning_alert_write_failure_is_non_blocking(self) -> None:
        evaluation = {
            "outcome": "WARN",
            "critical_count": 0,
            "error_count": 0,
            "warning_count": 2,
            "error_rate_percent": 0.0,
            "reason": "Issues detected within tolerance.",
        }

        output = io.StringIO()

        with patch.object(
            self.module.sqlite3,
            "connect",
            side_effect=sqlite3.OperationalError(
                "database is locked"
            ),
        ):
            with redirect_stdout(output):
                self.module.record_quality_alert(
                    run_id="quality-resilience-warning",
                    step_name="02_duplicate_checks",
                    evaluation=evaluation,
                    detected_at="2026-08-23 20:00:01",
                )

        rendered = output.getvalue()

        self.assertIn(
            "[QUALITY ALERT WRITE WARNING]",
            rendered,
        )
        self.assertIn(
            "OperationalError: database is locked",
            rendered,
        )

    def test_critical_alert_write_failure_is_non_blocking(self) -> None:
        evaluation = {
            "outcome": "FAIL",
            "critical_count": 1,
            "error_count": 0,
            "warning_count": 0,
            "error_rate_percent": 0.0,
            "reason": "Critical issue detected.",
        }

        output = io.StringIO()

        with patch.object(
            self.module.sqlite3,
            "connect",
            side_effect=sqlite3.OperationalError(
                "unable to open database file"
            ),
        ):
            with redirect_stdout(output):
                self.module.record_quality_alert(
                    run_id="quality-resilience-critical",
                    step_name="03_referential_integrity",
                    evaluation=evaluation,
                    detected_at="2026-08-23 20:00:02",
                )

        rendered = output.getvalue()

        self.assertIn(
            "[QUALITY ALERT WRITE WARNING]",
            rendered,
        )
        self.assertIn(
            "OperationalError: unable to open database file",
            rendered,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

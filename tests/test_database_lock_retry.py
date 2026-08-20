import importlib.util
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parent.parent

PIPELINE_RUNNER_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "05_run_pipeline.py"
)


def load_pipeline_runner():
    spec = importlib.util.spec_from_file_location(
        "project_pipeline_runner",
        PIPELINE_RUNNER_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Unable to load production pipeline runner"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PIPELINE_RUNNER = load_pipeline_runner()


class DatabaseLockRetryTestCase(unittest.TestCase):

    def test_transient_database_lock_retries_then_succeeds(
        self,
    ) -> None:
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1

            if attempts["count"] == 1:
                raise sqlite3.OperationalError(
                    "database is locked"
                )

            return "SUCCESS"

        with (
            patch.object(
                PIPELINE_RUNNER.time,
                "sleep",
            ) as sleep_mock,
            patch.object(
                PIPELINE_RUNNER,
                "write_log",
            ) as log_mock,
        ):
            result = (
                PIPELINE_RUNNER
                .run_database_operation_with_retry(
                    operation_name=(
                        "START_PIPELINE_AUDIT"
                    ),
                    operation=operation,
                    run_id="test-run-transient",
                    max_attempts=2,
                    retry_delay_seconds=0.01,
                )
            )

        self.assertEqual(result, "SUCCESS")
        self.assertEqual(attempts["count"], 2)
        sleep_mock.assert_called_once_with(0.01)

        self.assertTrue(
            any(
                "DB RETRY SCHEDULED"
                in str(call)
                for call in log_mock.call_args_list
            )
        )

    def test_persistent_database_lock_exhausts_retry(
        self,
    ) -> None:
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            raise sqlite3.OperationalError(
                "database is locked"
            )

        with (
            patch.object(
                PIPELINE_RUNNER.time,
                "sleep",
            ) as sleep_mock,
            patch.object(
                PIPELINE_RUNNER,
                "write_log",
            ) as log_mock,
        ):
            with self.assertRaises(
                sqlite3.OperationalError
            ):
                (
                    PIPELINE_RUNNER
                    .run_database_operation_with_retry(
                        operation_name=(
                            "START_PIPELINE_AUDIT"
                        ),
                        operation=operation,
                        run_id="test-run-exhausted",
                        max_attempts=2,
                        retry_delay_seconds=0.01,
                    )
                )

        self.assertEqual(attempts["count"], 2)
        sleep_mock.assert_called_once_with(0.01)

        self.assertTrue(
            any(
                "DB RETRY EXHAUSTED"
                in str(call)
                for call in log_mock.call_args_list
            )
        )

    def test_non_retryable_database_error_fails_immediately(
        self,
    ) -> None:
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            raise sqlite3.OperationalError(
                "no such table: pipeline_audit"
            )

        with (
            patch.object(
                PIPELINE_RUNNER.time,
                "sleep",
            ) as sleep_mock,
            patch.object(
                PIPELINE_RUNNER,
                "write_log",
            ),
        ):
            with self.assertRaises(
                sqlite3.OperationalError
            ):
                (
                    PIPELINE_RUNNER
                    .run_database_operation_with_retry(
                        operation_name=(
                            "START_PIPELINE_AUDIT"
                        ),
                        operation=operation,
                        run_id="test-run-non-retryable",
                        max_attempts=2,
                        retry_delay_seconds=0.01,
                    )
                )

        self.assertEqual(attempts["count"], 1)
        sleep_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()

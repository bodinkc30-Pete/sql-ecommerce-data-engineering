from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_RUNNER_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "05_run_pipeline.py"
)


def load_pipeline_runner():
    spec = spec_from_file_location(
        "pipeline_runner_recovery_contract",
        PIPELINE_RUNNER_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Unable to load scripts/05_run_pipeline.py"
        )

    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def create_audit_database(
    database_path: Path,
) -> None:
    connection = sqlite3.connect(database_path)

    try:
        connection.executescript(
            """
            CREATE TABLE pipeline_audit (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                pipeline_name TEXT NOT NULL,
                run_id TEXT NOT NULL,
                step_name TEXT NOT NULL,
                run_status TEXT NOT NULL,
                rows_processed INTEGER,
                rows_inserted INTEGER,
                rows_updated INTEGER,
                rows_rejected INTEGER,
                error_message TEXT,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                created_at TEXT,
                run_type TEXT NOT NULL,
                recovery_of_run_id TEXT,
                backfill_start_date TEXT,
                backfill_end_date TEXT
            );
            """
        )
    finally:
        connection.close()


def insert_audit_row(
    database_path: Path,
    *,
    pipeline_name: str,
    run_id: str,
    step_name: str,
    run_status: str,
) -> None:
    connection = sqlite3.connect(database_path)

    try:
        connection.execute(
            """
            INSERT INTO pipeline_audit (
                pipeline_name,
                run_id,
                step_name,
                run_status,
                rows_processed,
                rows_inserted,
                rows_updated,
                rows_rejected,
                error_message,
                started_at,
                completed_at,
                created_at,
                run_type,
                recovery_of_run_id,
                backfill_start_date,
                backfill_end_date
            )
            VALUES (
                ?,
                ?,
                ?,
                ?,
                0,
                0,
                0,
                0,
                NULL,
                '2026-08-20 08:00:00',
                '2026-08-20 08:00:01',
                '2026-08-20 08:00:00',
                'NORMAL',
                NULL,
                NULL,
                NULL
            );
            """,
            (
                pipeline_name,
                run_id,
                step_name,
                run_status,
            ),
        )
        connection.commit()
    finally:
        connection.close()


class RecoveryContractTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.pipeline_runner = load_pipeline_runner()

        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_directory.name)
            / "recovery_contract.db"
        )

        create_audit_database(
            self.database_path
        )

        self.database_path_patch = mock.patch.object(
            self.pipeline_runner,
            "DATABASE_PATH",
            self.database_path,
        )
        self.database_path_patch.start()

    def tearDown(self) -> None:
        self.database_path_patch.stop()
        self.temp_directory.cleanup()

    def test_failed_pipeline_total_is_valid_recovery_source(
        self,
    ) -> None:
        insert_audit_row(
            self.database_path,
            pipeline_name=self.pipeline_runner.PIPELINE_NAME,
            run_id="failed-top-level-run",
            step_name="PIPELINE_TOTAL",
            run_status="FAILED",
        )

        self.pipeline_runner.validate_recovery_source(
            "failed-top-level-run"
        )

    def test_success_pipeline_total_is_rejected(
        self,
    ) -> None:
        insert_audit_row(
            self.database_path,
            pipeline_name=self.pipeline_runner.PIPELINE_NAME,
            run_id="successful-top-level-run",
            step_name="PIPELINE_TOTAL",
            run_status="SUCCESS",
        )

        with self.assertRaisesRegex(
            ValueError,
            (
                "Recovery source must be a FAILED "
                "pipeline run"
            ),
        ):
            self.pipeline_runner.validate_recovery_source(
                "successful-top-level-run"
            )

    def test_unknown_run_id_is_rejected(
        self,
    ) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "Recovery source run_id does not exist",
        ):
            self.pipeline_runner.validate_recovery_source(
                "unknown-run"
            )

    def test_standalone_quality_failure_is_outside_recovery_scope(
        self,
    ) -> None:
        insert_audit_row(
            self.database_path,
            pipeline_name="ecommerce_quality_check_pipeline",
            run_id="standalone-quality-failure",
            step_name="07_freshness_checks",
            run_status="FAILED",
        )

        with self.assertRaisesRegex(
            ValueError,
            "Recovery source run_id does not exist",
        ):
            self.pipeline_runner.validate_recovery_source(
                "standalone-quality-failure"
            )


if __name__ == "__main__":
    unittest.main()

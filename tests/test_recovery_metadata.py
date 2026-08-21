from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import os
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
        "pipeline_runner_recovery_metadata",
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


def insert_pipeline_total_row(
    database_path: Path,
    *,
    pipeline_name: str,
    run_id: str,
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
                'PIPELINE_TOTAL',
                'RUNNING',
                0,
                0,
                0,
                0,
                NULL,
                '2026-08-21 10:00:00',
                NULL,
                '2026-08-21 10:00:00',
                'NORMAL',
                NULL,
                NULL,
                NULL
            );
            """,
            (
                pipeline_name,
                run_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def read_recovery_metadata(
    database_path: Path,
    run_id: str,
) -> tuple[str, str | None, str | None, str | None]:
    connection = sqlite3.connect(database_path)

    try:
        row = connection.execute(
            """
            SELECT
                run_type,
                recovery_of_run_id,
                backfill_start_date,
                backfill_end_date
            FROM pipeline_audit
            WHERE
                run_id = ?
                AND step_name = 'PIPELINE_TOTAL'
            ORDER BY audit_id DESC
            LIMIT 1;
            """,
            (run_id,),
        ).fetchone()
    finally:
        connection.close()

    if row is None:
        raise AssertionError(
            f"PIPELINE_TOTAL row not found for run_id={run_id}"
        )

    return (
        str(row[0]),
        row[1],
        row[2],
        row[3],
    )


class RecoveryMetadataTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.pipeline_runner = load_pipeline_runner()

        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_directory.name)
            / "recovery_metadata.db"
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

    def test_recovery_metadata_is_persisted_to_pipeline_audit(
        self,
    ) -> None:
        recovery_run_id = "recovery-run"
        failed_run_id = "failed-source-run"

        insert_pipeline_total_row(
            self.database_path,
            pipeline_name=self.pipeline_runner.PIPELINE_NAME,
            run_id=recovery_run_id,
        )

        self.pipeline_runner.stamp_pipeline_audit_metadata(
            run_id=recovery_run_id,
            run_type="RECOVERY",
            recovery_of_run_id=failed_run_id,
            backfill_start_date=None,
            backfill_end_date=None,
        )

        metadata = read_recovery_metadata(
            self.database_path,
            recovery_run_id,
        )

        self.assertEqual(
            metadata,
            (
                "RECOVERY",
                failed_run_id,
                None,
                None,
            ),
        )

    def test_recovery_metadata_is_propagated_to_child_environment(
        self,
    ) -> None:
        child_environment = (
            self.pipeline_runner.create_child_environment(
                run_id="recovery-run",
                run_type="RECOVERY",
                recovery_of_run_id="failed-source-run",
            )
        )

        self.assertEqual(
            child_environment["PIPELINE_RUN_ID"],
            "recovery-run",
        )
        self.assertEqual(
            child_environment["PIPELINE_RUN_TYPE"],
            "RECOVERY",
        )
        self.assertEqual(
            child_environment["PIPELINE_RECOVERY_OF_RUN_ID"],
            "failed-source-run",
        )

    def test_normal_run_removes_stale_recovery_environment(
        self,
    ) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "PIPELINE_RECOVERY_OF_RUN_ID":
                    "stale-recovery-source",
            },
            clear=False,
        ):
            child_environment = (
                self.pipeline_runner.create_child_environment(
                    run_id="normal-run",
                    run_type="NORMAL",
                    recovery_of_run_id=None,
                )
            )

        self.assertEqual(
            child_environment["PIPELINE_RUN_TYPE"],
            "NORMAL",
        )
        self.assertNotIn(
            "PIPELINE_RECOVERY_OF_RUN_ID",
            child_environment,
        )

    def test_recovery_metadata_does_not_set_backfill_dates(
        self,
    ) -> None:
        child_environment = (
            self.pipeline_runner.create_child_environment(
                run_id="recovery-run",
                run_type="RECOVERY",
                recovery_of_run_id="failed-source-run",
                backfill_start_date=None,
                backfill_end_date=None,
            )
        )

        self.assertNotIn(
            "PIPELINE_BACKFILL_START_DATE",
            child_environment,
        )
        self.assertNotIn(
            "PIPELINE_BACKFILL_END_DATE",
            child_environment,
        )


if __name__ == "__main__":
    unittest.main()

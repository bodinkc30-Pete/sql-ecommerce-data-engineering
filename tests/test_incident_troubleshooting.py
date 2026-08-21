from pathlib import Path
import sqlite3
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

QUERY_PATH = (
    PROJECT_ROOT
    / "queries"
    / "05_incident_troubleshooting.sql"
)


def load_statements() -> list[str]:
    sql_text = QUERY_PATH.read_text(
        encoding="utf-8",
    )

    return [
        statement.strip()
        for statement in sql_text.split(";")
        if statement.strip()
    ]


def create_test_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")

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
            run_type TEXT NOT NULL,
            recovery_of_run_id TEXT
        );

        CREATE TABLE pipeline_step_log (
            step_log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_name TEXT NOT NULL,
            run_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            step_name TEXT NOT NULL,
            script_name TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            status TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            duration_seconds REAL,
            rows_read INTEGER NOT NULL,
            rows_written INTEGER NOT NULL,
            rows_rejected INTEGER NOT NULL,
            error_type TEXT,
            error_message TEXT,
            sla_threshold_seconds REAL,
            sla_status TEXT NOT NULL
        );

        CREATE TABLE pipeline_sla_metrics (
            sla_metric_id INTEGER PRIMARY KEY AUTOINCREMENT,
            pipeline_name TEXT NOT NULL,
            run_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            step_run_status TEXT NOT NULL,
            duration_seconds REAL NOT NULL,
            sla_threshold_seconds REAL NOT NULL,
            sla_status TEXT NOT NULL,
            measured_at TEXT NOT NULL
        );

        CREATE TABLE pipeline_watermark (
            table_name TEXT PRIMARY KEY,
            last_loaded_at TEXT NOT NULL,
            updated_at TEXT
        );

        CREATE TABLE rejected_source_records (
            rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            dataset_name TEXT NOT NULL,
            source_file TEXT NOT NULL,
            source_row_number INTEGER NOT NULL,
            raw_record_json TEXT NOT NULL,
            rejected_column TEXT,
            rejected_value TEXT,
            rejection_reason TEXT NOT NULL,
            rejection_type TEXT NOT NULL,
            rejected_at TEXT NOT NULL
        );

        CREATE TABLE data_assets (
            asset_id INTEGER PRIMARY KEY,
            asset_name TEXT NOT NULL
        );

        CREATE TABLE lineage_edges (
            lineage_edge_id INTEGER PRIMARY KEY,
            upstream_asset_id INTEGER NOT NULL,
            downstream_asset_id INTEGER NOT NULL,
            transformation_type TEXT
        );

        CREATE TABLE lineage_run_events (
            lineage_run_event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            lineage_edge_id INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            execution_status TEXT NOT NULL,
            step_name TEXT,
            attempt_number INTEGER,
            recorded_at TEXT NOT NULL
        );
        """
    )

    connection.executemany(
        """
        INSERT INTO pipeline_watermark (
            table_name,
            last_loaded_at,
            updated_at
        )
        VALUES (?, ?, ?);
        """,
        [
            (
                "stg_orders",
                "2026-08-20 10:00:00",
                "2026-08-20 10:00:00",
            ),
            (
                "stg_payments",
                "2026-08-20 10:00:00",
                "2026-08-20 10:00:00",
            ),
        ],
    )

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
            run_type,
            recovery_of_run_id
        )
        VALUES (
            'ecommerce_quality_check_pipeline',
            'incident-run',
            '07_freshness_checks',
            'FAILED',
            27,
            0,
            0,
            1,
            'freshness SLA exceeded',
            '2026-08-20 08:59:11',
            '2026-08-20 08:59:11',
            'NORMAL',
            NULL
        );
        """
    )

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
            run_type,
            recovery_of_run_id
        )
        VALUES (
            'ecommerce_quality_check_pipeline',
            'declared-recovery-run',
            '07_freshness_checks',
            'SUCCESS',
            27,
            0,
            0,
            0,
            NULL,
            '2026-08-20 09:10:00',
            '2026-08-20 09:10:01',
            'RECOVERY',
            'incident-run'
        );
        """
    )

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
            run_type,
            recovery_of_run_id
        )
        VALUES (
            'ecommerce_quality_check_pipeline',
            'possible-recovery-run',
            '07_freshness_checks',
            'SUCCESS',
            27,
            0,
            0,
            0,
            NULL,
            '2026-08-20 09:20:00',
            '2026-08-20 09:20:01',
            'NORMAL',
            NULL
        );
        """
    )

    connection.commit()

    return connection


class IncidentTroubleshootingQueryTestCase(
    unittest.TestCase
):

    def test_query_pack_has_nine_read_only_statements(
        self,
    ) -> None:
        sql_text = QUERY_PATH.read_text(
            encoding="utf-8",
        )
        statements = load_statements()

        self.assertEqual(
            len(statements),
            9,
        )

        normalized_sql = (
            "\n" + sql_text.upper()
        )

        forbidden_tokens = (
            "\nINSERT ",
            "\nUPDATE ",
            "\nDELETE ",
            "\nDROP ",
            "\nCREATE ",
            "\nALTER ",
            "\nREPLACE ",
        )

        for token in forbidden_tokens:
            self.assertNotIn(
                token,
                normalized_sql,
            )

    def test_all_queries_execute_against_isolated_schema(
        self,
    ) -> None:
        connection = create_test_database()

        try:
            for statement in load_statements():
                connection.execute(
                    statement
                ).fetchall()
        finally:
            connection.close()

    def test_standalone_incident_uses_audit_fallback(
        self,
    ) -> None:
        connection = create_test_database()

        try:
            statements = load_statements()

            step_rows = connection.execute(
                statements[2]
            ).fetchall()

            self.assertEqual(
                len(step_rows),
                1,
            )
            self.assertEqual(
                step_rows[0][-1],
                "PIPELINE_AUDIT_FALLBACK",
            )
            self.assertEqual(
                step_rows[0][1],
                "07_freshness_checks",
            )
            self.assertEqual(
                step_rows[0][4],
                "FAILED",
            )

            sla_rows = connection.execute(
                statements[3]
            ).fetchall()

            self.assertEqual(
                len(sla_rows),
                1,
            )
            self.assertEqual(
                sla_rows[0][5],
                "NO_ORCHESTRATOR_SLA_TELEMETRY",
            )

            lineage_rows = connection.execute(
                statements[5]
            ).fetchall()

            self.assertEqual(
                len(lineage_rows),
                1,
            )
            self.assertEqual(
                lineage_rows[0][9],
                "NO_RUNTIME_LINEAGE_FOR_RUN",
            )
        finally:
            connection.close()

    def test_declared_and_possible_recovery_are_distinct(
        self,
    ) -> None:
        connection = create_test_database()

        try:
            recovery_rows = connection.execute(
                load_statements()[6]
            ).fetchall()

            recovery_linkage = {
                row[1]: row[6]
                for row in recovery_rows
            }

            self.assertEqual(
                recovery_linkage[
                    "declared-recovery-run"
                ],
                "DECLARED_RECOVERY",
            )
            self.assertEqual(
                recovery_linkage[
                    "possible-recovery-run"
                ],
                "POSSIBLE_RECOVERY_NOT_LINKED",
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

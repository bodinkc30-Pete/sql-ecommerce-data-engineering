import importlib.util
from pathlib import Path
import sqlite3
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

QUALITY_RUNNER_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "04_run_quality_checks.py"
)


def load_quality_runner():
    spec = importlib.util.spec_from_file_location(
        "project_quality_runner",
        QUALITY_RUNNER_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Unable to load production quality runner"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


QUALITY_RUNNER = load_quality_runner()


class FreshnessQualityGateTestCase(unittest.TestCase):

    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row

        self.connection.execute(
            """
            CREATE TABLE pipeline_watermark (
                table_name TEXT PRIMARY KEY,
                last_loaded_at TEXT,
                updated_at TEXT
            );
            """
        )

        self.config = QUALITY_RUNNER.read_pipeline_config()

        freshness_sql = QUALITY_RUNNER.read_sql_file(
            QUALITY_RUNNER.FRESHNESS_CHECK_FILE
        )

        self.rendered_freshness_sql = (
            QUALITY_RUNNER.render_quality_check_sql(
                QUALITY_RUNNER.FRESHNESS_CHECK_FILE,
                freshness_sql,
                self.config,
            )
        )

        (
            self.error_max_issue_count,
            self.error_max_issue_rate_percent,
        ) = QUALITY_RUNNER.get_threshold_config(
            self.config
        )

    def tearDown(self) -> None:
        self.connection.close()

    def seed_watermarks(
        self,
        target_last_loaded_at: str | None,
    ) -> None:
        fresh_timestamp = (
            self.connection.execute(
                """
                SELECT DATETIME('now', '-1 hour');
                """
            ).fetchone()[0]
        )

        expected_tables = [
            "stg_customers",
            "stg_products",
            "stg_orders",
            "stg_order_items",
            "stg_payments",
        ]

        for table_name in expected_tables:
            last_loaded_at = (
                target_last_loaded_at
                if table_name == "stg_orders"
                else fresh_timestamp
            )

            self.connection.execute(
                """
                INSERT INTO pipeline_watermark (
                    table_name,
                    last_loaded_at,
                    updated_at
                )
                VALUES (?, ?, CURRENT_TIMESTAMP);
                """,
                (
                    table_name,
                    last_loaded_at,
                ),
            )

        self.connection.commit()

    def run_freshness_query(self) -> list[sqlite3.Row]:
        return QUALITY_RUNNER.execute_check_queries(
            self.connection,
            self.rendered_freshness_sql,
        )

    def test_stale_orders_watermark_fails_quality_gate(
        self,
    ) -> None:
        stale_timestamp = (
            self.connection.execute(
                """
                SELECT DATETIME('now', '-49 hours');
                """
            ).fetchone()[0]
        )

        self.seed_watermarks(
            target_last_loaded_at=stale_timestamp
        )

        result_rows = self.run_freshness_query()

        self.assertEqual(len(result_rows), 1)

        stale_row = result_rows[0]

        self.assertEqual(
            stale_row["table_name"],
            "stg_orders",
        )
        self.assertEqual(
            stale_row["freshness_status"],
            "STALE_DATA",
        )
        self.assertGreater(
            float(stale_row["hours_since_last_load"]),
            24.0,
        )

        severity = QUALITY_RUNNER.classify_issue(
            "07_freshness_checks.sql",
            stale_row,
        )

        self.assertEqual(severity, "ERROR")

        evaluation = QUALITY_RUNNER.evaluate_quality_result(
            file_name="07_freshness_checks.sql",
            result_rows=result_rows,
            evaluated_rows=27,
            error_max_issue_count=(
                self.error_max_issue_count
            ),
            error_max_issue_rate_percent=(
                self.error_max_issue_rate_percent
            ),
        )

        self.assertEqual(
            evaluation["outcome"],
            "FAIL",
        )
        self.assertEqual(
            evaluation["error_count"],
            1,
        )
        self.assertAlmostEqual(
            evaluation["error_rate_percent"],
            100 / 27,
            places=4,
        )

    def test_fresh_orders_watermark_passes(
        self,
    ) -> None:
        fresh_timestamp = (
            self.connection.execute(
                """
                SELECT DATETIME('now', '-1 hour');
                """
            ).fetchone()[0]
        )

        self.seed_watermarks(
            target_last_loaded_at=fresh_timestamp
        )

        result_rows = self.run_freshness_query()

        self.assertEqual(result_rows, [])

        evaluation = QUALITY_RUNNER.evaluate_quality_result(
            file_name="07_freshness_checks.sql",
            result_rows=result_rows,
            evaluated_rows=27,
            error_max_issue_count=(
                self.error_max_issue_count
            ),
            error_max_issue_rate_percent=(
                self.error_max_issue_rate_percent
            ),
        )

        self.assertEqual(
            evaluation["outcome"],
            "PASS",
        )
        self.assertEqual(
            evaluation["critical_count"],
            0,
        )
        self.assertEqual(
            evaluation["error_count"],
            0,
        )

    def test_not_loaded_orders_is_critical(
        self,
    ) -> None:
        self.seed_watermarks(
            target_last_loaded_at="1900-01-01 00:00:00"
        )

        result_rows = self.run_freshness_query()

        self.assertEqual(len(result_rows), 1)

        not_loaded_row = result_rows[0]

        self.assertEqual(
            not_loaded_row["table_name"],
            "stg_orders",
        )
        self.assertEqual(
            not_loaded_row["freshness_status"],
            "NOT_LOADED",
        )

        severity = QUALITY_RUNNER.classify_issue(
            "07_freshness_checks.sql",
            not_loaded_row,
        )

        self.assertEqual(severity, "CRITICAL")

        evaluation = QUALITY_RUNNER.evaluate_quality_result(
            file_name="07_freshness_checks.sql",
            result_rows=result_rows,
            evaluated_rows=27,
            error_max_issue_count=(
                self.error_max_issue_count
            ),
            error_max_issue_rate_percent=(
                self.error_max_issue_rate_percent
            ),
        )

        self.assertEqual(
            evaluation["outcome"],
            "FAIL",
        )
        self.assertEqual(
            evaluation["critical_count"],
            1,
        )


if __name__ == "__main__":
    unittest.main()

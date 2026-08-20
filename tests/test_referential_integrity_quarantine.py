import importlib.util
from pathlib import Path
import sqlite3
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

STAGING_SCHEMA_PATH = (
    PROJECT_ROOT
    / "schema"
    / "01_create_staging_tables.sql"
)

CORE_SCHEMA_PATH = (
    PROJECT_ROOT
    / "schema"
    / "02_create_core_tables.sql"
)

TRANSFORMATION_RUNNER_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "03_run_transformations.py"
)

TRANSFORMATION_SQL_PATH = (
    PROJECT_ROOT
    / "transformations"
    / "06_incremental_load.sql"
)


def load_transformation_runner():
    spec = importlib.util.spec_from_file_location(
        "project_transformation_runner",
        TRANSFORMATION_RUNNER_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Unable to load production transformation runner"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TRANSFORMATION_RUNNER = load_transformation_runner()


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def create_test_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON;")

    connection.executescript(
        read_sql(STAGING_SCHEMA_PATH)
    )

    connection.executescript(
        read_sql(CORE_SCHEMA_PATH)
    )

    return connection


def render_incremental_sql() -> str:
    config = TRANSFORMATION_RUNNER.read_pipeline_config()

    lookback_minutes = (
        TRANSFORMATION_RUNNER
        .get_incremental_lookback_minutes(config)
    )

    future_tolerance_minutes = (
        TRANSFORMATION_RUNNER
        .get_watermark_future_tolerance_minutes(
            config
        )
    )

    sql_script = (
        TRANSFORMATION_RUNNER.read_sql_file(
            TRANSFORMATION_SQL_PATH
        )
    )

    return (
        TRANSFORMATION_RUNNER
        .render_transformation_sql(
            file_path=TRANSFORMATION_SQL_PATH,
            sql_script=sql_script,
            incremental_lookback_minutes=(
                lookback_minutes
            ),
            watermark_future_tolerance_minutes=(
                future_tolerance_minutes
            ),
        )
    )


def insert_customer(
    connection: sqlite3.Connection,
    customer_id: str = "1",
) -> None:
    connection.execute(
        """
        INSERT INTO stg_customers (
            customer_id,
            customer_name,
            email,
            city,
            signup_date,
            source_file,
            loaded_at
        )
        VALUES (
            ?,
            'Alice Example',
            'alice@example.com',
            'Bangkok',
            '2026-01-01',
            'customers.csv',
            CURRENT_TIMESTAMP
        );
        """,
        (customer_id,),
    )


def insert_order(
    connection: sqlite3.Connection,
    customer_id: str,
) -> None:
    connection.execute(
        """
        INSERT INTO stg_orders (
            order_id,
            customer_id,
            order_date,
            order_status,
            source_file,
            loaded_at
        )
        VALUES (
            '1001',
            ?,
            '2026-01-15',
            'COMPLETED',
            'orders.csv',
            CURRENT_TIMESTAMP
        );
        """,
        (customer_id,),
    )


class ReferentialIntegrityQuarantineTestCase(
    unittest.TestCase
):

    def test_orphan_order_is_quarantined_and_not_loaded(
        self,
    ) -> None:
        connection = create_test_database()

        try:
            insert_order(
                connection,
                customer_id="9999",
            )

            connection.executescript(
                render_incremental_sql()
            )

            core_order = connection.execute(
                """
                SELECT
                    order_id,
                    customer_id
                FROM orders
                WHERE order_id = 1001;
                """
            ).fetchone()

            self.assertIsNone(core_order)

            rejection = connection.execute(
                """
                SELECT
                    dataset_name,
                    source_file,
                    source_row_number,
                    rejected_column,
                    rejected_value,
                    rejection_type,
                    rejection_reason,
                    raw_record_json
                FROM rejected_source_records
                WHERE
                    dataset_name = 'orders'
                    AND rejection_type = (
                        'REFERENTIAL_INTEGRITY_FAILURE'
                    )
                ORDER BY rejection_id DESC
                LIMIT 1;
                """
            ).fetchone()

            self.assertIsNotNone(rejection)

            self.assertEqual(rejection[0], "orders")
            self.assertEqual(rejection[1], "orders.csv")
            self.assertEqual(rejection[2], 2)
            self.assertEqual(rejection[3], "customer_id")
            self.assertEqual(rejection[4], "9999")
            self.assertEqual(
                rejection[5],
                "REFERENTIAL_INTEGRITY_FAILURE",
            )
            self.assertEqual(
                rejection[6],
                (
                    "customer_id does not reference "
                    "an existing customer"
                ),
            )

            self.assertIn(
                '"order_id":"1001"',
                rejection[7],
            )
            self.assertIn(
                '"customer_id":"9999"',
                rejection[7],
            )
        finally:
            connection.close()

    def test_valid_order_loads_without_ri_rejection(
        self,
    ) -> None:
        connection = create_test_database()

        try:
            insert_customer(connection)
            insert_order(
                connection,
                customer_id="1",
            )

            connection.executescript(
                render_incremental_sql()
            )

            core_order = connection.execute(
                """
                SELECT
                    order_id,
                    customer_id
                FROM orders
                WHERE order_id = 1001;
                """
            ).fetchone()

            self.assertEqual(
                core_order,
                (1001, 1),
            )

            rejection_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM rejected_source_records
                WHERE
                    dataset_name = 'orders'
                    AND rejection_type = (
                        'REFERENTIAL_INTEGRITY_FAILURE'
                    );
                """
            ).fetchone()[0]

            self.assertEqual(
                rejection_count,
                0,
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

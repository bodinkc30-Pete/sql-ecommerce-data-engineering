from pathlib import Path
import sqlite3
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCHEMA_DIRECTORY = PROJECT_ROOT / "schema"

STAGING_SCHEMA_PATH = (
    SCHEMA_DIRECTORY
    / "01_create_staging_tables.sql"
)

CORE_SCHEMA_PATH = (
    SCHEMA_DIRECTORY
    / "02_create_core_tables.sql"
)

INDEX_SCHEMA_PATH = (
    SCHEMA_DIRECTORY
    / "03_create_indexes.sql"
)

TARGET_INDEX = "idx_orders_status_date"

TARGET_QUERY = """
SELECT
    order_date,
    COUNT(*) AS orders,
    SUM(order_total) AS revenue
FROM orders
WHERE order_status = 'COMPLETED'
GROUP BY order_date
ORDER BY order_date;
"""


class QueryPerformanceRegressionTestCase(
    unittest.TestCase
):

    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")

        for schema_path in (
            STAGING_SCHEMA_PATH,
            CORE_SCHEMA_PATH,
            INDEX_SCHEMA_PATH,
        ):
            sql_script = schema_path.read_text(
                encoding="utf-8"
            )
            self.connection.executescript(
                sql_script
            )

        self.connection.execute(
            """
            INSERT INTO customers (
                customer_id,
                customer_name,
                email,
                city,
                signup_date
            )
            VALUES (
                1,
                'Performance Test Customer',
                'performance@example.com',
                'Bangkok',
                '2026-01-01'
            );
            """
        )

        order_rows = []

        for order_id in range(1, 1001):
            status = (
                "COMPLETED"
                if order_id % 2 == 0
                else "PENDING"
            )

            day = (
                (order_id % 28)
                + 1
            )

            order_rows.append(
                (
                    order_id,
                    1,
                    f"2026-08-{day:02d}",
                    status,
                    float(order_id),
                )
            )

        self.connection.executemany(
            """
            INSERT INTO orders (
                order_id,
                customer_id,
                order_date,
                order_status,
                order_total
            )
            VALUES (?, ?, ?, ?, ?);
            """,
            order_rows,
        )

        self.connection.execute("ANALYZE;")
        self.connection.commit()

    def tearDown(self) -> None:
        self.connection.close()

    def get_query_plan_details(self) -> list[str]:
        rows = self.connection.execute(
            "EXPLAIN QUERY PLAN "
            + TARGET_QUERY
        ).fetchall()

        return [
            str(row[3])
            for row in rows
        ]

    def test_production_composite_index_definition(
        self,
    ) -> None:
        index_row = self.connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE
                type = 'index'
                AND name = ?;
            """,
            (TARGET_INDEX,),
        ).fetchone()

        self.assertIsNotNone(index_row)

        index_columns = self.connection.execute(
            f"PRAGMA index_info('{TARGET_INDEX}');"
        ).fetchall()

        column_names = [
            row[2]
            for row in index_columns
        ]

        self.assertEqual(
            column_names,
            [
                "order_status",
                "order_date",
            ],
        )

    def test_query_plan_uses_composite_index(
        self,
    ) -> None:
        plan_details = self.get_query_plan_details()

        joined_plan = " | ".join(plan_details)

        self.assertIn(
            TARGET_INDEX,
            joined_plan,
        )

        self.assertTrue(
            any(
                "SEARCH orders" in detail
                and TARGET_INDEX in detail
                and "order_status=?" in detail
                for detail in plan_details
            ),
            msg=(
                "Expected optimized SEARCH access path "
                f"using {TARGET_INDEX}; "
                f"actual plan: {joined_plan}"
            ),
        )

    def test_missing_composite_index_is_detectable(
        self,
    ) -> None:
        self.connection.execute(
            f"DROP INDEX {TARGET_INDEX};"
        )
        self.connection.execute("ANALYZE;")
        self.connection.commit()

        plan_details = self.get_query_plan_details()

        joined_plan = " | ".join(plan_details)

        self.assertNotIn(
            TARGET_INDEX,
            joined_plan,
        )

        remaining_index = self.connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE
                type = 'index'
                AND name = ?;
            """,
            (TARGET_INDEX,),
        ).fetchone()

        self.assertIsNone(remaining_index)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import re
import sqlite3
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VIEW_SQL_PATH = PROJECT_ROOT / "schema" / "04_create_views.sql"

TARGET_VIEWS = [
    "vw_daily_sales_summary",
    "vw_product_sales_summary",
    "vw_customer_order_summary",
    "vw_payment_summary",
    "vw_payment_reconciliation",
]


def _extract_view_sql(view_name: str) -> str:
    text = VIEW_SQL_PATH.read_text(encoding="utf-8")

    match = re.search(
        rf"CREATE\s+VIEW\s+{re.escape(view_name)}\s+AS\s+"
        rf"(.*?)(?=\n\s*CREATE\s+VIEW|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if match is None:
        raise AssertionError(
            f"View definition not found in {VIEW_SQL_PATH}: {view_name}"
        )

    return match.group(0).strip()


class BusinessServingCalculationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row

        self.conn.executescript(
            """
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                customer_name TEXT NOT NULL,
                email TEXT,
                city TEXT
            );

            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY,
                product_name TEXT NOT NULL,
                category TEXT,
                unit_price REAL NOT NULL,
                stock_quantity INTEGER NOT NULL
            );

            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER NOT NULL,
                order_date TEXT NOT NULL,
                order_status TEXT NOT NULL,
                order_total REAL NOT NULL
            );

            CREATE TABLE order_items (
                order_item_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                product_id INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                line_total REAL NOT NULL
            );

            CREATE TABLE payments (
                payment_id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL,
                payment_method TEXT NOT NULL,
                payment_status TEXT NOT NULL,
                payment_amount REAL NOT NULL,
                payment_date TEXT NOT NULL
            );
            """
        )

        for view_name in TARGET_VIEWS:
            self.conn.executescript(_extract_view_sql(view_name))

        self.conn.execute(
            """
            INSERT INTO customers (
                customer_id,
                customer_name,
                email,
                city
            )
            VALUES (1, 'Test Customer', 'test@example.com', 'Bangkok')
            """
        )

        self.conn.executemany(
            """
            INSERT INTO products (
                product_id,
                product_name,
                category,
                unit_price,
                stock_quantity
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (101, "Product A", "Category A", 60.0, 10),
                (102, "Product B", "Category B", 40.0, 20),
            ],
        )

        self.conn.executemany(
            """
            INSERT INTO orders (
                order_id,
                customer_id,
                order_date,
                order_status,
                order_total
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1001, 1, "2026-01-15", "COMPLETED", 100.0),
                (1002, 1, "2026-01-15", "COMPLETED", 200.0),
            ],
        )

        self.conn.executemany(
            """
            INSERT INTO order_items (
                order_item_id,
                order_id,
                product_id,
                quantity,
                line_total
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (1, 1001, 101, 1, 60.0),
                (2, 1001, 102, 1, 40.0),
                (3, 1002, 101, 2, 200.0),
            ],
        )

        self.conn.executemany(
            """
            INSERT INTO payments (
                payment_id,
                order_id,
                payment_method,
                payment_status,
                payment_amount,
                payment_date
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (1, 1001, "CARD", "PAID", 100.0, "2026-01-15"),
                (2, 1002, "CARD", "PAID", 200.0, "2026-01-15"),
            ],
        )

        self.conn.commit()

    def tearDown(self) -> None:
        self.conn.close()

    def test_daily_sales_summary_uses_order_grain_for_aov(self) -> None:
        row = self.conn.execute(
            """
            SELECT *
            FROM vw_daily_sales_summary
            WHERE order_date = '2026-01-15'
            """
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["total_orders"], 2)
        self.assertEqual(row["unique_customers"], 1)
        self.assertEqual(row["units_sold"], 4)
        self.assertAlmostEqual(row["total_revenue"], 300.0, places=2)
        self.assertAlmostEqual(
            row["average_order_value"],
            150.0,
            places=2,
            msg=(
                "Daily AOV must average one value per order. "
                "Joining orders directly to multiple order_items must not "
                "weight orders with more line items more heavily."
            ),
        )

    def test_customer_summary_uses_order_grain_for_aov(self) -> None:
        row = self.conn.execute(
            """
            SELECT *
            FROM vw_customer_order_summary
            WHERE customer_id = 1
            """
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["total_orders"], 2)
        self.assertAlmostEqual(row["total_spent"], 300.0, places=2)
        self.assertAlmostEqual(
            row["average_order_value"],
            150.0,
            places=2,
            msg=(
                "Customer AOV must average one value per order, not one "
                "value per joined order-item row."
            ),
        )
        self.assertEqual(row["first_order_date"], "2026-01-15")
        self.assertEqual(row["latest_order_date"], "2026-01-15")

    def test_product_sales_summary_aggregates_product_metrics(self) -> None:
        row = self.conn.execute(
            """
            SELECT *
            FROM vw_product_sales_summary
            WHERE product_id = 101
            """
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["total_orders"], 2)
        self.assertEqual(row["units_sold"], 3)
        self.assertAlmostEqual(row["total_revenue"], 260.0, places=2)

    def test_payment_summary_aggregates_paid_card_metrics(self) -> None:
        row = self.conn.execute(
            """
            SELECT *
            FROM vw_payment_summary
            WHERE payment_method = 'CARD'
              AND payment_status = 'PAID'
            """
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["total_payments"], 2)
        self.assertAlmostEqual(row["total_payment_amount"], 300.0, places=2)
        self.assertAlmostEqual(row["average_payment_amount"], 150.0, places=2)
        self.assertEqual(row["first_payment_date"], "2026-01-15")
        self.assertEqual(row["latest_payment_date"], "2026-01-15")

    def test_payment_reconciliation_matches_valid_orders(self) -> None:
        rows = self.conn.execute(
            """
            SELECT
                order_id,
                stored_order_total,
                calculated_order_total,
                paid_amount,
                order_total_difference,
                payment_difference,
                reconciliation_status
            FROM vw_payment_reconciliation
            ORDER BY order_id
            """
        ).fetchall()

        self.assertEqual(len(rows), 2)

        for row in rows:
            self.assertAlmostEqual(
                row["stored_order_total"],
                row["calculated_order_total"],
                places=2,
            )
            self.assertAlmostEqual(
                row["stored_order_total"],
                row["paid_amount"],
                places=2,
            )
            self.assertAlmostEqual(row["order_total_difference"], 0.0, places=2)
            self.assertAlmostEqual(row["payment_difference"], 0.0, places=2)
            self.assertEqual(row["reconciliation_status"], "MATCHED")


if __name__ == "__main__":
    unittest.main()

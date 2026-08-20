from pathlib import Path
import sqlite3
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

INCREMENTAL_SQL_PATH = (
    PROJECT_ROOT
    / "transformations"
    / "06_incremental_load.sql"
)


def extract_payment_quarantine_sql() -> str:
    sql_text = INCREMENTAL_SQL_PATH.read_text(
        encoding="utf-8",
    )

    payment_quarantine_statements = []

    for raw_statement in sql_text.split(";"):
        statement = raw_statement.strip()

        if not statement:
            continue

        normalized_statement = (
            " ".join(
                statement.lower().split()
            )
        )

        is_payment_quarantine = all(
            marker in normalized_statement
            for marker in (
                "insert into rejected_source_records",
                "stg_payments",
                "payment_amount",
                "invalid_data_type",
            )
        )

        if is_payment_quarantine:
            payment_quarantine_statements.append(
                statement + ";"
            )

    if len(payment_quarantine_statements) != 1:
        raise AssertionError(
            "Expected exactly one payment quarantine "
            "statement in 06_incremental_load.sql, "
            "found "
            f"{len(payment_quarantine_statements)}"
        )

    quarantine_sql = (
        payment_quarantine_statements[0]
        .replace(
            "__INCREMENTAL_LOOKBACK_MINUTES__",
            "10",
        )
        .replace(
            "__WATERMARK_FUTURE_TOLERANCE_MINUTES__",
            "5",
        )
    )

    return quarantine_sql


def create_test_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")

    connection.executescript(
        """
        CREATE TABLE pipeline_watermark (
            table_name TEXT PRIMARY KEY,
            last_loaded_at TEXT NOT NULL
        );

        CREATE TABLE stg_payments (
            payment_id TEXT,
            order_id TEXT,
            payment_date TEXT,
            payment_method TEXT,
            payment_amount TEXT,
            payment_status TEXT,
            source_file TEXT,
            loaded_at TEXT
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
        """
    )

    connection.execute(
        """
        INSERT INTO pipeline_watermark (
            table_name,
            last_loaded_at
        )
        VALUES (
            'stg_payments',
            '1900-01-01 00:00:00'
        );
        """
    )

    return connection


class InvalidPaymentQuarantineTestCase(unittest.TestCase):

    def test_extraction_is_scoped_to_payment_quarantine(
        self,
    ) -> None:
        quarantine_sql = (
            extract_payment_quarantine_sql()
        )

        normalized_sql = (
            quarantine_sql.lower()
        )

        self.assertIn(
            "stg_payments",
            normalized_sql,
        )
        self.assertIn(
            "payment_amount",
            normalized_sql,
        )
        self.assertIn(
            "invalid_data_type",
            normalized_sql,
        )
        self.assertNotIn(
            "stg_orders",
            normalized_sql,
        )

    def test_invalid_payment_amount_is_quarantined(
        self,
    ) -> None:
        connection = create_test_database()

        try:
            connection.execute(
                """
                INSERT INTO stg_payments (
                    payment_id,
                    order_id,
                    payment_date,
                    payment_method,
                    payment_amount,
                    payment_status,
                    source_file,
                    loaded_at
                )
                VALUES (
                    '9001',
                    '1001',
                    '2026-01-15',
                    'CREDIT_CARD',
                    'ABC',
                    'PAID',
                    'payments.csv',
                    CURRENT_TIMESTAMP
                );
                """
            )

            connection.executescript(
                extract_payment_quarantine_sql()
            )

            rejected_row = connection.execute(
                """
                SELECT
                    dataset_name,
                    source_file,
                    source_row_number,
                    rejected_column,
                    rejected_value,
                    rejection_type,
                    rejection_reason
                FROM rejected_source_records;
                """
            ).fetchone()

            self.assertEqual(
                rejected_row,
                (
                    "payments",
                    "payments.csv",
                    2,
                    "payment_amount",
                    "ABC",
                    "INVALID_DATA_TYPE",
                    (
                        "payment_amount must be a "
                        "non-negative numeric value"
                    ),
                ),
            )
        finally:
            connection.close()

    def test_valid_payment_amount_is_not_quarantined(
        self,
    ) -> None:
        connection = create_test_database()

        try:
            connection.execute(
                """
                INSERT INTO stg_payments (
                    payment_id,
                    order_id,
                    payment_date,
                    payment_method,
                    payment_amount,
                    payment_status,
                    source_file,
                    loaded_at
                )
                VALUES (
                    '9001',
                    '1001',
                    '2026-01-15',
                    'CREDIT_CARD',
                    '4280.50',
                    'PAID',
                    'payments.csv',
                    CURRENT_TIMESTAMP
                );
                """
            )

            connection.executescript(
                extract_payment_quarantine_sql()
            )

            rejected_count = connection.execute(
                """
                SELECT COUNT(*)
                FROM rejected_source_records;
                """
            ).fetchone()[0]

            self.assertEqual(
                rejected_count,
                0,
            )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

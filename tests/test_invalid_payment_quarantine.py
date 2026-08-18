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

    start_marker = "INSERT INTO rejected_source_records"
    end_marker = "WITH incremental_payments AS"

    start_index = sql_text.index(start_marker)
    end_index = sql_text.index(
        end_marker,
        start_index,
    )

    quarantine_sql = sql_text[
        start_index:end_index
    ].strip()

    quarantine_sql = quarantine_sql.replace(
        "__INCREMENTAL_LOOKBACK_MINUTES__",
        "10",
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

from pathlib import Path
import sqlite3
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)


EXPECTED_TABLES = {
    "stg_customers",
    "stg_products",
    "stg_orders",
    "stg_order_items",
    "stg_payments",
    "stg_influencer_payments",
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
    "campaigns",
    "influencers",
    "influencer_payments",
    "rejected_influencer_records",
    "pipeline_audit",
}


EXPECTED_VIEWS = {
    "vw_customer_order_summary",
    "vw_product_sales_summary",
    "vw_daily_sales_summary",
    "vw_payment_reconciliation",
    "vw_data_quality_summary",
    "vw_pipeline_run_summary",
    "vw_influencer_payment_details",
    "vw_campaign_payment_summary",
    "vw_influencer_payment_summary",
    "vw_payment_status_summary",
    "vw_rejected_influencer_summary",
}


EXPECTED_COLUMNS = {
    "stg_influencer_payments": {
        "staging_row_id",
        "campaign_name",
        "source_section",
        "sequence_number",
        "influencer_handle",
        "fee_amount",
        "post_date_text",
        "bank_account_hash",
        "payment_round_text",
        "payment_status",
        "contact_phone_hash",
        "account_name_masked",
        "notes_sanitized",
        "source_file",
        "source_sheet",
        "source_row_number",
        "loaded_at",
    },
    "campaigns": {
        "campaign_id",
        "campaign_name",
        "source_section",
        "created_at",
        "updated_at",
    },
    "influencers": {
        "influencer_id",
        "influencer_handle",
        "bank_account_hash",
        "contact_phone_hash",
        "account_name_masked",
        "created_at",
        "updated_at",
    },
    "influencer_payments": {
        "influencer_payment_id",
        "campaign_id",
        "influencer_id",
        "source_sequence",
        "fee_amount",
        "post_date",
        "payment_round_date",
        "payment_status",
        "notes_sanitized",
        "source_file",
        "source_sheet",
        "source_row_number",
        "record_hash",
        "created_at",
        "updated_at",
    },
    "rejected_influencer_records": {
        "rejection_id",
        "campaign_name",
        "source_section",
        "sequence_number",
        "influencer_handle",
        "fee_amount_text",
        "post_date_text",
        "payment_round_text",
        "payment_status_text",
        "rejection_reason",
        "source_file",
        "source_sheet",
        "source_row_number",
        "rejected_at",
    },
}


EXPECTED_FOREIGN_KEYS = {
    "influencer_payments": {
        ("campaign_id", "campaigns", "campaign_id"),
        ("influencer_id", "influencers", "influencer_id"),
    },
}


EXPECTED_INDEXES = {
    "idx_campaigns_campaign_name",
    "idx_campaigns_source_section",
    "idx_influencers_handle",
    "idx_influencers_bank_account_hash",
    "idx_influencers_contact_phone_hash",
    "idx_influencer_payments_campaign_id",
    "idx_influencer_payments_influencer_id",
    "idx_influencer_payments_payment_status",
    "idx_influencer_payments_post_date",
    "idx_influencer_payments_payment_round_date",
    "idx_influencer_payments_source_location",
    "idx_rejected_influencer_source_location",
    "idx_rejected_influencer_rejected_at",
}


class SchemaTestCase(unittest.TestCase):
    connection: sqlite3.Connection

    @classmethod
    def setUpClass(cls) -> None:
        if not DATABASE_PATH.exists():
            raise FileNotFoundError(
                "ยังไม่พบฐานข้อมูล กรุณารัน "
                "scripts/01_setup_database.py ก่อน"
            )

        cls.connection = sqlite3.connect(
            DATABASE_PATH
        )

        cls.connection.row_factory = sqlite3.Row

        cls.connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def get_database_objects(
        self,
        object_type: str,
    ) -> set[str]:
        cursor = self.connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = ?
              AND name NOT LIKE 'sqlite_%';
            """,
            (object_type,),
        )

        return {
            row["name"]
            for row in cursor.fetchall()
        }

    def get_table_columns(
        self,
        table_name: str,
    ) -> set[str]:
        cursor = self.connection.execute(
            f"PRAGMA table_info({table_name});"
        )

        return {
            row["name"]
            for row in cursor.fetchall()
        }

    def get_foreign_keys(
        self,
        table_name: str,
    ) -> set[tuple[str, str, str]]:
        cursor = self.connection.execute(
            f"PRAGMA foreign_key_list({table_name});"
        )

        return {
            (
                row["from"],
                row["table"],
                row["to"],
            )
            for row in cursor.fetchall()
        }

    def test_expected_tables_exist(
        self,
    ) -> None:
        actual_tables = self.get_database_objects(
            "table"
        )

        missing_tables = (
            EXPECTED_TABLES - actual_tables
        )

        self.assertEqual(
            missing_tables,
            set(),
            (
                "ไม่พบตารางที่ต้องมี: "
                f"{sorted(missing_tables)}"
            ),
        )

    def test_expected_views_exist(
        self,
    ) -> None:
        actual_views = self.get_database_objects(
            "view"
        )

        missing_views = (
            EXPECTED_VIEWS - actual_views
        )

        self.assertEqual(
            missing_views,
            set(),
            (
                "ไม่พบ View ที่ต้องมี: "
                f"{sorted(missing_views)}"
            ),
        )

    def test_pawchoice_table_columns(
        self,
    ) -> None:
        for table_name, expected_columns in (
            EXPECTED_COLUMNS.items()
        ):
            with self.subTest(
                table_name=table_name
            ):
                actual_columns = (
                    self.get_table_columns(
                        table_name
                    )
                )

                missing_columns = (
                    expected_columns
                    - actual_columns
                )

                self.assertEqual(
                    missing_columns,
                    set(),
                    (
                        f"ตาราง {table_name} "
                        "ขาดคอลัมน์: "
                        f"{sorted(missing_columns)}"
                    ),
                )

    def test_pawchoice_foreign_keys(
        self,
    ) -> None:
        for table_name, expected_keys in (
            EXPECTED_FOREIGN_KEYS.items()
        ):
            with self.subTest(
                table_name=table_name
            ):
                actual_keys = (
                    self.get_foreign_keys(
                        table_name
                    )
                )

                missing_keys = (
                    expected_keys
                    - actual_keys
                )

                self.assertEqual(
                    missing_keys,
                    set(),
                    (
                        f"ตาราง {table_name} "
                        "ขาด Foreign Key: "
                        f"{sorted(missing_keys)}"
                    ),
                )

    def test_expected_indexes_exist(
        self,
    ) -> None:
        actual_indexes = (
            self.get_database_objects(
                "index"
            )
        )

        missing_indexes = (
            EXPECTED_INDEXES
            - actual_indexes
        )

        self.assertEqual(
            missing_indexes,
            set(),
            (
                "ไม่พบ Index ที่ต้องมี: "
                f"{sorted(missing_indexes)}"
            ),
        )

    def test_foreign_keys_are_enabled(
        self,
    ) -> None:
        cursor = self.connection.execute(
            "PRAGMA foreign_keys;"
        )

        foreign_keys_enabled = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            foreign_keys_enabled,
            1,
            "SQLite Foreign Key ยังไม่ถูกเปิดใช้งาน",
        )

    def test_database_integrity(
        self,
    ) -> None:
        cursor = self.connection.execute(
            "PRAGMA integrity_check;"
        )

        result = cursor.fetchone()[0]

        self.assertEqual(
            result,
            "ok",
            (
                "SQLite ตรวจพบปัญหา "
                f"ในฐานข้อมูล: {result}"
            ),
        )


def main() -> None:
    test_suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        SchemaTestCase
    )

    test_runner = unittest.TextTestRunner(
        verbosity=2
    )

    test_result = test_runner.run(
        test_suite
    )

    if not test_result.wasSuccessful():
        sys.exit(1)


if __name__ == "__main__":
    main()
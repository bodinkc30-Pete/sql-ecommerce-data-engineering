from pathlib import Path
import json
import sqlite3
import sys
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)

QUALITY_CHECK_DIRECTORY = (
    PROJECT_ROOT
    / "quality_checks"
)


EXPECTED_QUALITY_CHECK_FILES = {
    "01_null_checks.sql",
    "02_duplicate_checks.sql",
    "03_referential_integrity.sql",
    "04_reconciliation_checks.sql",
    "05_business_rule_checks.sql",
    "06_influencer_payment_checks.sql",
}


EXPECTED_INFLUENCER_CHECK_COLUMNS = {
    "check_name",
    "table_name",
    "record_identifier",
    "invalid_value",
    "issue_description",
}


class QualityCheckTestCase(unittest.TestCase):
    connection: sqlite3.Connection

    @classmethod
    def setUpClass(cls) -> None:
        if not DATABASE_PATH.exists():
            raise FileNotFoundError(
                "ยังไม่พบฐานข้อมูล กรุณารัน Pipeline "
                "ก่อนรัน Quality Check Tests"
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

    def read_sql_file(
        self,
        file_name: str,
    ) -> str:
        file_path = (
            QUALITY_CHECK_DIRECTORY
            / file_name
        )

        if not file_path.exists():
            raise FileNotFoundError(
                f"ไม่พบไฟล์ Quality Check: "
                f"{file_path}"
            )

        sql_script = file_path.read_text(
            encoding="utf-8"
        )

        config_path = (
            PROJECT_ROOT
            / "config"
            / "pipeline_config.json"
        )

        config = json.loads(
            config_path.read_text(
                encoding="utf-8"
            )
        )

        quality_config = config.get(
            "quality",
            {}
        )

        amount_tolerance = float(
            quality_config.get(
                "amount_tolerance",
                0.01,
            )
        )

        allowed_payment_statuses = (
            quality_config.get(
                "allowed_payment_statuses",
                [
                    "PENDING",
                    "PAID",
                    "FAILED",
                    "REFUNDED",
                    "CANCELLED",
                ],
            )
        )

        allowed_payment_methods = (
            quality_config.get(
                "allowed_payment_methods",
                [
                    "CREDIT_CARD",
                    "DEBIT_CARD",
                    "BANK_TRANSFER",
                    "E_WALLET",
                    "CASH",
                ],
            )
        )

        allowed_order_statuses = (
            quality_config.get(
                "allowed_order_statuses",
                [
                    "PENDING",
                    "PROCESSING",
                    "COMPLETED",
                    "CANCELLED",
                    "REFUNDED",
                ],
            )
        )

        allowed_influencer_payment_statuses = (
            quality_config.get(
                "allowed_influencer_payment_statuses",
                [
                    "PAID",
                    "UNPAID",
                    "CANCELLED",
                ],
            )
        )

        def sql_string_list(
            values: list[str],
        ) -> str:
            return ", ".join(
                "'" + str(value).replace(
                    "'",
                    "''",
                ) + "'"
                for value in values
            )

        replacements = {
            "__AMOUNT_TOLERANCE__": str(
                amount_tolerance
            ),
            "__ALLOWED_ORDER_STATUSES__": (
                sql_string_list(
                    allowed_order_statuses
                )
            ),
            "__ALLOWED_PAYMENT_METHODS__": (
                sql_string_list(
                    allowed_payment_methods
                )
            ),
            "__ALLOWED_PAYMENT_STATUSES__": (
                sql_string_list(
                    allowed_payment_statuses
                )
            ),
            "__ALLOWED_INFLUENCER_PAYMENT_STATUSES__": (
                sql_string_list(
                    allowed_influencer_payment_statuses
                )
            ),
        }

        for placeholder, replacement in (
            replacements.items()
        ):
            sql_script = sql_script.replace(
                placeholder,
                replacement,
            )

        unresolved_placeholders = [
            token
            for token in (
                "__AMOUNT_TOLERANCE__",
                "__ALLOWED_ORDER_STATUSES__",
                "__ALLOWED_PAYMENT_METHODS__",
                "__ALLOWED_PAYMENT_STATUSES__",
                "__ALLOWED_INFLUENCER_PAYMENT_STATUSES__",
            )
            if token in sql_script
        ]

        if unresolved_placeholders:
            raise ValueError(
                "Quality Check SQL ยังมี placeholder "
                "ที่ไม่ได้แทนค่า: "
                f"{unresolved_placeholders}"
            )

        return sql_script

    def execute_sql_script(
        self,
        sql_script: str,
    ) -> list[sqlite3.Row]:
        result_rows = []

        statements = [
            statement.strip()
            for statement in sql_script.split(";")
            if statement.strip()
        ]

        for statement in statements:
            cursor = self.connection.execute(
                statement
            )

            if cursor.description is not None:
                result_rows.extend(
                    cursor.fetchall()
                )

        return result_rows

    def execute_quality_check(
        self,
        file_name: str,
    ) -> list[sqlite3.Row]:
        sql_script = self.read_sql_file(
            file_name
        )

        return self.execute_sql_script(
            sql_script
        )

    def table_exists(
        self,
        table_name: str,
    ) -> bool:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE
                type = 'table'
                AND name = ?;
            """,
            (table_name,),
        )

        return cursor.fetchone()[0] == 1

    def test_all_quality_check_files_exist(
        self,
    ) -> None:
        actual_files = {
            file_path.name
            for file_path
            in QUALITY_CHECK_DIRECTORY.glob(
                "*.sql"
            )
        }

        missing_files = (
            EXPECTED_QUALITY_CHECK_FILES
            - actual_files
        )

        self.assertEqual(
            missing_files,
            set(),
            (
                "ไม่พบไฟล์ Quality Check: "
                f"{sorted(missing_files)}"
            ),
        )

    def test_null_check_executes(
        self,
    ) -> None:
        result_rows = self.execute_quality_check(
            "01_null_checks.sql"
        )

        self.assertIsInstance(
            result_rows,
            list,
        )

        for row in result_rows:
            self.assertIn(
                "table_name",
                row.keys(),
            )

            self.assertIn(
                "column_name",
                row.keys(),
            )

            self.assertIn(
                "null_count",
                row.keys(),
            )

            self.assertGreater(
                row["null_count"],
                0,
                (
                    "Null Check ควรแสดงเฉพาะ "
                    "คอลัมน์ที่พบปัญหา"
                ),
            )

    def test_duplicate_check_executes(
        self,
    ) -> None:
        result_rows = self.execute_quality_check(
            "02_duplicate_checks.sql"
        )

        self.assertIsInstance(
            result_rows,
            list,
        )

        for row in result_rows:
            self.assertIn(
                "table_name",
                row.keys(),
            )

            self.assertIn(
                "duplicate_key",
                row.keys(),
            )

            self.assertIn(
                "duplicate_value",
                row.keys(),
            )

            self.assertIn(
                "duplicate_count",
                row.keys(),
            )

            self.assertGreater(
                row["duplicate_count"],
                1,
                (
                    "Duplicate Check ควรแสดง "
                    "เฉพาะค่าที่ซ้ำมากกว่า 1 ครั้ง"
                ),
            )

    def test_referential_integrity_executes(
        self,
    ) -> None:
        result_rows = self.execute_quality_check(
            "03_referential_integrity.sql"
        )

        self.assertIsInstance(
            result_rows,
            list,
        )

        for row in result_rows:
            self.assertIn(
                "child_table",
                row.keys(),
            )

            self.assertIn(
                "foreign_key_column",
                row.keys(),
            )

            self.assertIn(
                "missing_reference_value",
                row.keys(),
            )

            self.assertIn(
                "affected_row_count",
                row.keys(),
            )

            self.assertGreater(
                row["affected_row_count"],
                0,
            )

    def test_reconciliation_check_executes(
        self,
    ) -> None:
        result_rows = self.execute_quality_check(
            "04_reconciliation_checks.sql"
        )

        self.assertIsInstance(
            result_rows,
            list,
        )

        for row in result_rows:
            self.assertGreater(
                len(row.keys()),
                0,
                (
                    "Reconciliation Check "
                    "ต้องมีคอลัมน์ผลลัพธ์"
                ),
            )

    def test_business_rule_check_executes(
        self,
    ) -> None:
        result_rows = self.execute_quality_check(
            "05_business_rule_checks.sql"
        )

        self.assertIsInstance(
            result_rows,
            list,
        )

        for row in result_rows:
            self.assertGreater(
                len(row.keys()),
                0,
                (
                    "Business Rule Check "
                    "ต้องมีคอลัมน์ผลลัพธ์"
                ),
            )

    def test_influencer_quality_check_executes(
        self,
    ) -> None:
        result_rows = self.execute_quality_check(
            "06_influencer_payment_checks.sql"
        )

        self.assertIsInstance(
            result_rows,
            list,
        )

        for row in result_rows:
            actual_columns = set(
                row.keys()
            )

            missing_columns = (
                EXPECTED_INFLUENCER_CHECK_COLUMNS
                - actual_columns
            )

            self.assertEqual(
                missing_columns,
                set(),
                (
                    "ผลลัพธ์ Influencer Quality Check "
                    "ขาดคอลัมน์: "
                    f"{sorted(missing_columns)}"
                ),
            )

    def test_influencer_payment_statuses(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM influencer_payments
            WHERE payment_status NOT IN (
                'PAID',
                'UNPAID',
                'CANCELLED'
            );
            """
        )

        invalid_status_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            invalid_status_count,
            0,
            (
                "พบ payment_status ที่ไม่อยู่ใน "
                "PAID, UNPAID หรือ CANCELLED"
            ),
        )

    def test_influencer_fee_amounts(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM influencer_payments
            WHERE fee_amount < 0;
            """
        )

        negative_amount_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            negative_amount_count,
            0,
            "พบค่าจ้าง Influencer ติดลบ",
        )

    def test_cancelled_amounts_are_zero(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM influencer_payments
            WHERE
                payment_status = 'CANCELLED'
                AND fee_amount <> 0;
            """
        )

        invalid_cancelled_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            invalid_cancelled_count,
            0,
            (
                "พบรายการ CANCELLED "
                "ที่มี fee_amount ไม่เท่ากับ 0"
            ),
        )

    def test_influencer_payment_references(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM influencer_payments AS ip
            LEFT JOIN campaigns AS c
                ON ip.campaign_id = c.campaign_id
            LEFT JOIN influencers AS i
                ON ip.influencer_id =
                    i.influencer_id
            WHERE
                c.campaign_id IS NULL
                OR i.influencer_id IS NULL;
            """
        )

        missing_reference_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            missing_reference_count,
            0,
            (
                "พบรายการ Influencer Payment "
                "ที่ไม่มี Campaign หรือ Influencer "
                "อ้างอิง"
            ),
        )

    def test_influencer_record_hashes(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM influencer_payments
            WHERE
                record_hash IS NULL
                OR TRIM(record_hash) = '';
            """
        )

        missing_hash_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            missing_hash_count,
            0,
            (
                "พบรายการ Influencer Payment "
                "ที่ไม่มี record_hash"
            ),
        )

    def test_influencer_record_hashes_are_unique(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    record_hash
                FROM influencer_payments
                GROUP BY record_hash
                HAVING COUNT(*) > 1
            );
            """
        )

        duplicate_hash_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            duplicate_hash_count,
            0,
            "พบ record_hash ซ้ำ",
        )

    def test_pii_hash_lengths(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM influencers
            WHERE
                (
                    bank_account_hash IS NOT NULL
                    AND LENGTH(
                        bank_account_hash
                    ) <> 64
                )
                OR
                (
                    contact_phone_hash IS NOT NULL
                    AND LENGTH(
                        contact_phone_hash
                    ) <> 64
                );
            """
        )

        invalid_hash_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            invalid_hash_count,
            0,
            (
                "พบ Bank Account Hash หรือ "
                "Phone Hash ที่ไม่ใช่ SHA-256"
            ),
        )

    def test_account_names_are_masked(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM influencers
            WHERE
                account_name_masked IS NOT NULL
                AND TRIM(
                    account_name_masked
                ) <> ''
                AND account_name_masked
                    NOT LIKE '%*%';
            """
        )

        unmasked_name_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            unmasked_name_count,
            0,
            "พบชื่อบัญชีที่ยังไม่ได้ Mask",
        )

    def test_rejected_records_have_reasons(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM rejected_influencer_records
            WHERE
                rejection_reason IS NULL
                OR TRIM(
                    rejection_reason
                ) = '';
            """
        )

        missing_reason_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            missing_reason_count,
            0,
            (
                "พบข้อมูล Reject "
                "ที่ไม่มี rejection_reason"
            ),
        )

    def test_rejected_records_have_lineage(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM rejected_influencer_records
            WHERE
                source_file IS NULL
                OR TRIM(source_file) = ''
                OR source_sheet IS NULL
                OR TRIM(source_sheet) = ''
                OR source_row_number IS NULL;
            """
        )

        missing_lineage_count = (
            cursor.fetchone()[0]
        )

        self.assertEqual(
            missing_lineage_count,
            0,
            (
                "พบข้อมูล Reject ที่ไม่มี "
                "Data Lineage ครบถ้วน"
            ),
        )

    def test_quality_check_audit_table_exists(
        self,
    ) -> None:
        self.assertTrue(
            self.table_exists(
                "pipeline_audit"
            ),
            (
                "ไม่พบตาราง pipeline_audit "
                "สำหรับบันทึกผล Quality Check"
            ),
        )


def main() -> None:
    test_suite = (
        unittest.defaultTestLoader
        .loadTestsFromTestCase(
            QualityCheckTestCase
        )
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
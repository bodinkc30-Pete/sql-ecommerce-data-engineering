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


class TransformationTestCase(unittest.TestCase):
    connection: sqlite3.Connection

    @classmethod
    def setUpClass(cls) -> None:
        if not DATABASE_PATH.exists():
            raise FileNotFoundError(
                "ยังไม่พบฐานข้อมูล กรุณารัน Pipeline "
                "ก่อนรัน Transformation Tests"
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

    def get_row_count(
        self,
        table_name: str,
    ) -> int:
        cursor = self.connection.execute(
            f"""
            SELECT COUNT(*) AS row_count
            FROM {table_name};
            """
        )

        return cursor.fetchone()["row_count"]

    def get_scalar(
        self,
        sql_query: str,
    ) -> int | float | str | None:
        cursor = self.connection.execute(
            sql_query
        )

        result = cursor.fetchone()

        if result is None:
            return None

        return result[0]

    def test_customer_transformation_created_rows(
        self,
    ) -> None:
        staging_count = self.get_row_count(
            "stg_customers"
        )

        core_count = self.get_row_count(
            "customers"
        )

        self.assertGreater(
            staging_count,
            0,
            "stg_customers ไม่มีข้อมูล",
        )

        self.assertGreater(
            core_count,
            0,
            "customers ไม่มีข้อมูลหลัง Transformation",
        )

    def test_product_transformation_created_rows(
        self,
    ) -> None:
        staging_count = self.get_row_count(
            "stg_products"
        )

        core_count = self.get_row_count(
            "products"
        )

        self.assertGreater(
            staging_count,
            0,
            "stg_products ไม่มีข้อมูล",
        )

        self.assertGreater(
            core_count,
            0,
            "products ไม่มีข้อมูลหลัง Transformation",
        )

    def test_order_transformation_created_rows(
        self,
    ) -> None:
        staging_count = self.get_row_count(
            "stg_orders"
        )

        core_count = self.get_row_count(
            "orders"
        )

        self.assertGreater(
            staging_count,
            0,
            "stg_orders ไม่มีข้อมูล",
        )

        self.assertGreater(
            core_count,
            0,
            "orders ไม่มีข้อมูลหลัง Transformation",
        )

    def test_order_item_transformation_created_rows(
        self,
    ) -> None:
        staging_count = self.get_row_count(
            "stg_order_items"
        )

        core_count = self.get_row_count(
            "order_items"
        )

        self.assertGreater(
            staging_count,
            0,
            "stg_order_items ไม่มีข้อมูล",
        )

        self.assertGreater(
            core_count,
            0,
            "order_items ไม่มีข้อมูลหลัง Transformation",
        )

    def test_payment_transformation_created_rows(
        self,
    ) -> None:
        staging_count = self.get_row_count(
            "stg_payments"
        )

        core_count = self.get_row_count(
            "payments"
        )

        self.assertGreater(
            staging_count,
            0,
            "stg_payments ไม่มีข้อมูล",
        )

        self.assertGreater(
            core_count,
            0,
            "payments ไม่มีข้อมูลหลัง Transformation",
        )

    def test_pawchoice_staging_created_rows(
        self,
    ) -> None:
        staging_count = self.get_row_count(
            "stg_influencer_payments"
        )

        self.assertGreater(
            staging_count,
            0,
            (
                "stg_influencer_payments ไม่มีข้อมูล "
                "ตรวจสอบไฟล์ Excel และชื่อ Sheet"
            ),
        )

    def test_campaign_transformation_created_rows(
        self,
    ) -> None:
        campaign_count = self.get_row_count(
            "campaigns"
        )

        self.assertGreater(
            campaign_count,
            0,
            "campaigns ไม่มีข้อมูลหลัง Transformation",
        )

    def test_influencer_transformation_created_rows(
        self,
    ) -> None:
        influencer_count = self.get_row_count(
            "influencers"
        )

        self.assertGreater(
            influencer_count,
            0,
            "influencers ไม่มีข้อมูลหลัง Transformation",
        )

    def test_influencer_payment_rows_exist(
        self,
    ) -> None:
        payment_count = self.get_row_count(
            "influencer_payments"
        )

        rejected_count = self.get_row_count(
            "rejected_influencer_records"
        )

        total_processed = (
            payment_count
            + rejected_count
        )

        self.assertGreater(
            total_processed,
            0,
            (
                "ไม่พบทั้งข้อมูลที่ผ่านและข้อมูลที่ถูก Reject "
                "จาก Pawchoice"
            ),
        )

    def test_valid_influencer_payment_statuses(
        self,
    ) -> None:
        invalid_status_count = self.get_scalar(
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

        self.assertEqual(
            invalid_status_count,
            0,
            "พบสถานะรายการจ่าย Influencer ที่ไม่ถูกต้อง",
        )

    def test_influencer_fee_amount_is_not_negative(
        self,
    ) -> None:
        negative_amount_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM influencer_payments
            WHERE fee_amount < 0;
            """
        )

        self.assertEqual(
            negative_amount_count,
            0,
            "พบค่าจ้าง Influencer ติดลบ",
        )

    def test_cancelled_payment_amount_is_zero(
        self,
    ) -> None:
        invalid_cancelled_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM influencer_payments
            WHERE
                payment_status = 'CANCELLED'
                AND fee_amount <> 0;
            """
        )

        self.assertEqual(
            invalid_cancelled_count,
            0,
            (
                "พบรายการ CANCELLED "
                "ที่มีค่าจ้างไม่เท่ากับ 0"
            ),
        )

    def test_influencer_payment_foreign_keys(
        self,
    ) -> None:
        missing_campaign_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM influencer_payments AS ip
            LEFT JOIN campaigns AS c
                ON ip.campaign_id = c.campaign_id
            WHERE c.campaign_id IS NULL;
            """
        )

        missing_influencer_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM influencer_payments AS ip
            LEFT JOIN influencers AS i
                ON ip.influencer_id = i.influencer_id
            WHERE i.influencer_id IS NULL;
            """
        )

        self.assertEqual(
            missing_campaign_count,
            0,
            "พบรายการจ่ายที่ไม่มีแคมเปญอ้างอิง",
        )

        self.assertEqual(
            missing_influencer_count,
            0,
            "พบรายการจ่ายที่ไม่มี Influencer อ้างอิง",
        )

    def test_record_hash_is_unique(
        self,
    ) -> None:
        duplicate_hash_count = self.get_scalar(
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

        self.assertEqual(
            duplicate_hash_count,
            0,
            "พบ record_hash ซ้ำใน influencer_payments",
        )

    def test_source_location_is_unique(
        self,
    ) -> None:
        duplicate_source_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    source_file,
                    source_sheet,
                    source_row_number
                FROM influencer_payments
                GROUP BY
                    source_file,
                    source_sheet,
                    source_row_number
                HAVING COUNT(*) > 1
            );
            """
        )

        self.assertEqual(
            duplicate_source_count,
            0,
            (
                "พบแถวต้นทางจาก Excel "
                "ถูกโหลดเข้าตาราง Core ซ้ำ"
            ),
        )

    def test_raw_bank_account_is_not_stored(
        self,
    ) -> None:
        invalid_hash_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM influencers
            WHERE
                bank_account_hash IS NOT NULL
                AND LENGTH(bank_account_hash) <> 64;
            """
        )

        self.assertEqual(
            invalid_hash_count,
            0,
            (
                "พบข้อมูลเลขบัญชีที่ไม่ได้จัดเก็บ "
                "ในรูปแบบ SHA-256"
            ),
        )

    def test_raw_phone_is_not_stored(
        self,
    ) -> None:
        invalid_hash_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM influencers
            WHERE
                contact_phone_hash IS NOT NULL
                AND LENGTH(contact_phone_hash) <> 64;
            """
        )

        self.assertEqual(
            invalid_hash_count,
            0,
            (
                "พบข้อมูลเบอร์โทรที่ไม่ได้จัดเก็บ "
                "ในรูปแบบ SHA-256"
            ),
        )

    def test_account_names_are_masked(
        self,
    ) -> None:
        unmasked_name_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM influencers
            WHERE
                account_name_masked IS NOT NULL
                AND TRIM(account_name_masked) <> ''
                AND account_name_masked NOT LIKE '%*%';
            """
        )

        self.assertEqual(
            unmasked_name_count,
            0,
            "พบชื่อบัญชีที่ยังไม่ได้ปิดบัง",
        )

    def test_rejected_records_have_reasons(
        self,
    ) -> None:
        missing_reason_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM rejected_influencer_records
            WHERE
                rejection_reason IS NULL
                OR TRIM(rejection_reason) = '';
            """
        )

        self.assertEqual(
            missing_reason_count,
            0,
            "พบข้อมูล Reject ที่ไม่มีเหตุผล",
        )

    def test_rejected_records_have_lineage(
        self,
    ) -> None:
        missing_lineage_count = self.get_scalar(
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

        self.assertEqual(
            missing_lineage_count,
            0,
            (
                "พบข้อมูล Reject ที่ไม่มี "
                "source_file, source_sheet "
                "หรือ source_row_number"
            ),
        )

    def test_no_unknown_campaigns(
        self,
    ) -> None:
        unknown_campaign_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM campaigns
            WHERE
                LOWER(TRIM(campaign_name))
                = 'unknown campaign';
            """
        )

        self.assertEqual(
            unknown_campaign_count,
            0,
            (
                "พบ Unknown Campaign "
                "ต้องตรวจ Logic การอ่านหัวข้อใน Excel"
            ),
        )

    def test_no_unknown_source_sections(
        self,
    ) -> None:
        unknown_section_count = self.get_scalar(
            """
            SELECT COUNT(*)
            FROM campaigns
            WHERE
                source_section
                LIKE 'UNKNOWN_SECTION_ROW_%';
            """
        )

        self.assertEqual(
            unknown_section_count,
            0,
            (
                "พบ Source Section ที่ระบบหาไม่สำเร็จ "
                "ต้องตรวจแถว Header ใน Excel"
            ),
        )

    def test_influencer_payment_view_matches_table(
        self,
    ) -> None:
        table_count = self.get_row_count(
            "influencer_payments"
        )

        view_count = self.get_row_count(
            "vw_influencer_payment_details"
        )

        self.assertEqual(
            view_count,
            table_count,
            (
                "จำนวนแถวใน View รายละเอียด "
                "ไม่ตรงกับ influencer_payments"
            ),
        )


def main() -> None:
    test_suite = (
        unittest.defaultTestLoader
        .loadTestsFromTestCase(
            TransformationTestCase
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
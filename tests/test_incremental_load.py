from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)

INFLUENCER_TRANSFORMATION_PATH = (
    PROJECT_ROOT
    / "transformations"
    / "07_clean_influencer_payments.sql"
)


class IncrementalLoadTestCase(unittest.TestCase):
    temporary_directory: tempfile.TemporaryDirectory
    temporary_database_path: Path
    connection: sqlite3.Connection

    @classmethod
    def setUpClass(cls) -> None:
        if not DATABASE_PATH.exists():
            raise FileNotFoundError(
                "ยังไม่พบฐานข้อมูล กรุณารัน Pipeline "
                "ก่อนรัน Incremental Load Tests"
            )

        if not INFLUENCER_TRANSFORMATION_PATH.exists():
            raise FileNotFoundError(
                "ไม่พบไฟล์ Transformation: "
                f"{INFLUENCER_TRANSFORMATION_PATH}"
            )

        cls.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        cls.temporary_database_path = (
            Path(cls.temporary_directory.name)
            / "incremental_load_test.db"
        )

        shutil.copy2(
            DATABASE_PATH,
            cls.temporary_database_path,
        )

        cls.connection = sqlite3.connect(
            cls.temporary_database_path
        )

        cls.connection.row_factory = sqlite3.Row

        cls.connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()
        cls.temporary_directory.cleanup()

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

    def get_distinct_count(
        self,
        table_name: str,
        column_name: str,
    ) -> int:
        cursor = self.connection.execute(
            f"""
            SELECT COUNT(
                DISTINCT {column_name}
            ) AS distinct_count
            FROM {table_name};
            """
        )

        return cursor.fetchone()["distinct_count"]

    def run_influencer_transformation(
        self,
    ) -> None:
        sql_script = (
            INFLUENCER_TRANSFORMATION_PATH
            .read_text(
                encoding="utf-8"
            )
        )

        self.connection.executescript(
            sql_script
        )

    def get_table_counts(
        self,
    ) -> dict[str, int]:
        table_names = [
            "campaigns",
            "influencers",
            "influencer_payments",
            "rejected_influencer_records",
        ]

        return {
            table_name: self.get_row_count(
                table_name
            )
            for table_name in table_names
        }

    def test_staging_source_locations_are_unique(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    source_file,
                    source_sheet,
                    source_row_number
                FROM stg_influencer_payments
                GROUP BY
                    source_file,
                    source_sheet,
                    source_row_number
                HAVING COUNT(*) > 1
            );
            """
        )

        duplicate_count = cursor.fetchone()[0]

        self.assertEqual(
            duplicate_count,
            0,
            (
                "พบแถวต้นทางซ้ำใน "
                "stg_influencer_payments"
            ),
        )

    def test_campaign_business_key_is_unique(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT
                    campaign_name,
                    source_section
                FROM campaigns
                GROUP BY
                    campaign_name,
                    source_section
                HAVING COUNT(*) > 1
            );
            """
        )

        duplicate_count = cursor.fetchone()[0]

        self.assertEqual(
            duplicate_count,
            0,
            (
                "พบ campaign_name และ "
                "source_section ซ้ำ"
            ),
        )

    def test_influencer_handle_is_unique(
        self,
    ) -> None:
        total_rows = self.get_row_count(
            "influencers"
        )

        distinct_handles = self.get_distinct_count(
            "influencers",
            "influencer_handle",
        )

        self.assertEqual(
            total_rows,
            distinct_handles,
            "พบ influencer_handle ซ้ำ",
        )

    def test_record_hash_is_unique(
        self,
    ) -> None:
        total_rows = self.get_row_count(
            "influencer_payments"
        )

        distinct_hashes = self.get_distinct_count(
            "influencer_payments",
            "record_hash",
        )

        self.assertEqual(
            total_rows,
            distinct_hashes,
            "พบ record_hash ซ้ำ",
        )

    def test_core_source_locations_are_unique(
        self,
    ) -> None:
        cursor = self.connection.execute(
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

        duplicate_count = cursor.fetchone()[0]

        self.assertEqual(
            duplicate_count,
            0,
            (
                "พบแถวต้นทางเดียวกันถูกโหลด "
                "เข้า influencer_payments ซ้ำ"
            ),
        )

    def test_first_rerun_does_not_add_duplicates(
        self,
    ) -> None:
        counts_before = self.get_table_counts()

        self.run_influencer_transformation()

        counts_after = self.get_table_counts()

        self.assertEqual(
            counts_before,
            counts_after,
            (
                "จำนวนข้อมูลเปลี่ยนหลังรัน "
                "Transformation ซ้ำครั้งแรก\n"
                f"ก่อนรัน: {counts_before}\n"
                f"หลังรัน: {counts_after}"
            ),
        )

    def test_second_rerun_is_idempotent(
        self,
    ) -> None:
        self.run_influencer_transformation()

        counts_before_second_run = (
            self.get_table_counts()
        )

        self.run_influencer_transformation()

        counts_after_second_run = (
            self.get_table_counts()
        )

        self.assertEqual(
            counts_before_second_run,
            counts_after_second_run,
            (
                "Transformation ไม่เป็น Idempotent "
                "เมื่อรันซ้ำหลายครั้ง\n"
                "ก่อนรันซ้ำ: "
                f"{counts_before_second_run}\n"
                "หลังรันซ้ำ: "
                f"{counts_after_second_run}"
            ),
        )

    def test_rejected_records_do_not_duplicate(
        self,
    ) -> None:
        rejected_before = self.get_row_count(
            "rejected_influencer_records"
        )

        self.run_influencer_transformation()

        rejected_after = self.get_row_count(
            "rejected_influencer_records"
        )

        self.assertEqual(
            rejected_before,
            rejected_after,
            (
                "ข้อมูล Reject เพิ่มซ้ำหลังรัน "
                "Transformation รอบใหม่"
            ),
        )

    def test_valid_and_rejected_source_rows_do_not_overlap(
        self,
    ) -> None:
        cursor = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM influencer_payments AS valid
            INNER JOIN rejected_influencer_records AS rejected
                ON valid.source_file =
                    rejected.source_file
                AND valid.source_sheet =
                    rejected.source_sheet
                AND valid.source_row_number =
                    rejected.source_row_number;
            """
        )

        overlapping_count = cursor.fetchone()[0]

        self.assertEqual(
            overlapping_count,
            0,
            (
                "พบแถวต้นทางเดียวกันอยู่ทั้ง "
                "Valid และ Rejected"
            ),
        )

    def test_foreign_keys_remain_valid_after_rerun(
        self,
    ) -> None:
        self.run_influencer_transformation()

        cursor = self.connection.execute(
            "PRAGMA foreign_key_check;"
        )

        foreign_key_issues = cursor.fetchall()

        self.assertEqual(
            foreign_key_issues,
            [],
            (
                "พบ Foreign Key ผิดหลังรันซ้ำ: "
                f"{foreign_key_issues}"
            ),
        )

    def test_database_integrity_after_rerun(
        self,
    ) -> None:
        self.run_influencer_transformation()

        cursor = self.connection.execute(
            "PRAGMA integrity_check;"
        )

        integrity_result = cursor.fetchone()[0]

        self.assertEqual(
            integrity_result,
            "ok",
            (
                "ฐานข้อมูลไม่สมบูรณ์หลังรันซ้ำ: "
                f"{integrity_result}"
            ),
        )


def main() -> None:
    test_suite = (
        unittest.defaultTestLoader
        .loadTestsFromTestCase(
            IncrementalLoadTestCase
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
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import sys
import uuid


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)

TRANSFORMATION_DIRECTORY = (
    PROJECT_ROOT
    / "transformations"
)


TRANSFORMATION_FILES = [
    TRANSFORMATION_DIRECTORY
    / "01_clean_customers.sql",

    TRANSFORMATION_DIRECTORY
    / "02_clean_products.sql",

    TRANSFORMATION_DIRECTORY
    / "03_clean_orders.sql",

    TRANSFORMATION_DIRECTORY
    / "04_clean_order_items.sql",

    TRANSFORMATION_DIRECTORY
    / "05_clean_payments.sql",

    TRANSFORMATION_DIRECTORY
    / "06_incremental_load.sql",

    TRANSFORMATION_DIRECTORY
    / "07_clean_influencer_payments.sql",
]


TARGET_TABLE_MAPPING = {
    "01_clean_customers.sql": "customers",
    "02_clean_products.sql": "products",
    "03_clean_orders.sql": "orders",
    "04_clean_order_items.sql": "order_items",
    "05_clean_payments.sql": "payments",
    "06_incremental_load.sql": None,
    "07_clean_influencer_payments.sql": (
        "influencer_payments"
    ),
}


PIPELINE_NAME = "ecommerce_transformation_pipeline"


def current_utc_time() -> str:
    return datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")


def validate_transformation_files() -> None:
    missing_files = [
        file_path
        for file_path in TRANSFORMATION_FILES
        if not file_path.exists()
    ]

    if not missing_files:
        return

    missing_file_text = "\n".join(
        f"- {file_path}"
        for file_path in missing_files
    )

    raise FileNotFoundError(
        "ไม่พบไฟล์ Transformation "
        "ต่อไปนี้:\n"
        f"{missing_file_text}"
    )


def read_sql_file(
    file_path: Path,
) -> str:
    sql_script = file_path.read_text(
        encoding="utf-8"
    )

    if not sql_script.strip():
        raise ValueError(
            f"ไฟล์ SQL ว่างเปล่า: "
            f"{file_path}"
        )

    return sql_script


def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    cursor = connection.execute(
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


def get_table_row_count(
    connection: sqlite3.Connection,
    table_name: str | None,
) -> int:
    if table_name is None:
        return 0

    if not table_exists(
        connection=connection,
        table_name=table_name,
    ):
        raise RuntimeError(
            f"ไม่พบ Target Table: "
            f"{table_name}"
        )

    cursor = connection.execute(
        f"""
        SELECT COUNT(*)
        FROM {table_name};
        """
    )

    return cursor.fetchone()[0]


def insert_audit_record(
    connection: sqlite3.Connection,
    run_id: str,
    step_name: str,
    run_status: str,
    rows_processed: int,
    rows_inserted: int,
    rows_updated: int,
    rows_rejected: int,
    error_message: str | None,
    started_at: str,
    completed_at: str,
) -> None:
    connection.execute(
        """
        INSERT INTO pipeline_audit (
            pipeline_name,
            run_id,
            step_name,
            run_status,
            rows_processed,
            rows_inserted,
            rows_updated,
            rows_rejected,
            error_message,
            started_at,
            completed_at
        )
        VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?
        );
        """,
        (
            PIPELINE_NAME,
            run_id,
            step_name,
            run_status,
            rows_processed,
            rows_inserted,
            rows_updated,
            rows_rejected,
            error_message,
            started_at,
            completed_at,
        ),
    )

    connection.commit()


def get_rejected_row_count(
    connection: sqlite3.Connection,
    file_name: str,
) -> int:
    if (
        file_name
        != "07_clean_influencer_payments.sql"
    ):
        return 0

    if not table_exists(
        connection=connection,
        table_name=(
            "rejected_influencer_records"
        ),
    ):
        return 0

    cursor = connection.execute(
        """
        SELECT COUNT(*)
        FROM rejected_influencer_records;
        """
    )

    return cursor.fetchone()[0]


def execute_transformation(
    connection: sqlite3.Connection,
    run_id: str,
    file_path: Path,
) -> None:
    file_name = file_path.name
    step_name = file_path.stem

    target_table = TARGET_TABLE_MAPPING.get(
        file_name
    )

    started_at = current_utc_time()

    rows_before = get_table_row_count(
        connection=connection,
        table_name=target_table,
    )

    rejected_before = get_rejected_row_count(
        connection=connection,
        file_name=file_name,
    )

    print(
        f"[INFO] กำลังรัน: "
        f"{file_name}"
    )

    try:
        sql_script = read_sql_file(
            file_path
        )

        connection.executescript(
            sql_script
        )

        rows_after = get_table_row_count(
            connection=connection,
            table_name=target_table,
        )

        rejected_after = (
            get_rejected_row_count(
                connection=connection,
                file_name=file_name,
            )
        )

        rows_inserted = max(
            rows_after - rows_before,
            0,
        )

        rows_updated = (
            rows_after
            if rows_after == rows_before
            and rows_after > 0
            else 0
        )

        rows_rejected = max(
            rejected_after - rejected_before,
            0,
        )

        rows_processed = (
            rows_after
            + rows_rejected
        )

        completed_at = current_utc_time()

        insert_audit_record(
            connection=connection,
            run_id=run_id,
            step_name=step_name,
            run_status="SUCCESS",
            rows_processed=rows_processed,
            rows_inserted=rows_inserted,
            rows_updated=rows_updated,
            rows_rejected=rows_rejected,
            error_message=None,
            started_at=started_at,
            completed_at=completed_at,
        )

        print(
            f"[SUCCESS] {file_name}"
        )

        if target_table is not None:
            print(
                f"  Target table: "
                f"{target_table}"
            )

            print(
                f"  Rows before: "
                f"{rows_before}"
            )

            print(
                f"  Rows after: "
                f"{rows_after}"
            )

        if (
            file_name
            == "07_clean_influencer_payments.sql"
        ):
            print(
                f"  Rejected rows: "
                f"{rejected_after}"
            )

    except Exception as error:
        completed_at = current_utc_time()

        try:
            connection.rollback()
        except sqlite3.Error:
            pass

        insert_audit_record(
            connection=connection,
            run_id=run_id,
            step_name=step_name,
            run_status="FAILED",
            rows_processed=0,
            rows_inserted=0,
            rows_updated=0,
            rows_rejected=0,
            error_message=str(error),
            started_at=started_at,
            completed_at=completed_at,
        )

        raise RuntimeError(
            f"Transformation ล้มเหลวที่ "
            f"{file_name}: {error}"
        ) from error


def validate_foreign_keys(
    connection: sqlite3.Connection,
) -> None:
    cursor = connection.execute(
        "PRAGMA foreign_key_check;"
    )

    foreign_key_issues = (
        cursor.fetchall()
    )

    if foreign_key_issues:
        raise RuntimeError(
            "พบ Foreign Key ที่ไม่ถูกต้อง: "
            f"{foreign_key_issues}"
        )


def print_transformation_summary(
    connection: sqlite3.Connection,
) -> None:
    summary_tables = [
        "customers",
        "products",
        "orders",
        "order_items",
        "payments",
        "campaigns",
        "influencers",
        "influencer_payments",
        "rejected_influencer_records",
    ]

    print("-" * 60)

    print(
        "[SUMMARY] Transformation results"
    )

    for table_name in summary_tables:
        row_count = get_table_row_count(
            connection=connection,
            table_name=table_name,
        )

        print(
            f"  - {table_name}: "
            f"{row_count} rows"
        )

    print("-" * 60)


def run_all_transformations() -> None:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "ยังไม่พบฐานข้อมูล กรุณารัน "
            "scripts/01_setup_database.py ก่อน"
        )

    validate_transformation_files()

    run_id = str(
        uuid.uuid4()
    )

    print(
        f"[INFO] Transformation "
        f"run_id: {run_id}"
    )

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

        for transformation_file in (
            TRANSFORMATION_FILES
        ):
            execute_transformation(
                connection=connection,
                run_id=run_id,
                file_path=transformation_file,
            )

        validate_foreign_keys(
            connection
        )

        print_transformation_summary(
            connection
        )

    print(
        "[SUCCESS] รัน Transformation "
        "ครบทุกไฟล์แล้ว"
    )


def main() -> None:
    try:
        run_all_transformations()

    except FileNotFoundError as error:
        print(
            f"[FILE ERROR] {error}"
        )

        sys.exit(1)

    except ValueError as error:
        print(
            f"[VALIDATION ERROR] {error}"
        )

        sys.exit(1)

    except RuntimeError as error:
        print(
            f"[TRANSFORMATION ERROR] {error}"
        )

        sys.exit(1)

    except sqlite3.Error as error:
        print(
            f"[DATABASE ERROR] {error}"
        )

        sys.exit(1)

    except Exception as error:
        print(
            f"[UNEXPECTED ERROR] {error}"
        )

        sys.exit(1)


if __name__ == "__main__":
    main()
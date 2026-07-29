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

QUALITY_CHECK_FILES = [
    PROJECT_ROOT
    / "quality_checks"
    / "01_null_checks.sql",

    PROJECT_ROOT
    / "quality_checks"
    / "02_duplicate_checks.sql",

    PROJECT_ROOT
    / "quality_checks"
    / "03_referential_integrity.sql",

    PROJECT_ROOT
    / "quality_checks"
    / "04_reconciliation_checks.sql",

    PROJECT_ROOT
    / "quality_checks"
    / "05_business_rule_checks.sql",

    PROJECT_ROOT
    / "quality_checks"
    / "06_influencer_payment_checks.sql",
]

PIPELINE_NAME = "ecommerce_quality_check_pipeline"


def current_utc_time() -> str:
    return datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")


def read_sql_file(
    file_path: Path,
) -> str:
    if not file_path.exists():
        raise FileNotFoundError(
            f"ไม่พบไฟล์ Quality Check: "
            f"{file_path}"
        )

    return file_path.read_text(
        encoding="utf-8"
    )


def execute_check_queries(
    connection: sqlite3.Connection,
    sql_script: str,
) -> list[sqlite3.Row]:
    result_rows = []

    statements = [
        statement.strip()
        for statement in sql_script.split(";")
        if statement.strip()
    ]

    for statement in statements:
        cursor = connection.execute(
            statement
        )

        if cursor.description is not None:
            result_rows.extend(
                cursor.fetchall()
            )

    return result_rows


def insert_audit_record(
    connection: sqlite3.Connection,
    run_id: str,
    step_name: str,
    run_status: str,
    rows_processed: int,
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
            ?, ?, ?, ?, ?, 0, 0,
            ?, ?, ?, ?
        );
        """,
        (
            PIPELINE_NAME,
            run_id,
            step_name,
            run_status,
            rows_processed,
            rows_rejected,
            error_message,
            started_at,
            completed_at,
        ),
    )

    connection.commit()


def print_check_results(
    file_name: str,
    result_rows: list[sqlite3.Row],
) -> None:
    if not result_rows:
        print(
            f"[PASSED] {file_name}: "
            "ไม่พบข้อมูลที่ผิดเงื่อนไข"
        )
        return

    print(
        f"[FAILED] {file_name}: "
        f"พบปัญหา "
        f"{len(result_rows)} รายการ"
    )

    for row_number, row in enumerate(
        result_rows,
        start=1,
    ):
        row_values = dict(row)

        print(
            f"  {row_number}. "
            f"{row_values}"
        )


def run_quality_check(
    connection: sqlite3.Connection,
    run_id: str,
    file_path: Path,
) -> int:
    step_name = file_path.stem

    started_at = current_utc_time()

    try:
        sql_script = read_sql_file(
            file_path
        )

        result_rows = execute_check_queries(
            connection=connection,
            sql_script=sql_script,
        )

        issue_count = len(result_rows)

        if issue_count == 0:
            run_status = "SUCCESS"
            error_message = None
        else:
            run_status = "FAILED"

            error_message = (
                "พบปัญหาคุณภาพข้อมูล "
                f"{issue_count} รายการ"
            )

        completed_at = current_utc_time()

        insert_audit_record(
            connection=connection,
            run_id=run_id,
            step_name=step_name,
            run_status=run_status,
            rows_processed=issue_count,
            rows_rejected=issue_count,
            error_message=error_message,
            started_at=started_at,
            completed_at=completed_at,
        )

        print_check_results(
            file_name=file_path.name,
            result_rows=result_rows,
        )

        return issue_count

    except Exception as error:
        completed_at = current_utc_time()

        insert_audit_record(
            connection=connection,
            run_id=run_id,
            step_name=step_name,
            run_status="FAILED",
            rows_processed=0,
            rows_rejected=0,
            error_message=str(error),
            started_at=started_at,
            completed_at=completed_at,
        )

        raise


def run_all_quality_checks() -> None:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "ยังไม่พบฐานข้อมูล กรุณารัน "
            "scripts/01_setup_database.py "
            "ก่อน"
        )

    run_id = str(
        uuid.uuid4()
    )

    print(
        f"[INFO] Quality check "
        f"run_id: {run_id}"
    )

    total_issues = 0

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

        for quality_check_file in (
            QUALITY_CHECK_FILES
        ):
            issue_count = run_quality_check(
                connection=connection,
                run_id=run_id,
                file_path=quality_check_file,
            )

            total_issues += issue_count

    print("-" * 60)

    if total_issues == 0:
        print(
            "[SUCCESS] ข้อมูลผ่าน "
            "Quality Checks ทั้งหมด"
        )

    else:
        print(
            "[FAILED] พบปัญหา"
            "คุณภาพข้อมูลรวม: "
            f"{total_issues} รายการ"
        )

        raise ValueError(
            "Quality Checks ไม่ผ่าน "
            f"{total_issues} รายการ"
        )


def main() -> None:
    try:
        run_all_quality_checks()

    except FileNotFoundError as error:
        print(
            f"[FILE ERROR] {error}"
        )
        sys.exit(1)

    except ValueError as error:
        print(
            f"[QUALITY ERROR] {error}"
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
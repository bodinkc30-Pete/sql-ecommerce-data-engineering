from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import sys
import uuid


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)

CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "pipeline_config.json"
)

INCREMENTAL_LOAD_FILE = (
    PROJECT_ROOT
    / "transformations"
    / "06_incremental_load.sql"
)

INCREMENTAL_LOOKBACK_PLACEHOLDER = (
    "__INCREMENTAL_LOOKBACK_MINUTES__"
)

WATERMARK_FUTURE_TOLERANCE_PLACEHOLDER = (
    "__WATERMARK_FUTURE_TOLERANCE_MINUTES__"
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


def get_run_context() -> tuple[
    str,
    str | None,
    str | None,
]:
    run_type = (
        os.environ.get("PIPELINE_RUN_TYPE", "NORMAL")
        .strip()
        .upper()
    )
    backfill_start_date = os.environ.get(
        "PIPELINE_BACKFILL_START_DATE"
    )
    backfill_end_date = os.environ.get(
        "PIPELINE_BACKFILL_END_DATE"
    )

    if run_type == "BACKFILL":
        if not backfill_start_date or not backfill_end_date:
            raise ValueError(
                "BACKFILL transformation requires both "
                "backfill environment dates."
            )

    return (
        run_type,
        backfill_start_date,
        backfill_end_date,
    )


def get_transformation_files_for_run(
    run_type: str,
) -> list[Path]:
    if run_type == "BACKFILL":
        # Preserve existing historical full-upsert behavior.
        # Historical reruns must not advance the normal watermark.
        return [
            file_path
            for file_path in TRANSFORMATION_FILES
            if file_path.name != "06_incremental_load.sql"
        ]

    # NORMAL and RECOVERY use one Core load path only.
    # 01-05 are full staging-to-core upserts, so running them here
    # would bypass the incremental watermark logic in 06.
    return [
        file_path
        for file_path in TRANSFORMATION_FILES
        if file_path.name in {
            "06_incremental_load.sql",
            "07_clean_influencer_payments.sql",
        }
    ]


def read_pipeline_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"ไม่พบ Pipeline Config: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open(
        mode="r",
        encoding="utf-8",
    ) as config_file:
        config = json.load(config_file)

    if not isinstance(config, dict):
        raise ValueError(
            "pipeline_config.json ต้องเป็น JSON object"
        )

    return config


def get_incremental_lookback_minutes(
    config: dict,
) -> int:
    pipeline_config = config.get("pipeline", {})
    raw_value = pipeline_config.get(
        "incremental_lookback_minutes"
    )

    if raw_value is None:
        raise ValueError(
            "ไม่พบ pipeline.incremental_lookback_minutes "
            "ใน pipeline_config.json"
        )

    if isinstance(raw_value, bool):
        raise ValueError(
            "pipeline.incremental_lookback_minutes ต้องเป็นจำนวนเต็ม"
        )

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "pipeline.incremental_lookback_minutes ต้องเป็นจำนวนเต็ม"
        ) from error

    if value < 0:
        raise ValueError(
            "pipeline.incremental_lookback_minutes ต้องไม่น้อยกว่า 0"
        )

    return value


def get_watermark_future_tolerance_minutes(
    config: dict,
) -> int:
    pipeline_config = config.get("pipeline", {})
    raw_value = pipeline_config.get(
        "watermark_future_tolerance_minutes"
    )

    if raw_value is None:
        raise ValueError(
            "ไม่พบ pipeline.watermark_future_tolerance_minutes "
            "ใน pipeline_config.json"
        )

    if isinstance(raw_value, bool):
        raise ValueError(
            "pipeline.watermark_future_tolerance_minutes "
            "ต้องเป็นจำนวนเต็ม"
        )

    try:
        value = int(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "pipeline.watermark_future_tolerance_minutes "
            "ต้องเป็นจำนวนเต็ม"
        ) from error

    if value < 0:
        raise ValueError(
            "pipeline.watermark_future_tolerance_minutes "
            "ต้องไม่น้อยกว่า 0"
        )

    return value


def render_transformation_sql(
    file_path: Path,
    sql_script: str,
    incremental_lookback_minutes: int,
    watermark_future_tolerance_minutes: int,
) -> str:
    if file_path != INCREMENTAL_LOAD_FILE:
        return sql_script

    if INCREMENTAL_LOOKBACK_PLACEHOLDER not in sql_script:
        raise ValueError(
            "06_incremental_load.sql ไม่มี placeholder "
            f"{INCREMENTAL_LOOKBACK_PLACEHOLDER}"
        )

    rendered_sql = sql_script.replace(
        INCREMENTAL_LOOKBACK_PLACEHOLDER,
        str(incremental_lookback_minutes),
    )

    rendered_sql = rendered_sql.replace(
        WATERMARK_FUTURE_TOLERANCE_PLACEHOLDER,
        str(watermark_future_tolerance_minutes),
    )

    if INCREMENTAL_LOOKBACK_PLACEHOLDER in rendered_sql:
        raise ValueError(
            "ไม่สามารถแทนค่า Incremental Lookback ใน SQL ได้ครบ"
        )

    if WATERMARK_FUTURE_TOLERANCE_PLACEHOLDER in rendered_sql:
        raise ValueError(
            "ไม่สามารถแทนค่า Watermark Future Tolerance "
            "ใน SQL ได้ครบ"
        )

    return rendered_sql


def validate_transformation_files(
    transformation_files: list[Path] | None = None,
) -> None:
    files_to_validate = (
        transformation_files
        if transformation_files is not None
        else TRANSFORMATION_FILES
    )

    missing_files = [
        file_path
        for file_path in files_to_validate
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
    incremental_lookback_minutes: int,
    watermark_future_tolerance_minutes: int,
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

        sql_script = render_transformation_sql(
            file_path=file_path,
            sql_script=sql_script,
            incremental_lookback_minutes=(
                incremental_lookback_minutes
            ),
            watermark_future_tolerance_minutes=(
                watermark_future_tolerance_minutes
            ),
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

    (
        run_type,
        backfill_start_date,
        backfill_end_date,
    ) = get_run_context()

    transformation_files = get_transformation_files_for_run(
        run_type
    )

    config = read_pipeline_config()
    incremental_lookback_minutes = (
        get_incremental_lookback_minutes(config)
    )
    watermark_future_tolerance_minutes = (
        get_watermark_future_tolerance_minutes(config)
    )

    validate_transformation_files(
        transformation_files
    )

    run_id = (
        os.environ.get("PIPELINE_RUN_ID")
        or str(uuid.uuid4())
    )

    print(
        f"[INFO] Transformation "
        f"run_id: {run_id}"
    )
    print(f"[INFO] Transformation run_type: {run_type}")
    print(
        "[INFO] Incremental lookback: "
        f"{incremental_lookback_minutes} minutes"
    )
    print(
        "[INFO] Watermark future tolerance: "
        f"{watermark_future_tolerance_minutes} minutes"
    )

    if run_type == "BACKFILL":
        print(
            "[INFO] Transformation backfill window: "
            f"{backfill_start_date} -> {backfill_end_date}"
        )
        print(
            "[INFO] 06_incremental_load.sql skipped "
            "to preserve the normal watermark."
        )

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

        for transformation_file in (
            transformation_files
        ):
            execute_transformation(
                connection=connection,
                run_id=run_id,
                file_path=transformation_file,
                incremental_lookback_minutes=(
                    incremental_lookback_minutes
                ),
                watermark_future_tolerance_minutes=(
                    watermark_future_tolerance_minutes
                ),
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

    except json.JSONDecodeError as error:
        print(
            f"[CONFIG ERROR] JSON ไม่ถูกต้อง: {error}"
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
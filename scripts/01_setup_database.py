from pathlib import Path
import sqlite3
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_DIRECTORY = (
    PROJECT_ROOT
    / "database"
)

DATABASE_PATH = (
    DATABASE_DIRECTORY
    / "ecommerce_data_engineering.db"
)

SCHEMA_DIRECTORY = (
    PROJECT_ROOT
    / "schema"
)


SCHEMA_FILES = [
    SCHEMA_DIRECTORY
    / "01_create_staging_tables.sql",

    SCHEMA_DIRECTORY
    / "02_create_core_tables.sql",

    SCHEMA_DIRECTORY
    / "03_create_indexes.sql",

    SCHEMA_DIRECTORY
    / "04_create_views.sql",
]


def validate_schema_files() -> None:
    missing_files = [
        file_path
        for file_path in SCHEMA_FILES
        if not file_path.exists()
    ]

    if not missing_files:
        return

    missing_file_text = "\n".join(
        f"- {file_path}"
        for file_path in missing_files
    )

    raise FileNotFoundError(
        "ไม่พบไฟล์ Schema ต่อไปนี้:\n"
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
            f"ไฟล์ SQL ว่างเปล่า: {file_path}"
        )

    return sql_script


def execute_schema_file(
    connection: sqlite3.Connection,
    file_path: Path,
) -> None:
    sql_script = read_sql_file(
        file_path
    )

    print(
        f"[INFO] กำลังรัน: "
        f"{file_path.name}"
    )

    connection.executescript(
        sql_script
    )

    print(
        f"[SUCCESS] สร้างจากไฟล์ "
        f"{file_path.name} สำเร็จ"
    )


def get_database_objects(
    connection: sqlite3.Connection,
    object_type: str,
) -> list[str]:
    cursor = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE
            type = ?
            AND name NOT LIKE 'sqlite_%'
        ORDER BY name;
        """,
        (object_type,),
    )

    return [
        row[0]
        for row in cursor.fetchall()
    ]


def validate_required_tables(
    connection: sqlite3.Connection,
) -> None:
    required_tables = {
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

    actual_tables = set(
        get_database_objects(
            connection=connection,
            object_type="table",
        )
    )

    missing_tables = (
        required_tables
        - actual_tables
    )

    if missing_tables:
        raise RuntimeError(
            "สร้างตารางไม่ครบ ขาดตาราง: "
            f"{sorted(missing_tables)}"
        )


def validate_required_views(
    connection: sqlite3.Connection,
) -> None:
    required_views = {
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

    actual_views = set(
        get_database_objects(
            connection=connection,
            object_type="view",
        )
    )

    missing_views = (
        required_views
        - actual_views
    )

    if missing_views:
        raise RuntimeError(
            "สร้าง View ไม่ครบ ขาด View: "
            f"{sorted(missing_views)}"
        )


def validate_database_integrity(
    connection: sqlite3.Connection,
) -> None:
    cursor = connection.execute(
        "PRAGMA integrity_check;"
    )

    integrity_result = (
        cursor.fetchone()[0]
    )

    if integrity_result != "ok":
        raise RuntimeError(
            "SQLite ตรวจพบปัญหาในฐานข้อมูล: "
            f"{integrity_result}"
        )


def print_database_summary(
    connection: sqlite3.Connection,
) -> None:
    tables = get_database_objects(
        connection=connection,
        object_type="table",
    )

    views = get_database_objects(
        connection=connection,
        object_type="view",
    )

    indexes = get_database_objects(
        connection=connection,
        object_type="index",
    )

    print("-" * 60)

    print(
        f"[SUMMARY] Tables: "
        f"{len(tables)}"
    )

    for table_name in tables:
        print(
            f"  - {table_name}"
        )

    print(
        f"[SUMMARY] Views: "
        f"{len(views)}"
    )

    for view_name in views:
        print(
            f"  - {view_name}"
        )

    print(
        f"[SUMMARY] Indexes: "
        f"{len(indexes)}"
    )

    for index_name in indexes:
        print(
            f"  - {index_name}"
        )

    print("-" * 60)


def setup_database() -> None:
    DATABASE_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    validate_schema_files()

    print(
        f"[INFO] Database path: "
        f"{DATABASE_PATH}"
    )

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

        try:
            for schema_file in SCHEMA_FILES:
                execute_schema_file(
                    connection=connection,
                    file_path=schema_file,
                )

            validate_required_tables(
                connection
            )

            validate_required_views(
                connection
            )

            validate_database_integrity(
                connection
            )

            connection.commit()

            print_database_summary(
                connection
            )

        except Exception:
            connection.rollback()
            raise

    print(
        "[SUCCESS] สร้างฐานข้อมูล "
        "Schema, Index และ View ครบแล้ว"
    )


def main() -> None:
    try:
        setup_database()

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

    except sqlite3.Error as error:
        print(
            f"[DATABASE ERROR] {error}"
        )
        sys.exit(1)

    except RuntimeError as error:
        print(
            f"[SETUP ERROR] {error}"
        )
        sys.exit(1)

    except Exception as error:
        print(
            f"[UNEXPECTED ERROR] {error}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
from contextlib import closing
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
    SCHEMA_DIRECTORY / "01_create_staging_tables.sql",
    SCHEMA_DIRECTORY / "02_create_core_tables.sql",
    SCHEMA_DIRECTORY / "03_create_indexes.sql",
    SCHEMA_DIRECTORY / "04_create_views.sql",

    # Governance / Lineage
    SCHEMA_DIRECTORY / "05_create_governance_tables.sql",
    SCHEMA_DIRECTORY / "06_seed_data_assets.sql",
    SCHEMA_DIRECTORY / "07_create_lineage_edges.sql",
    SCHEMA_DIRECTORY / "08_seed_lineage_edges.sql",
    SCHEMA_DIRECTORY / "09_correct_lineage_edges.sql",
    SCHEMA_DIRECTORY / "10_create_lineage_run_events.sql",
    SCHEMA_DIRECTORY / "11_create_governance_views.sql",
    SCHEMA_DIRECTORY / "12_fix_governance_dependency_views.sql",
    SCHEMA_DIRECTORY / "13_fix_pii_classification.sql",
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
        "pipeline_watermark",
        "pipeline_step_log",
        "pipeline_sla_metrics",

        # Governance / Lineage
        "data_assets",
        "lineage_edges",
        "lineage_run_events",
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
        "vw_order_details",
        "vw_customer_order_summary",
        "vw_product_sales_summary",
        "vw_daily_sales_summary",
        "vw_payment_reconciliation",
        "vw_payment_summary",
        "vw_data_quality_summary",
        "vw_pipeline_run_summary",
        "vw_pipeline_step_monitoring",
        "vw_pipeline_sla_monitoring",
        "vw_influencer_payment_details",
        "vw_campaign_payment_summary",
        "vw_influencer_payment_summary",
        "vw_payment_status_summary",
        "vw_rejected_influencer_summary",

        # Governance / Lineage
        "vw_data_lineage",
        "vw_lineage_run_history",
        "vw_asset_upstream_dependencies",
        "vw_asset_downstream_dependencies",
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


def validate_governance_metadata(
    connection: sqlite3.Connection,
) -> None:
    asset_count = connection.execute(
        "SELECT COUNT(*) FROM data_assets;"
    ).fetchone()[0]

    lineage_edge_count = connection.execute(
        "SELECT COUNT(*) FROM lineage_edges;"
    ).fetchone()[0]

    if asset_count <= 0:
        raise RuntimeError(
            "Governance metadata ไม่สมบูรณ์: data_assets ไม่มีข้อมูล"
        )

    if lineage_edge_count <= 0:
        raise RuntimeError(
            "Governance metadata ไม่สมบูรณ์: lineage_edges ไม่มีข้อมูล"
        )

    duplicate_asset_keys = connection.execute(
        """
        SELECT asset_key
        FROM data_assets
        GROUP BY asset_key
        HAVING COUNT(*) > 1;
        """
    ).fetchall()

    if duplicate_asset_keys:
        raise RuntimeError(
            "Governance metadata พบ asset_key ซ้ำ: "
            f"{duplicate_asset_keys}"
        )

    invalid_pii_assets = connection.execute(
        """
        SELECT asset_key, classification
        FROM data_assets
        WHERE
            contains_pii = 1
            AND classification NOT IN (
                'CONFIDENTIAL',
                'RESTRICTED'
            );
        """
    ).fetchall()

    if invalid_pii_assets:
        raise RuntimeError(
            "Governance metadata พบ PII classification ไม่ถูกต้อง: "
            f"{invalid_pii_assets}"
        )

    orphan_lineage_edges = connection.execute(
        """
        SELECT e.lineage_edge_id
        FROM lineage_edges AS e
        LEFT JOIN data_assets AS u
            ON u.asset_id = e.upstream_asset_id
        LEFT JOIN data_assets AS d
            ON d.asset_id = e.downstream_asset_id
        WHERE
            u.asset_id IS NULL
            OR d.asset_id IS NULL;
        """
    ).fetchall()

    if orphan_lineage_edges:
        raise RuntimeError(
            "Governance metadata พบ orphan lineage edges: "
            f"{orphan_lineage_edges}"
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

    # sqlite3.Connection's context manager commits/rolls back, but it does
    # not guarantee that the database handle itself is closed immediately.
    # Explicit closing is important on Windows, where an open SQLite handle
    # can keep temporary database files locked after setup completes.
    with closing(
        sqlite3.connect(DATABASE_PATH)
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

            validate_governance_metadata(
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
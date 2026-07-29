from pathlib import Path
import csv
import sqlite3
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)

OUTPUT_DIRECTORY = (
    PROJECT_ROOT
    / "data"
    / "processed"
)


EXPORT_QUERIES = {
    "sample_campaign_payment_summary.csv": """
        SELECT
            campaign_name,
            source_section,
            total_payment_records,
            total_influencers,
            ROUND(total_fee_amount, 2)
                AS total_fee_amount,
            ROUND(paid_amount, 2)
                AS paid_amount,
            ROUND(unpaid_amount, 2)
                AS unpaid_amount,
            ROUND(cancelled_amount, 2)
                AS cancelled_amount
        FROM vw_campaign_payment_summary
        ORDER BY
            total_fee_amount DESC,
            campaign_name,
            source_section;
    """,

    "sample_payment_status_summary.csv": """
        SELECT
            payment_status,
            total_records,
            total_influencers,
            total_campaigns,
            ROUND(total_fee_amount, 2)
                AS total_fee_amount,
            ROUND(average_fee_amount, 2)
                AS average_fee_amount
        FROM vw_payment_status_summary
        ORDER BY
            payment_status;
    """,

    "sample_rejected_record_summary.csv": """
        SELECT
            rejection_reason,
            rejected_record_count,
            affected_source_files,
            first_rejected_at,
            latest_rejected_at
        FROM vw_rejected_influencer_summary
        ORDER BY
            rejected_record_count DESC,
            rejection_reason;
    """,

    "sample_pipeline_run_summary.csv": """
        SELECT
            run_id,
            pipeline_name,
            pipeline_started_at,
            pipeline_completed_at,
            total_steps,
            total_rows_processed,
            total_rows_inserted,
            total_rows_updated,
            total_rows_rejected,
            pipeline_status
        FROM vw_pipeline_run_summary
        ORDER BY
            pipeline_started_at DESC;
    """,

    "sample_data_quality_summary.csv": """
        SELECT
            quality_source,
            issue_type,
            issue_count,
            affected_source_count,
            first_detected_at,
            latest_detected_at
        FROM vw_data_quality_summary
        ORDER BY
            issue_count DESC,
            quality_source,
            issue_type;
    """,

    "sample_ecommerce_daily_sales.csv": """
        SELECT
            order_date,
            total_orders,
            unique_customers,
            units_sold,
            ROUND(total_revenue, 2)
                AS total_revenue,
            ROUND(average_order_value, 2)
                AS average_order_value
        FROM vw_daily_sales_summary
        ORDER BY
            order_date;
    """,
}


def validate_database_exists() -> None:
    if DATABASE_PATH.exists():
        return

    raise FileNotFoundError(
        "ยังไม่พบฐานข้อมูล กรุณารัน "
        "python scripts/05_run_pipeline.py ก่อน"
    )


def create_output_directory() -> None:
    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )


def export_query_to_csv(
    connection: sqlite3.Connection,
    output_file_name: str,
    sql_query: str,
) -> int:
    cursor = connection.execute(
        sql_query
    )

    column_names = [
        description[0]
        for description in cursor.description
    ]

    rows = cursor.fetchall()

    output_path = (
        OUTPUT_DIRECTORY
        / output_file_name
    )

    with output_path.open(
        mode="w",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        writer = csv.writer(
            csv_file
        )

        writer.writerow(
            column_names
        )

        writer.writerows(
            rows
        )

    print(
        f"[SUCCESS] สร้าง {output_file_name}: "
        f"{len(rows)} แถว"
    )

    return len(rows)


def export_portfolio_outputs() -> None:
    validate_database_exists()

    create_output_directory()

    total_exported_rows = 0

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        for output_file_name, sql_query in (
            EXPORT_QUERIES.items()
        ):
            exported_rows = export_query_to_csv(
                connection=connection,
                output_file_name=output_file_name,
                sql_query=sql_query,
            )

            total_exported_rows += (
                exported_rows
            )

    print("-" * 60)

    print(
        "[SUCCESS] สร้าง Portfolio Outputs "
        "ครบทั้งหมด"
    )

    print(
        f"[INFO] Output directory: "
        f"{OUTPUT_DIRECTORY}"
    )

    print(
        f"[INFO] จำนวนไฟล์: "
        f"{len(EXPORT_QUERIES)}"
    )

    print(
        f"[INFO] จำนวนแถวรวม: "
        f"{total_exported_rows}"
    )


def main() -> None:
    try:
        export_portfolio_outputs()

    except FileNotFoundError as error:
        print(
            f"[FILE ERROR] {error}"
        )
        sys.exit(1)

    except sqlite3.Error as error:
        print(
            f"[DATABASE ERROR] {error}"
        )
        sys.exit(1)

    except OSError as error:
        print(
            f"[OUTPUT ERROR] {error}"
        )
        sys.exit(1)

    except Exception as error:
        print(
            f"[UNEXPECTED ERROR] {error}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
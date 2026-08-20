import csv
import importlib.util
from pathlib import Path
import sqlite3
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

STAGING_SCHEMA_PATH = (
    PROJECT_ROOT
    / "schema"
    / "01_create_staging_tables.sql"
)

CORE_SCHEMA_PATH = (
    PROJECT_ROOT
    / "schema"
    / "02_create_core_tables.sql"
)

TRANSFORMATION_RUNNER_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "03_run_transformations.py"
)

TRANSFORMATION_SQL_PATH = (
    PROJECT_ROOT
    / "transformations"
    / "06_incremental_load.sql"
)

SYNTHETIC_DATA_DIR = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "synthetic"
)

DATASETS = {
    "customers": "customers.csv",
    "products": "products.csv",
    "orders": "orders.csv",
    "order_items": "order_items.csv",
    "payments": "payments.csv",
}


def load_transformation_runner():
    spec = importlib.util.spec_from_file_location(
        "project_transformation_runner",
        TRANSFORMATION_RUNNER_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Unable to load production transformation runner"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TRANSFORMATION_RUNNER = load_transformation_runner()


def read_sql(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def create_test_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")

    connection.execute(
        "PRAGMA foreign_keys = ON;"
    )

    connection.executescript(
        read_sql(STAGING_SCHEMA_PATH)
    )

    connection.executescript(
        read_sql(CORE_SCHEMA_PATH)
    )

    return connection


def table_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> list[str]:
    return [
        row[1]
        for row in connection.execute(
            f"PRAGMA table_info({table_name});"
        ).fetchall()
    ]


def seed_pipeline_watermarks(
    connection: sqlite3.Connection,
) -> None:
    for dataset_name in DATASETS:
        connection.execute(
            """
            INSERT OR REPLACE INTO pipeline_watermark (
                table_name,
                last_loaded_at
            )
            VALUES (?, '1900-01-01 00:00:00');
            """,
            (f"stg_{dataset_name}",),
        )


def load_csv_into_staging(
    connection: sqlite3.Connection,
    dataset_name: str,
    file_name: str,
    loaded_at: str,
) -> None:
    source_path = SYNTHETIC_DATA_DIR / file_name
    staging_table = f"stg_{dataset_name}"

    available_columns = set(
        table_columns(
            connection,
            staging_table,
        )
    )

    with source_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as csv_file:
        reader = csv.DictReader(csv_file)

        if reader.fieldnames is None:
            raise AssertionError(
                f"{file_name} has no CSV header"
            )

        csv_columns = list(reader.fieldnames)

        missing_columns = (
            set(csv_columns)
            - available_columns
        )

        if missing_columns:
            raise AssertionError(
                (
                    f"{staging_table} is missing CSV "
                    f"columns: {sorted(missing_columns)}"
                )
            )

        insert_columns = list(csv_columns)

        if "source_file" in available_columns:
            insert_columns.append("source_file")

        if "loaded_at" in available_columns:
            insert_columns.append("loaded_at")

        column_sql = ", ".join(insert_columns)

        placeholders = ", ".join(
            "?" for _ in insert_columns
        )

        insert_sql = (
            f"INSERT INTO {staging_table} "
            f"({column_sql}) "
            f"VALUES ({placeholders});"
        )

        for row in reader:
            values = [
                row[column]
                for column in csv_columns
            ]

            if "source_file" in available_columns:
                values.append(file_name)

            if "loaded_at" in available_columns:
                values.append(loaded_at)

            connection.execute(
                insert_sql,
                values,
            )


def seed_staging_from_real_csvs(
    connection: sqlite3.Connection,
    loaded_at: str,
) -> None:
    for dataset_name, file_name in DATASETS.items():
        load_csv_into_staging(
            connection=connection,
            dataset_name=dataset_name,
            file_name=file_name,
            loaded_at=loaded_at,
        )


def render_incremental_sql() -> str:
    config = (
        TRANSFORMATION_RUNNER.read_pipeline_config()
    )

    incremental_lookback_minutes = (
        TRANSFORMATION_RUNNER
        .get_incremental_lookback_minutes(
            config
        )
    )

    watermark_future_tolerance_minutes = (
        TRANSFORMATION_RUNNER
        .get_watermark_future_tolerance_minutes(
            config
        )
    )

    sql_script = (
        TRANSFORMATION_RUNNER.read_sql_file(
            TRANSFORMATION_SQL_PATH
        )
    )

    rendered_sql = (
        TRANSFORMATION_RUNNER
        .render_transformation_sql(
            file_path=TRANSFORMATION_SQL_PATH,
            sql_script=sql_script,
            incremental_lookback_minutes=(
                incremental_lookback_minutes
            ),
            watermark_future_tolerance_minutes=(
                watermark_future_tolerance_minutes
            ),
        )
    )

    if "__INCREMENTAL_LOOKBACK_MINUTES__" in rendered_sql:
        raise AssertionError(
            "Incremental lookback placeholder was not rendered"
        )

    if (
        "__WATERMARK_FUTURE_TOLERANCE_MINUTES__"
        in rendered_sql
    ):
        raise AssertionError(
            "Watermark future tolerance placeholder "
            "was not rendered"
        )

    return rendered_sql


def get_core_counts(
    connection: sqlite3.Connection,
) -> dict[str, int]:
    return {
        table_name: connection.execute(
            f"SELECT COUNT(*) FROM {table_name};"
        ).fetchone()[0]
        for table_name in DATASETS
    }


def count_duplicate_keys(
    connection: sqlite3.Connection,
    table_name: str,
    key_column: str,
) -> int:
    return connection.execute(
        f"""
        SELECT COUNT(*)
        FROM (
            SELECT
                {key_column}
            FROM {table_name}
            GROUP BY {key_column}
            HAVING COUNT(*) > 1
        );
        """
    ).fetchone()[0]


class DuplicateDeliveryIdempotencyTestCase(
    unittest.TestCase
):

    def test_production_renderer_resolves_all_placeholders(
        self,
    ) -> None:
        rendered_sql = render_incremental_sql()

        self.assertNotIn(
            "__INCREMENTAL_LOOKBACK_MINUTES__",
            rendered_sql,
        )

        self.assertNotIn(
            "__WATERMARK_FUTURE_TOLERANCE_MINUTES__",
            rendered_sql,
        )

    def test_duplicate_delivery_does_not_duplicate_core_rows(
        self,
    ) -> None:
        connection = create_test_database()

        try:
            seed_pipeline_watermarks(connection)

            # First delivery.
            seed_staging_from_real_csvs(
                connection,
                loaded_at="2026-08-18 12:00:00",
            )

            sql_text = render_incremental_sql()

            connection.executescript(sql_text)

            first_counts = get_core_counts(
                connection
            )

            self.assertEqual(
                first_counts,
                {
                    "customers": 5,
                    "products": 5,
                    "orders": 5,
                    "order_items": 7,
                    "payments": 5,
                },
            )

            # Duplicate delivery of the exact same source.
            # Use a later loaded_at so it is inside the
            # incremental window and must be processed again.
            seed_staging_from_real_csvs(
                connection,
                loaded_at="2026-08-18 12:01:00",
            )

            connection.executescript(sql_text)

            second_counts = get_core_counts(
                connection
            )

            self.assertEqual(
                second_counts,
                first_counts,
            )

            duplicate_checks = {
                "customers": "customer_id",
                "products": "product_id",
                "orders": "order_id",
                "order_items": "order_item_id",
                "payments": "payment_id",
            }

            for table_name, key_column in (
                duplicate_checks.items()
            ):
                self.assertEqual(
                    count_duplicate_keys(
                        connection,
                        table_name,
                        key_column,
                    ),
                    0,
                    msg=(
                        f"{table_name} contains "
                        f"duplicate {key_column} values"
                    ),
                )
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent

LOAD_RAW_DATA_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "02_load_raw_data.py"
)


def load_raw_data_module():
    spec = spec_from_file_location(
        "load_raw_data",
        LOAD_RAW_DATA_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load module: {LOAD_RAW_DATA_PATH}"
        )

    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


LOAD_RAW_DATA = load_raw_data_module()


class RawDataIngestionTestCase(unittest.TestCase):

    def test_missing_required_source_file_raises_file_not_found(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)

            existing_file = (
                temporary_path
                / "products.csv"
            )

            missing_file = (
                temporary_path
                / "customers.csv"
            )

            existing_file.write_text(
                "product_id,product_name`n1,Test Product`n",
                encoding="utf-8",
            )

            with self.assertRaises(FileNotFoundError) as context:
                LOAD_RAW_DATA.validate_required_files(
                    [
                        missing_file,
                        existing_file,
                    ]
                )

            error_message = str(context.exception)

            self.assertIn(
                str(missing_file),
                error_message,
            )

            self.assertNotIn(
                str(existing_file),
                error_message,
            )

    def test_schema_drift_missing_expected_column_raises_value_error(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)

            orders_file = (
                temporary_path
                / "orders.csv"
            )

            actual_columns = [
                "order_number",
                "customer_id",
                "order_date",
                "order_status",
            ]

            expected_columns = [
                "order_id",
                "customer_id",
                "order_date",
                "order_status",
            ]

            with self.assertRaises(ValueError) as context:
                LOAD_RAW_DATA.validate_csv_columns(
                    file_path=orders_file,
                    actual_columns=actual_columns,
                    expected_columns=expected_columns,
                )

            error_message = str(context.exception)

            self.assertIn(
                "orders.csv",
                error_message,
            )

            self.assertIn(
                "order_id",
                error_message,
            )


if __name__ == "__main__":
    unittest.main()

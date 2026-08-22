from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOAD_RAW_DATA_PATH = (
    PROJECT_ROOT
    / "scripts"
    / "02_load_raw_data.py"
)


def load_raw_data_module():
    spec = spec_from_file_location(
        "load_raw_data_structural_contract",
        LOAD_RAW_DATA_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Unable to load scripts/02_load_raw_data.py"
        )

    module = module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


class StructuralDataContractTestCase(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.load_raw_data = load_raw_data_module()

    def test_missing_required_column_is_rejected(
        self,
    ) -> None:
        file_path = Path("orders.csv")

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
            self.load_raw_data.validate_csv_columns(
                file_path=file_path,
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

    def test_unexpected_column_is_rejected(
        self,
    ) -> None:
        file_path = Path("orders.csv")

        actual_columns = [
            "order_id",
            "customer_id",
            "order_date",
            "order_status",
            "surprise_column",
        ]

        expected_columns = [
            "order_id",
            "customer_id",
            "order_date",
            "order_status",
        ]

        with self.assertRaises(ValueError) as context:
            self.load_raw_data.validate_csv_columns(
                file_path=file_path,
                actual_columns=actual_columns,
                expected_columns=expected_columns,
            )

        error_message = str(context.exception)

        self.assertIn(
            "orders.csv",
            error_message,
        )
        self.assertIn(
            "surprise_column",
            error_message,
        )

    def test_duplicate_header_is_rejected(
        self,
    ) -> None:
        file_path = Path("orders.csv")

        actual_columns = [
            "order_id",
            "customer_id",
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
            self.load_raw_data.validate_csv_columns(
                file_path=file_path,
                actual_columns=actual_columns,
                expected_columns=expected_columns,
            )

        error_message = str(context.exception)

        self.assertIn(
            "orders.csv",
            error_message,
        )
        self.assertIn(
            "customer_id",
            error_message,
        )

    def test_column_order_is_flexible(
        self,
    ) -> None:
        file_path = Path("orders.csv")

        actual_columns = [
            "order_status",
            "order_date",
            "customer_id",
            "order_id",
        ]

        expected_columns = [
            "order_id",
            "customer_id",
            "order_date",
            "order_status",
        ]

        self.load_raw_data.validate_csv_columns(
            file_path=file_path,
            actual_columns=actual_columns,
            expected_columns=expected_columns,
        )


if __name__ == "__main__":
    unittest.main()

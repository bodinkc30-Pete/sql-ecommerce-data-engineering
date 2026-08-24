from pathlib import Path
import importlib.util
import sqlite3
import tempfile
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SETUP_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "01_setup_database.py"


def load_setup_module():
    spec = importlib.util.spec_from_file_location(
        "setup_database_for_fresh_test",
        SETUP_SCRIPT_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"ไม่สามารถโหลด setup module ได้: {SETUP_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FreshDatabaseSetupTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_directory = tempfile.TemporaryDirectory()
        cls.test_database_path = (
            Path(cls.temp_directory.name)
            / "fresh_ecommerce_data_engineering.db"
        )

        cls.setup_module = load_setup_module()
        cls.original_database_path = cls.setup_module.DATABASE_PATH
        cls.setup_module.DATABASE_PATH = cls.test_database_path

        cls.setup_module.setup_database()

        if not cls.test_database_path.exists():
            raise AssertionError(
                "Fresh database setup did not create the expected database file."
            )

        cls.connection = sqlite3.connect(cls.test_database_path)
        cls.connection.execute("PRAGMA foreign_keys = ON;")

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "connection"):
            cls.connection.close()

        if hasattr(cls, "setup_module"):
            cls.setup_module.DATABASE_PATH = cls.original_database_path

        if hasattr(cls, "temp_directory"):
            cls.temp_directory.cleanup()

    def test_fresh_database_object_counts(self) -> None:
        table_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE
                type = 'table'
                AND name NOT LIKE 'sqlite_%';
            """
        ).fetchone()[0]

        view_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'view';
            """
        ).fetchone()[0]

        index_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE
                type = 'index'
                AND name NOT LIKE 'sqlite_%';
            """
        ).fetchone()[0]

        self.assertEqual(25, table_count)
        self.assertEqual(20, view_count)
        self.assertEqual(57, index_count)

    def test_fresh_governance_metadata_is_seeded(self) -> None:
        asset_count = self.connection.execute(
            "SELECT COUNT(*) FROM data_assets;"
        ).fetchone()[0]

        lineage_edge_count = self.connection.execute(
            "SELECT COUNT(*) FROM lineage_edges;"
        ).fetchone()[0]

        run_event_count = self.connection.execute(
            "SELECT COUNT(*) FROM lineage_run_events;"
        ).fetchone()[0]

        invalid_pii_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM data_assets
            WHERE
                contains_pii = 1
                AND classification NOT IN (
                    'CONFIDENTIAL',
                    'RESTRICTED'
                );
            """
        ).fetchone()[0]

        self.assertEqual(32, asset_count)
        self.assertEqual(34, lineage_edge_count)
        self.assertEqual(0, run_event_count)
        self.assertEqual(0, invalid_pii_count)

    def test_fresh_database_foreign_keys_are_clean(self) -> None:
        violations = self.connection.execute(
            "PRAGMA foreign_key_check;"
        ).fetchall()

        self.assertEqual([], violations)

    def test_fresh_recursive_lineage_is_correct(self) -> None:
        orders_upstream = self.connection.execute(
            """
            SELECT
                dependency_asset_name,
                depth,
                lineage_path
            FROM vw_asset_upstream_dependencies
            WHERE root_asset_name = 'orders'
            ORDER BY depth, dependency_asset_name;
            """
        ).fetchall()

        self.assertEqual(
            [
                ("stg_orders", 1, "orders <- stg_orders"),
                ("orders.csv", 2, "orders <- stg_orders <- orders.csv"),
            ],
            orders_upstream,
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_SCRIPT_PATH = PROJECT_ROOT / "scripts" / "05_run_pipeline.py"


def load_pipeline_module():
    spec = importlib.util.spec_from_file_location(
        "pipeline_runner_for_monitoring_schema_test",
        PIPELINE_SCRIPT_PATH,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load pipeline module: {PIPELINE_SCRIPT_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MonitoringSchemaContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pipeline_runner = load_pipeline_module()

    def setUp(self) -> None:
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temp_directory.name)
            / "monitoring_schema_test.db"
        )

        self.original_database_path = self.pipeline_runner.DATABASE_PATH
        self.pipeline_runner.DATABASE_PATH = self.database_path

    def tearDown(self) -> None:
        self.pipeline_runner.DATABASE_PATH = self.original_database_path
        self.temp_directory.cleanup()

    def create_tables(self, table_names: tuple[str, ...]) -> None:
        connection = sqlite3.connect(self.database_path)
        try:
            for table_name in table_names:
                connection.execute(
                    f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY);"
                )
            connection.commit()
        finally:
            connection.close()

    def test_monitoring_schema_requires_pipeline_alerts(self) -> None:
        self.create_tables(
            (
                "pipeline_audit",
                "pipeline_step_log",
                "pipeline_sla_metrics",
                "pipeline_alert_occurrences",
            )
        )

        self.assertFalse(
            self.pipeline_runner.monitoring_schema_available(),
            "Monitoring schema must be considered unavailable "
            "when pipeline_alerts is missing.",
        )

    def test_monitoring_schema_requires_pipeline_alert_occurrences(
        self,
    ) -> None:
        self.create_tables(
            (
                "pipeline_audit",
                "pipeline_step_log",
                "pipeline_sla_metrics",
                "pipeline_alerts",
            )
        )

        self.assertFalse(
            self.pipeline_runner.monitoring_schema_available(),
            "Monitoring schema must be considered unavailable "
            "when pipeline_alert_occurrences is missing.",
        )

    def test_monitoring_schema_is_available_when_all_required_tables_exist(
        self,
    ) -> None:
        self.create_tables(
            (
                "pipeline_audit",
                "pipeline_step_log",
                "pipeline_sla_metrics",
                "pipeline_alerts",
                "pipeline_alert_occurrences",
            )
        )

        self.assertTrue(
            self.pipeline_runner.monitoring_schema_available()
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_SCHEMA_PATH = PROJECT_ROOT / "schema" / "02_create_core_tables.sql"


def extract_table_definition(
    schema_text: str,
    table_name: str,
) -> str | None:
    pattern = re.compile(
        rf"""
        CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+
        {re.escape(table_name)}
        \s*\(
        (?P<body>.*?)
        \n\);
        """,
        flags=re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    match = pattern.search(schema_text)

    if match is None:
        return None

    return match.group(0)


class PipelineAlertSchemaTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.schema_text = CORE_SCHEMA_PATH.read_text(
            encoding="utf-8"
        )
        cls.alert_table_sql = extract_table_definition(
            cls.schema_text,
            "pipeline_alerts",
        )

    def require_alert_table(self) -> str:
        self.assertIsNotNone(
            self.alert_table_sql,
            "pipeline_alerts table definition is missing.",
        )

        assert self.alert_table_sql is not None
        return self.alert_table_sql

    def test_pipeline_alerts_table_exists(self) -> None:
        self.require_alert_table()

    def test_pipeline_alerts_has_required_columns(self) -> None:
        alert_table_sql = self.require_alert_table()

        required_columns = (
            "alert_id",
            "alert_key",
            "source_type",
            "alert_type",
            "severity",
            "status",
            "pipeline_name",
            "run_id",
            "step_name",
            "attempt_number",
            "title",
            "message",
            "first_detected_at",
            "last_detected_at",
            "occurrence_count",
            "acknowledged_at",
            "resolved_at",
            "created_at",
            "updated_at",
        )

        for column_name in required_columns:
            with self.subTest(column_name=column_name):
                self.assertRegex(
                    alert_table_sql,
                    rf"(?im)^\s*{re.escape(column_name)}\s+",
                )

    def test_pipeline_alerts_enforces_enum_contracts(self) -> None:
        alert_table_sql = self.require_alert_table()
        normalized_table_sql = alert_table_sql.upper()

        expected_values = (
            "ORCHESTRATOR",
            "QUALITY_GATE",
            "STEP_FAILURE",
            "SLA_BREACH",
            "DATA_QUALITY_WARNING",
            "DATA_QUALITY_FAILURE",
            "CRITICAL",
            "ERROR",
            "WARNING",
            "OPEN",
            "ACKNOWLEDGED",
            "RESOLVED",
        )

        for expected_value in expected_values:
            with self.subTest(expected_value=expected_value):
                self.assertIn(
                    f"'{expected_value}'",
                    normalized_table_sql,
                )

    def test_pipeline_alert_key_is_unique_for_deduplication(
        self,
    ) -> None:
        alert_table_sql = self.require_alert_table()

        inline_unique = re.search(
            r"(?im)^\s*alert_key\s+[^\n]*\bUNIQUE\b",
            alert_table_sql,
        )

        table_unique = re.search(
            r"(?is)UNIQUE\s*\(\s*alert_key\s*\)",
            alert_table_sql,
        )

        self.assertTrue(
            inline_unique or table_unique,
            "pipeline_alerts.alert_key must be UNIQUE "
            "to enforce durable alert deduplication.",
        )


if __name__ == "__main__":
    unittest.main()

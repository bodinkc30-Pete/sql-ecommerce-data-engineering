from __future__ import annotations

import re
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
INDEX_SCHEMA_PATH = PROJECT_ROOT / "schema" / "03_create_indexes.sql"


def normalize_identifier(value: str) -> str:
    return value.strip().lower()


def parse_index_definitions(sql: str) -> dict[str, tuple[str, tuple[str, ...]]]:
    pattern = re.compile(
        r"""
        CREATE\s+(?:UNIQUE\s+)?INDEX\s+
        (?P<index_name>[A-Za-z_][A-Za-z0-9_]*)\s+
        ON\s+
        (?P<table_name>[A-Za-z_][A-Za-z0-9_]*)\s*
        \(
            (?P<columns>[^)]+)
        \)\s*;
        """,
        re.IGNORECASE | re.VERBOSE | re.DOTALL,
    )

    definitions: dict[str, tuple[str, tuple[str, ...]]] = {}

    for match in pattern.finditer(sql):
        index_name = normalize_identifier(match.group("index_name"))
        table_name = normalize_identifier(match.group("table_name"))
        columns = tuple(
            normalize_identifier(column)
            for column in match.group("columns").split(",")
        )

        definitions[index_name] = (table_name, columns)

    return definitions


class AlertIndexContractTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sql = INDEX_SCHEMA_PATH.read_text(encoding="utf-8")
        cls.index_definitions = parse_index_definitions(sql)

    def assert_index_definition(
        self,
        *,
        index_name: str,
        table_name: str,
        columns: tuple[str, ...],
    ) -> None:
        normalized_index_name = normalize_identifier(index_name)
        expected = (
            normalize_identifier(table_name),
            tuple(normalize_identifier(column) for column in columns),
        )

        self.assertIn(
            normalized_index_name,
            self.index_definitions,
            f"Missing operational alert index {index_name}.",
        )

        self.assertEqual(
            self.index_definitions[normalized_index_name],
            expected,
            (
                f"Index {index_name} has the wrong table/column contract. "
                f"Expected {expected}, "
                f"found {self.index_definitions[normalized_index_name]}."
            ),
        )

    def test_open_alert_queue_has_operational_index(self) -> None:
        self.assert_index_definition(
            index_name=(
                "idx_pipeline_alerts_status_severity_last_detected"
            ),
            table_name="pipeline_alerts",
            columns=(
                "status",
                "severity",
                "last_detected_at",
            ),
        )

    def test_alert_source_type_filter_has_operational_index(self) -> None:
        self.assert_index_definition(
            index_name=(
                "idx_pipeline_alerts_source_type_alert_type_detected"
            ),
            table_name="pipeline_alerts",
            columns=(
                "source_type",
                "alert_type",
                "last_detected_at",
            ),
        )

    def test_occurrence_run_lookup_has_operational_index(self) -> None:
        self.assert_index_definition(
            index_name="idx_pipeline_alert_occurrences_run_id",
            table_name="pipeline_alert_occurrences",
            columns=("run_id",),
        )

    def test_occurrence_history_has_operational_index(self) -> None:
        self.assert_index_definition(
            index_name=(
                "idx_pipeline_alert_occurrences_alert_detected"
            ),
            table_name="pipeline_alert_occurrences",
            columns=(
                "alert_id",
                "detected_at",
            ),
        )


if __name__ == "__main__":
    unittest.main()

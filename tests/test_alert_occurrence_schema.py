from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_SCHEMA_PATH = PROJECT_ROOT / "schema" / "02_create_core_tables.sql"


class AlertOccurrenceSchemaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.execute("PRAGMA foreign_keys = ON;")
        self.connection.executescript(
            CORE_SCHEMA_PATH.read_text(encoding="utf-8")
        )

    def tearDown(self) -> None:
        self.connection.close()

    def table_exists(self, table_name: str) -> bool:
        row = self.connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = ?;
            """,
            (table_name,),
        ).fetchone()
        return row is not None

    def table_columns(self, table_name: str) -> set[str]:
        rows = self.connection.execute(
            f"PRAGMA table_info({table_name});"
        ).fetchall()
        return {row[1] for row in rows}

    def test_pipeline_alerts_has_stable_fingerprint_column(self) -> None:
        columns = self.table_columns("pipeline_alerts")

        self.assertIn(
            "alert_fingerprint",
            columns,
            "pipeline_alerts must store a stable cross-run fingerprint.",
        )

    def test_pipeline_alert_occurrences_table_exists(self) -> None:
        self.assertTrue(
            self.table_exists("pipeline_alert_occurrences"),
            "pipeline_alert_occurrences table is missing.",
        )

    def test_pipeline_alert_occurrences_has_required_columns(self) -> None:
        required_columns = {
            "occurrence_id",
            "alert_id",
            "run_id",
            "attempt_number",
            "detected_at",
            "error_type",
            "raw_error_message",
            "normalized_error_signature",
            "created_at",
        }

        columns = self.table_columns("pipeline_alert_occurrences")

        self.assertTrue(
            required_columns.issubset(columns),
            (
                "pipeline_alert_occurrences is missing required columns: "
                f"{sorted(required_columns - columns)}"
            ),
        )

    def test_occurrence_alert_id_references_pipeline_alerts(self) -> None:
        foreign_keys = self.connection.execute(
            "PRAGMA foreign_key_list(pipeline_alert_occurrences);"
        ).fetchall()

        references_pipeline_alerts = any(
            row[2] == "pipeline_alerts"
            and row[3] == "alert_id"
            and row[4] == "alert_id"
            for row in foreign_keys
        )

        self.assertTrue(
            references_pipeline_alerts,
            (
                "pipeline_alert_occurrences.alert_id must reference "
                "pipeline_alerts.alert_id."
            ),
        )

    def test_alert_fingerprint_is_unique(self) -> None:
        index_rows = self.connection.execute(
            "PRAGMA index_list(pipeline_alerts);"
        ).fetchall()

        unique_index_names = [
            row[1]
            for row in index_rows
            if row[2] == 1
        ]

        fingerprint_is_unique = False

        for index_name in unique_index_names:
            columns = self.connection.execute(
                f"PRAGMA index_info({index_name});"
            ).fetchall()
            indexed_columns = [row[2] for row in columns]

            if indexed_columns == ["alert_fingerprint"]:
                fingerprint_is_unique = True
                break

        self.assertTrue(
            fingerprint_is_unique,
            "pipeline_alerts.alert_fingerprint must be UNIQUE.",
        )


if __name__ == "__main__":
    unittest.main()

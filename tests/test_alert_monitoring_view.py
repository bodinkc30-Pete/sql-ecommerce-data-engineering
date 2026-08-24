from __future__ import annotations

import re
import sqlite3
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
VIEW_SCHEMA_PATH = PROJECT_ROOT / "schema" / "04_create_views.sql"
VIEW_NAME = "vw_pipeline_alert_monitoring"


def read_view_schema() -> str:
    return VIEW_SCHEMA_PATH.read_text(encoding="utf-8")


def extract_alert_monitoring_view_sql(sql: str) -> str | None:
    match = re.search(
        rf"""
        CREATE\s+VIEW\s+{VIEW_NAME}\s+AS
        \b
        .*?
        ;
        """,
        sql,
        flags=re.IGNORECASE | re.VERBOSE | re.DOTALL,
    )

    if match is None:
        return None

    return match.group(0)


def create_alert_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE pipeline_alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_key TEXT NOT NULL UNIQUE,
            alert_fingerprint TEXT UNIQUE,
            source_type TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN',
            pipeline_name TEXT NOT NULL,
            run_id TEXT NOT NULL,
            step_name TEXT NOT NULL,
            attempt_number INTEGER NOT NULL DEFAULT 1,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            first_detected_at TEXT NOT NULL,
            last_detected_at TEXT NOT NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            acknowledged_at TEXT,
            resolved_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE pipeline_alert_occurrences (
            occurrence_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_id INTEGER NOT NULL,
            run_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL DEFAULT 1,
            detected_at TEXT NOT NULL,
            error_type TEXT,
            raw_error_message TEXT,
            normalized_error_signature TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (alert_id)
                REFERENCES pipeline_alerts(alert_id)
                ON DELETE CASCADE
        );
        """
    )


def insert_alert(
    connection: sqlite3.Connection,
    *,
    alert_key: str,
    fingerprint: str,
    severity: str,
    status: str,
    run_id: str,
    occurrence_count: int,
    acknowledged_at: str | None = None,
    resolved_at: str | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO pipeline_alerts (
            alert_key,
            alert_fingerprint,
            source_type,
            alert_type,
            severity,
            status,
            pipeline_name,
            run_id,
            step_name,
            attempt_number,
            title,
            message,
            first_detected_at,
            last_detected_at,
            occurrence_count,
            acknowledged_at,
            resolved_at,
            created_at,
            updated_at
        )
        VALUES (
            ?,
            ?,
            'QUALITY_GATE',
            'DATA_QUALITY_FAILURE',
            ?,
            ?,
            'ecommerce_quality_check_pipeline',
            ?,
            '03_referential_integrity',
            1,
            'Monitoring view test alert',
            'Controlled monitoring-view test alert',
            '2026-08-24 03:00:00',
            '2026-08-24 03:05:00',
            ?,
            ?,
            ?,
            '2026-08-24 03:00:00',
            '2026-08-24 03:05:00'
        );
        """,
        (
            alert_key,
            fingerprint,
            severity,
            status,
            run_id,
            occurrence_count,
            acknowledged_at,
            resolved_at,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


def insert_occurrence(
    connection: sqlite3.Connection,
    *,
    alert_id: int,
    run_id: str,
    attempt_number: int,
    detected_at: str,
    error_type: str,
    raw_error_message: str,
    normalized_error_signature: str,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO pipeline_alert_occurrences (
            alert_id,
            run_id,
            attempt_number,
            detected_at,
            error_type,
            raw_error_message,
            normalized_error_signature
        )
        VALUES (?, ?, ?, ?, ?, ?, ?);
        """,
        (
            alert_id,
            run_id,
            attempt_number,
            detected_at,
            error_type,
            raw_error_message,
            normalized_error_signature,
        ),
    )
    connection.commit()
    return int(cursor.lastrowid)


VIEW_SCHEMA_SQL = read_view_schema()
ALERT_MONITORING_VIEW_SQL = extract_alert_monitoring_view_sql(
    VIEW_SCHEMA_SQL
)


class AlertMonitoringViewContractTestCase(unittest.TestCase):
    def test_alert_monitoring_view_exists(self) -> None:
        self.assertIsNotNone(
            ALERT_MONITORING_VIEW_SQL,
            (
                "Missing CREATE VIEW vw_pipeline_alert_monitoring. "
                "Alert monitoring serving view is not implemented yet."
            ),
        )


@unittest.skipUnless(
    ALERT_MONITORING_VIEW_SQL is not None,
    "Alert monitoring view has not been implemented yet.",
)
class AlertMonitoringViewRuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        create_alert_tables(self.connection)
        self.connection.executescript(
            str(ALERT_MONITORING_VIEW_SQL)
        )

    def tearDown(self) -> None:
        self.connection.close()

    def test_view_exposes_operational_columns(self) -> None:
        columns = {
            row["name"]
            for row in self.connection.execute(
                f"PRAGMA table_info({VIEW_NAME});"
            ).fetchall()
        }

        required_columns = {
            "alert_id",
            "alert_fingerprint",
            "source_type",
            "alert_type",
            "severity",
            "severity_priority",
            "status",
            "status_priority",
            "is_active",
            "pipeline_name",
            "alert_run_id",
            "step_name",
            "alert_attempt_number",
            "title",
            "message",
            "first_detected_at",
            "last_detected_at",
            "occurrence_count",
            "acknowledged_at",
            "resolved_at",
            "created_at",
            "updated_at",
            "latest_occurrence_id",
            "latest_occurrence_run_id",
            "latest_occurrence_attempt_number",
            "latest_occurrence_detected_at",
            "latest_error_type",
            "latest_raw_error_message",
            "latest_normalized_error_signature",
        }

        self.assertTrue(
            required_columns.issubset(columns),
            (
                "Alert monitoring view is missing required "
                f"operational columns: "
                f"{sorted(required_columns - columns)}"
            ),
        )

    def test_view_returns_one_row_per_alert_with_latest_occurrence(self) -> None:
        alert_id = insert_alert(
            self.connection,
            alert_key="latest-occurrence-alert",
            fingerprint="latest-occurrence-fingerprint",
            severity="CRITICAL",
            status="OPEN",
            run_id="first-alert-run",
            occurrence_count=2,
        )

        first_occurrence_id = insert_occurrence(
            self.connection,
            alert_id=alert_id,
            run_id="occurrence-run-01",
            attempt_number=1,
            detected_at="2026-08-24 03:01:00",
            error_type="DataQualityCriticalFailure",
            raw_error_message="first raw error",
            normalized_error_signature="signature-one",
        )

        latest_occurrence_id = insert_occurrence(
            self.connection,
            alert_id=alert_id,
            run_id="occurrence-run-02",
            attempt_number=2,
            detected_at="2026-08-24 03:04:00",
            error_type="DataQualityCriticalFailure",
            raw_error_message="latest raw error",
            normalized_error_signature="signature-two",
        )

        rows = self.connection.execute(
            f"""
            SELECT *
            FROM {VIEW_NAME}
            WHERE alert_id = ?;
            """,
            (alert_id,),
        ).fetchall()

        self.assertEqual(1, len(rows))

        row = rows[0]

        self.assertNotEqual(
            first_occurrence_id,
            row["latest_occurrence_id"],
        )
        self.assertEqual(
            latest_occurrence_id,
            row["latest_occurrence_id"],
        )
        self.assertEqual(
            "occurrence-run-02",
            row["latest_occurrence_run_id"],
        )
        self.assertEqual(
            2,
            row["latest_occurrence_attempt_number"],
        )
        self.assertEqual(
            "2026-08-24 03:04:00",
            row["latest_occurrence_detected_at"],
        )
        self.assertEqual(
            "latest raw error",
            row["latest_raw_error_message"],
        )
        self.assertEqual(
            "signature-two",
            row["latest_normalized_error_signature"],
        )

    def test_view_exposes_status_and_severity_priority(self) -> None:
        open_critical_id = insert_alert(
            self.connection,
            alert_key="open-critical-alert",
            fingerprint="open-critical-fingerprint",
            severity="CRITICAL",
            status="OPEN",
            run_id="open-critical-run",
            occurrence_count=1,
        )

        resolved_warning_id = insert_alert(
            self.connection,
            alert_key="resolved-warning-alert",
            fingerprint="resolved-warning-fingerprint",
            severity="WARNING",
            status="RESOLVED",
            run_id="resolved-warning-run",
            occurrence_count=1,
            acknowledged_at="2026-08-24 03:06:00",
            resolved_at="2026-08-24 03:07:00",
        )

        rows = {
            row["alert_id"]: row
            for row in self.connection.execute(
                f"""
                SELECT
                    alert_id,
                    severity_priority,
                    status_priority,
                    is_active,
                    acknowledged_at,
                    resolved_at
                FROM {VIEW_NAME}
                WHERE alert_id IN (?, ?);
                """,
                (
                    open_critical_id,
                    resolved_warning_id,
                ),
            ).fetchall()
        }

        open_row = rows[open_critical_id]
        resolved_row = rows[resolved_warning_id]

        self.assertEqual(1, open_row["severity_priority"])
        self.assertEqual(1, open_row["status_priority"])
        self.assertEqual(1, open_row["is_active"])
        self.assertIsNone(open_row["acknowledged_at"])
        self.assertIsNone(open_row["resolved_at"])

        self.assertEqual(3, resolved_row["severity_priority"])
        self.assertEqual(3, resolved_row["status_priority"])
        self.assertEqual(0, resolved_row["is_active"])
        self.assertEqual(
            "2026-08-24 03:06:00",
            resolved_row["acknowledged_at"],
        )
        self.assertEqual(
            "2026-08-24 03:07:00",
            resolved_row["resolved_at"],
        )

    def test_alert_without_occurrence_is_still_visible(self) -> None:
        alert_id = insert_alert(
            self.connection,
            alert_key="no-occurrence-alert",
            fingerprint="no-occurrence-fingerprint",
            severity="ERROR",
            status="ACKNOWLEDGED",
            run_id="no-occurrence-run",
            occurrence_count=1,
            acknowledged_at="2026-08-24 03:08:00",
        )

        row = self.connection.execute(
            f"""
            SELECT
                alert_id,
                status,
                latest_occurrence_id,
                latest_occurrence_run_id,
                latest_occurrence_detected_at
            FROM {VIEW_NAME}
            WHERE alert_id = ?;
            """,
            (alert_id,),
        ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual("ACKNOWLEDGED", row["status"])
        self.assertIsNone(row["latest_occurrence_id"])
        self.assertIsNone(row["latest_occurrence_run_id"])
        self.assertIsNone(row["latest_occurrence_detected_at"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

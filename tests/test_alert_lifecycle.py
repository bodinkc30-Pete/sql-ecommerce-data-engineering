from __future__ import annotations

import importlib.util
import sqlite3
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALERT_MANAGER_PATH = PROJECT_ROOT / "scripts" / "07_manage_alerts.py"


def load_alert_manager():
    spec = importlib.util.spec_from_file_location(
        "alert_manager_module",
        ALERT_MANAGER_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Unable to load alert manager: {ALERT_MANAGER_PATH}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def create_alert_table(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE pipeline_alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            alert_key TEXT NOT NULL UNIQUE,
            alert_fingerprint TEXT UNIQUE,
            source_type TEXT NOT NULL,
            alert_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'OPEN'
                CHECK (
                    status IN (
                        'OPEN',
                        'ACKNOWLEDGED',
                        'RESOLVED'
                    )
                ),
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
        """
    )


def insert_open_alert(connection: sqlite3.Connection) -> int:
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
            occurrence_count
        )
        VALUES (
            'alert-lifecycle-key',
            'alert-lifecycle-fingerprint',
            'QUALITY_GATE',
            'DATA_QUALITY_FAILURE',
            'CRITICAL',
            'OPEN',
            'ecommerce_quality_check_pipeline',
            'alert-lifecycle-run',
            '03_referential_integrity',
            1,
            'Lifecycle test alert',
            'Controlled lifecycle test alert',
            '2026-08-24 03:10:00',
            '2026-08-24 03:10:00',
            1
        );
        """
    )
    connection.commit()
    return int(cursor.lastrowid)


class AlertLifecycleScriptContractTestCase(unittest.TestCase):
    def test_alert_manager_script_exists(self) -> None:
        self.assertTrue(
            ALERT_MANAGER_PATH.exists(),
            (
                "Missing scripts/07_manage_alerts.py. "
                "Alert lifecycle management is not implemented yet."
            ),
        )


@unittest.skipUnless(
    ALERT_MANAGER_PATH.exists(),
    "Alert manager production script has not been implemented yet.",
)
class AlertLifecycleRuntimeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.module = load_alert_manager()
        self.connection = sqlite3.connect(":memory:")
        self.connection.row_factory = sqlite3.Row
        create_alert_table(self.connection)
        self.alert_id = insert_open_alert(self.connection)

    def tearDown(self) -> None:
        self.connection.close()

    def read_alert(self) -> sqlite3.Row:
        row = self.connection.execute(
            """
            SELECT
                alert_id,
                status,
                acknowledged_at,
                resolved_at,
                updated_at
            FROM pipeline_alerts
            WHERE alert_id = ?;
            """,
            (self.alert_id,),
        ).fetchone()

        if row is None:
            raise AssertionError("Test alert disappeared unexpectedly.")

        return row

    def test_open_alert_can_be_acknowledged(self) -> None:
        changed_at = "2026-08-24 03:11:00"

        result = self.module.acknowledge_alert(
            self.connection,
            self.alert_id,
            changed_at=changed_at,
        )

        row = self.read_alert()

        self.assertTrue(result["changed"])
        self.assertEqual("OPEN", result["previous_status"])
        self.assertEqual("ACKNOWLEDGED", result["status"])
        self.assertEqual("ACKNOWLEDGED", row["status"])
        self.assertEqual(changed_at, row["acknowledged_at"])
        self.assertIsNone(row["resolved_at"])
        self.assertEqual(changed_at, row["updated_at"])

    def test_acknowledge_is_idempotent_and_preserves_timestamp(self) -> None:
        first_acknowledged_at = "2026-08-24 03:11:00"

        self.module.acknowledge_alert(
            self.connection,
            self.alert_id,
            changed_at=first_acknowledged_at,
        )

        result = self.module.acknowledge_alert(
            self.connection,
            self.alert_id,
            changed_at="2026-08-24 03:12:00",
        )

        row = self.read_alert()

        self.assertFalse(result["changed"])
        self.assertEqual("ACKNOWLEDGED", result["status"])
        self.assertEqual(
            first_acknowledged_at,
            row["acknowledged_at"],
        )
        self.assertEqual(
            first_acknowledged_at,
            row["updated_at"],
        )

    def test_acknowledged_alert_can_be_resolved(self) -> None:
        acknowledged_at = "2026-08-24 03:11:00"
        resolved_at = "2026-08-24 03:13:00"

        self.module.acknowledge_alert(
            self.connection,
            self.alert_id,
            changed_at=acknowledged_at,
        )

        result = self.module.resolve_alert(
            self.connection,
            self.alert_id,
            changed_at=resolved_at,
        )

        row = self.read_alert()

        self.assertTrue(result["changed"])
        self.assertEqual(
            "ACKNOWLEDGED",
            result["previous_status"],
        )
        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual("RESOLVED", row["status"])
        self.assertEqual(
            acknowledged_at,
            row["acknowledged_at"],
        )
        self.assertEqual(resolved_at, row["resolved_at"])
        self.assertEqual(resolved_at, row["updated_at"])

    def test_resolve_is_idempotent_and_preserves_timestamp(self) -> None:
        resolved_at = "2026-08-24 03:13:00"

        self.module.acknowledge_alert(
            self.connection,
            self.alert_id,
            changed_at="2026-08-24 03:11:00",
        )
        self.module.resolve_alert(
            self.connection,
            self.alert_id,
            changed_at=resolved_at,
        )

        result = self.module.resolve_alert(
            self.connection,
            self.alert_id,
            changed_at="2026-08-24 03:14:00",
        )

        row = self.read_alert()

        self.assertFalse(result["changed"])
        self.assertEqual("RESOLVED", result["status"])
        self.assertEqual(resolved_at, row["resolved_at"])
        self.assertEqual(resolved_at, row["updated_at"])

    def test_open_alert_cannot_skip_acknowledgement(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "ACKNOWLEDGED",
        ):
            self.module.resolve_alert(
                self.connection,
                self.alert_id,
                changed_at="2026-08-24 03:13:00",
            )

        row = self.read_alert()

        self.assertEqual("OPEN", row["status"])
        self.assertIsNone(row["acknowledged_at"])
        self.assertIsNone(row["resolved_at"])

    def test_resolved_alert_cannot_move_back_to_acknowledged(self) -> None:
        self.module.acknowledge_alert(
            self.connection,
            self.alert_id,
            changed_at="2026-08-24 03:11:00",
        )
        self.module.resolve_alert(
            self.connection,
            self.alert_id,
            changed_at="2026-08-24 03:13:00",
        )

        with self.assertRaisesRegex(
            ValueError,
            "RESOLVED",
        ):
            self.module.acknowledge_alert(
                self.connection,
                self.alert_id,
                changed_at="2026-08-24 03:15:00",
            )

        row = self.read_alert()
        self.assertEqual("RESOLVED", row["status"])

    def test_unknown_alert_id_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "not found",
        ):
            self.module.acknowledge_alert(
                self.connection,
                999999,
                changed_at="2026-08-24 03:11:00",
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)

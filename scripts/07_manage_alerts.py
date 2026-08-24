from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)


def utc_timestamp() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def _validate_alert_id(alert_id: int) -> int:
    if isinstance(alert_id, bool) or not isinstance(alert_id, int):
        raise ValueError("alert_id must be an integer.")

    if alert_id <= 0:
        raise ValueError("alert_id must be greater than 0.")

    return alert_id


def _fetch_alert(
    connection: sqlite3.Connection,
    alert_id: int,
) -> sqlite3.Row:
    original_row_factory = connection.row_factory
    connection.row_factory = sqlite3.Row

    try:
        row = connection.execute(
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
            (alert_id,),
        ).fetchone()
    finally:
        connection.row_factory = original_row_factory

    if row is None:
        raise ValueError(
            f"Alert id={alert_id} not found."
        )

    return row


def _build_result(
    *,
    alert_id: int,
    changed: bool,
    previous_status: str,
    status: str,
    acknowledged_at: str | None,
    resolved_at: str | None,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "alert_id": alert_id,
        "changed": changed,
        "previous_status": previous_status,
        "status": status,
        "acknowledged_at": acknowledged_at,
        "resolved_at": resolved_at,
        "updated_at": updated_at,
    }


def acknowledge_alert(
    connection: sqlite3.Connection,
    alert_id: int,
    *,
    changed_at: str | None = None,
) -> dict[str, Any]:
    alert_id = _validate_alert_id(alert_id)
    row = _fetch_alert(connection, alert_id)

    status = str(row["status"])

    if status == "ACKNOWLEDGED":
        return _build_result(
            alert_id=alert_id,
            changed=False,
            previous_status=status,
            status=status,
            acknowledged_at=row["acknowledged_at"],
            resolved_at=row["resolved_at"],
            updated_at=str(row["updated_at"]),
        )

    if status == "RESOLVED":
        raise ValueError(
            (
                f"Alert id={alert_id} is RESOLVED and cannot "
                "move back to ACKNOWLEDGED."
            )
        )

    if status != "OPEN":
        raise ValueError(
            (
                f"Alert id={alert_id} has unsupported status "
                f"{status!r}."
            )
        )

    acknowledged_at = changed_at or utc_timestamp()

    cursor = connection.execute(
        """
        UPDATE pipeline_alerts
        SET
            status = 'ACKNOWLEDGED',
            acknowledged_at = ?,
            updated_at = ?
        WHERE
            alert_id = ?
            AND status = 'OPEN';
        """,
        (
            acknowledged_at,
            acknowledged_at,
            alert_id,
        ),
    )

    if cursor.rowcount != 1:
        connection.rollback()
        latest = _fetch_alert(connection, alert_id)
        raise RuntimeError(
            (
                f"Alert id={alert_id} changed concurrently. "
                f"Current status={latest['status']}."
            )
        )

    connection.commit()

    return _build_result(
        alert_id=alert_id,
        changed=True,
        previous_status="OPEN",
        status="ACKNOWLEDGED",
        acknowledged_at=acknowledged_at,
        resolved_at=None,
        updated_at=acknowledged_at,
    )


def resolve_alert(
    connection: sqlite3.Connection,
    alert_id: int,
    *,
    changed_at: str | None = None,
) -> dict[str, Any]:
    alert_id = _validate_alert_id(alert_id)
    row = _fetch_alert(connection, alert_id)

    status = str(row["status"])

    if status == "RESOLVED":
        return _build_result(
            alert_id=alert_id,
            changed=False,
            previous_status=status,
            status=status,
            acknowledged_at=row["acknowledged_at"],
            resolved_at=row["resolved_at"],
            updated_at=str(row["updated_at"]),
        )

    if status == "OPEN":
        raise ValueError(
            (
                f"Alert id={alert_id} must be ACKNOWLEDGED "
                "before it can be RESOLVED."
            )
        )

    if status != "ACKNOWLEDGED":
        raise ValueError(
            (
                f"Alert id={alert_id} has unsupported status "
                f"{status!r}."
            )
        )

    resolved_at = changed_at or utc_timestamp()

    cursor = connection.execute(
        """
        UPDATE pipeline_alerts
        SET
            status = 'RESOLVED',
            resolved_at = ?,
            updated_at = ?
        WHERE
            alert_id = ?
            AND status = 'ACKNOWLEDGED';
        """,
        (
            resolved_at,
            resolved_at,
            alert_id,
        ),
    )

    if cursor.rowcount != 1:
        connection.rollback()
        latest = _fetch_alert(connection, alert_id)
        raise RuntimeError(
            (
                f"Alert id={alert_id} changed concurrently. "
                f"Current status={latest['status']}."
            )
        )

    connection.commit()

    return _build_result(
        alert_id=alert_id,
        changed=True,
        previous_status="ACKNOWLEDGED",
        status="RESOLVED",
        acknowledged_at=row["acknowledged_at"],
        resolved_at=resolved_at,
        updated_at=resolved_at,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Manage pipeline alert lifecycle transitions."
        )
    )
    parser.add_argument(
        "action",
        choices=("acknowledge", "resolve"),
        help=(
            "Lifecycle transition to perform."
        ),
    )
    parser.add_argument(
        "alert_id",
        type=int,
        help="pipeline_alerts.alert_id to update.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=DATABASE_PATH,
        help=(
            "SQLite database path. Defaults to the Project 01 "
            "database."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    database_path = args.database.resolve()

    if not database_path.exists():
        print(
            f"[ALERT ERROR] Database not found: "
            f"{database_path}"
        )
        return 1

    connection = sqlite3.connect(database_path)

    try:
        if args.action == "acknowledge":
            result = acknowledge_alert(
                connection,
                args.alert_id,
            )
        else:
            result = resolve_alert(
                connection,
                args.alert_id,
            )
    except (ValueError, RuntimeError, sqlite3.Error) as exc:
        print(
            f"[ALERT ERROR] "
            f"{type(exc).__name__}: {exc}"
        )
        return 1
    finally:
        connection.close()

    if result["changed"]:
        print(
            "[ALERT UPDATED] "
            f"alert_id={result['alert_id']} "
            f"{result['previous_status']} -> "
            f"{result['status']}"
        )
    else:
        print(
            "[ALERT NO-OP] "
            f"alert_id={result['alert_id']} "
            f"already {result['status']}"
        )

    print(
        f"acknowledged_at={result['acknowledged_at']}"
    )
    print(
        f"resolved_at={result['resolved_at']}"
    )
    print(
        f"updated_at={result['updated_at']}"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

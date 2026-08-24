import argparse
import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = PROJECT_ROOT / "config" / "pipeline_config.json"
SCRIPTS_DIRECTORY = PROJECT_ROOT / "scripts"
DATABASE_PATH = PROJECT_ROOT / "database" / "ecommerce_data_engineering.db"
PIPELINE_NAME = "hybrid_ecommerce_data_pipeline"
LOG_DIRECTORY = PROJECT_ROOT / "logs"
PIPELINE_LOG_PATH = LOG_DIRECTORY / "pipeline.log"

DATABASE_RETRY_MAX_ATTEMPTS = 2
DATABASE_RETRY_DELAY_SECONDS = 2.0
RETRYABLE_ERROR_PATTERNS = (
    "database is locked",
    "database is busy",
    "temporarily unavailable",
    "temporary failure",
    "timed out",
    "timeout",
)


PIPELINE_STEPS = [
    {
        "step_number": 1,
        "step_name": "SETUP_DATABASE",
        "script_name": "01_setup_database.py",
        "description": "สร้างตาราง Index และ View ในฐานข้อมูล SQLite",
    },
    {
        "step_number": 2,
        "step_name": "LOAD_RAW_DATA",
        "script_name": "02_load_raw_data.py",
        "description": "โหลดข้อมูลต้นทางเข้าสู่ Staging ตาม Pipeline Mode",
    },
    {
        "step_number": 3,
        "step_name": "RUN_TRANSFORMATIONS",
        "script_name": "03_run_transformations.py",
        "description": "ทำความสะอาด ตรวจสอบ และโหลดข้อมูลเข้าสู่ Core Tables",
    },
    {
        "step_number": 4,
        "step_name": "RUN_QUALITY_CHECKS",
        "script_name": "04_run_quality_checks.py",
        "description": "ตรวจ Null, Duplicate, Foreign Key, Reconciliation และ Business Rules",
    },
]


STAGING_TABLES = [
    "stg_customers",
    "stg_products",
    "stg_orders",
    "stg_order_items",
    "stg_payments",
    "stg_influencer_payments",
]

QUALITY_SCOPE_TABLES = [
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
    "campaigns",
    "influencers",
    "influencer_payments",
]


def current_utc_time() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def read_pipeline_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"ไม่พบไฟล์ Config: {CONFIG_PATH}")

    with CONFIG_PATH.open(mode="r", encoding="utf-8") as config_file:
        return json.load(config_file)


def get_pipeline_mode(config: dict[str, Any]) -> str:
    pipeline_mode = str(
        config.get("pipeline", {}).get("mode", "hybrid")
    ).strip().lower()

    allowed_modes = {"demo", "hybrid"}
    if pipeline_mode not in allowed_modes:
        allowed_mode_text = ", ".join(sorted(allowed_modes))
        raise ValueError(
            "ค่า pipeline.mode ไม่ถูกต้อง: "
            f"{pipeline_mode}. ค่าที่รองรับคือ: {allowed_mode_text}"
        )

    return pipeline_mode


def get_monitoring_config(
    config: dict[str, Any],
) -> tuple[bool, dict[str, float]]:
    monitoring_config = config.get("monitoring", {})
    sla_enabled = bool(monitoring_config.get("sla_enabled", False))
    raw_step_sla_seconds = monitoring_config.get("step_sla_seconds", {})

    if not isinstance(raw_step_sla_seconds, dict):
        raise ValueError("monitoring.step_sla_seconds ต้องเป็น JSON object")

    step_sla_seconds: dict[str, float] = {}
    for step_name, threshold_value in raw_step_sla_seconds.items():
        try:
            threshold_seconds = float(threshold_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"ค่า SLA ของ Step {step_name} ต้องเป็นตัวเลข"
            ) from error

        if threshold_seconds <= 0:
            raise ValueError(f"ค่า SLA ของ Step {step_name} ต้องมากกว่า 0")

        step_sla_seconds[str(step_name)] = threshold_seconds

    if sla_enabled:
        required_step_names = {step["step_name"] for step in PIPELINE_STEPS}
        missing_sla_steps = required_step_names - set(step_sla_seconds)
        if missing_sla_steps:
            raise ValueError(
                "เปิด SLA Monitoring แล้ว แต่ไม่มีค่า SLA สำหรับ Step: "
                f"{sorted(missing_sla_steps)}"
            )

    return sla_enabled, step_sla_seconds


def ensure_required_directories() -> None:
    required_directories = [
        PROJECT_ROOT / "database",
        PROJECT_ROOT / "logs",
        PROJECT_ROOT / "data" / "staging",
        PROJECT_ROOT / "data" / "processed",
    ]

    for directory_path in required_directories:
        directory_path.mkdir(parents=True, exist_ok=True)


def write_log(message: str) -> None:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    log_message = f"{current_utc_time()} | {message}\n"
    with PIPELINE_LOG_PATH.open(mode="a", encoding="utf-8") as log_file:
        log_file.write(log_message)


def print_separator() -> None:
    print("=" * 70)


def validate_script_exists(script_path: Path) -> None:
    if not script_path.exists():
        raise FileNotFoundError(f"ไม่พบ Script: {script_path}")


def is_retryable_error(error: Exception) -> bool:
    error_text = str(error).lower()
    return any(
        pattern in error_text
        for pattern in RETRYABLE_ERROR_PATTERNS
    )


def run_database_operation_with_retry(
    operation_name: str,
    operation: Callable[[], Any],
    run_id: str,
    max_attempts: int = DATABASE_RETRY_MAX_ATTEMPTS,
    retry_delay_seconds: float = DATABASE_RETRY_DELAY_SECONDS,
) -> Any:
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")

    for attempt_number in range(1, max_attempts + 1):
        try:
            return operation()

        except Exception as error:
            if not is_retryable_error(error):
                print(
                    f"[DB NO RETRY] {operation_name} | "
                    "error is not retryable"
                )
                raise

            if attempt_number >= max_attempts:
                print(
                    f"[DB RETRY EXHAUSTED] {operation_name} | "
                    f"attempts={max_attempts}"
                )
                write_log(
                    f"DB RETRY EXHAUSTED | {operation_name} | "
                    f"run_id={run_id} | attempts={max_attempts} | "
                    f"error={error}"
                )
                raise

            print(
                f"[DB RETRY] {operation_name} | "
                f"attempt {attempt_number} failed | "
                f"retrying as attempt {attempt_number + 1} "
                f"in {retry_delay_seconds:.0f} seconds"
            )
            write_log(
                f"DB RETRY SCHEDULED | {operation_name} | "
                f"run_id={run_id} | "
                f"failed_attempt={attempt_number} | "
                f"next_attempt={attempt_number + 1} | "
                f"delay={retry_delay_seconds:.0f}s | "
                f"error={error}"
            )
            time.sleep(retry_delay_seconds)

    raise RuntimeError(
        f"Unexpected retry loop exit: {operation_name}"
    )


def create_child_environment(
    run_id: str,
    run_type: str = "NORMAL",
    recovery_of_run_id: str | None = None,
    backfill_start_date: str | None = None,
    backfill_end_date: str | None = None,
) -> dict[str, str]:
    child_environment = os.environ.copy()
    child_environment["PYTHONIOENCODING"] = "utf-8"
    child_environment["PYTHONUTF8"] = "1"
    child_environment["PIPELINE_RUN_ID"] = run_id
    child_environment["PIPELINE_RUN_TYPE"] = run_type

    if recovery_of_run_id:
        child_environment["PIPELINE_RECOVERY_OF_RUN_ID"] = recovery_of_run_id
    else:
        child_environment.pop("PIPELINE_RECOVERY_OF_RUN_ID", None)

    if backfill_start_date and backfill_end_date:
        child_environment["PIPELINE_BACKFILL_START_DATE"] = backfill_start_date
        child_environment["PIPELINE_BACKFILL_END_DATE"] = backfill_end_date
    else:
        child_environment.pop("PIPELINE_BACKFILL_START_DATE", None)
        child_environment.pop("PIPELINE_BACKFILL_END_DATE", None)

    return child_environment


def table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    cursor = connection.execute(
        """
        SELECT COUNT(*)
        FROM sqlite_master
        WHERE type = 'table' AND name = ?;
        """,
        (table_name,),
    )
    return cursor.fetchone()[0] == 1


def get_table_row_count(connection: sqlite3.Connection, table_name: str) -> int:
    if not table_exists(connection, table_name):
        return 0

    cursor = connection.execute(f"SELECT COUNT(*) FROM {table_name};")
    return int(cursor.fetchone()[0])


def get_total_row_count(table_names: list[str]) -> int:
    if not DATABASE_PATH.exists():
        return 0

    with sqlite3.connect(DATABASE_PATH) as connection:
        return sum(
            get_table_row_count(connection, table_name)
            for table_name in table_names
        )


def monitoring_schema_available() -> bool:
    if not DATABASE_PATH.exists():
        return False

    connection: sqlite3.Connection | None = None

    try:
        connection = sqlite3.connect(DATABASE_PATH)
        required_tables = {
            "pipeline_audit",
            "pipeline_step_log",
            "pipeline_sla_metrics",
            "pipeline_alerts",
            "pipeline_alert_occurrences",
        }
        return all(
            table_exists(connection, table_name)
            for table_name in required_tables
        )
    except sqlite3.Error:
        raise
    finally:
        if connection is not None:
            connection.close()


def bootstrap_monitoring_schema() -> None:
    if monitoring_schema_available():
        return

    setup_script_path = SCRIPTS_DIRECTORY / "01_setup_database.py"
    validate_script_exists(setup_script_path)

    print("[BOOTSTRAP] Monitoring schema ยังไม่พร้อม กำลังสร้าง Schema ก่อน")
    write_log("BOOTSTRAP | Monitoring schema not available")

    process = subprocess.run(
        [sys.executable, str(setup_script_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if process.stdout:
        print(process.stdout.rstrip())
    if process.stderr:
        print(process.stderr.rstrip(), file=sys.stderr)

    if process.returncode != 0:
        raise RuntimeError(
            "ไม่สามารถ Bootstrap Monitoring Schema ได้ "
            f"(Exit Code {process.returncode})"
        )

    if not monitoring_schema_available():
        raise RuntimeError(
            "Bootstrap สำเร็จแต่ยังไม่พบ Monitoring Tables ที่จำเป็น"
        )

    print("[SUCCESS] Monitoring schema พร้อมใช้งาน")


def validate_pipeline_inputs(config: dict[str, Any], pipeline_mode: str) -> None:
    directories = config["directories"]
    synthetic_files = config["synthetic_files"]
    pawchoice_files = config["pawchoice_files"]

    synthetic_directory = PROJECT_ROOT / directories["synthetic_raw_data"]
    pawchoice_directory = PROJECT_ROOT / directories["pawchoice_raw_data"]

    required_paths = [
        CONFIG_PATH,
        synthetic_directory / synthetic_files["customers"],
        synthetic_directory / synthetic_files["products"],
        synthetic_directory / synthetic_files["orders"],
        synthetic_directory / synthetic_files["order_items"],
        synthetic_directory / synthetic_files["payments"],
    ]

    if pipeline_mode == "hybrid":
        required_paths.append(
            pawchoice_directory / pawchoice_files["influencer_payments"]
        )

    missing_paths = [path for path in required_paths if not path.exists()]
    if missing_paths:
        missing_path_text = "\n".join(f"- {path}" for path in missing_paths)
        raise FileNotFoundError(
            "ไฟล์ที่ Pipeline ต้องใช้ไม่ครบ:\n" + missing_path_text
        )


def print_pipeline_sources(pipeline_mode: str) -> None:
    print(f"[INFO] Pipeline mode: {pipeline_mode.upper()}")
    print("[INFO] แหล่งข้อมูล:")
    print("  1. Synthetic CSV")
    if pipeline_mode == "hybrid":
        print("  2. Pawchoice Excel")
    else:
        print("  2. Pawchoice Excel (ข้ามใน Demo Mode)")


def lineage_schema_available() -> bool:
    if not DATABASE_PATH.exists():
        return False

    with sqlite3.connect(DATABASE_PATH) as connection:
        required_tables = {
            "data_assets",
            "lineage_edges",
            "lineage_run_events",
        }
        return all(
            table_exists(connection, table_name)
            for table_name in required_tables
        )


def get_runtime_lineage_types(
    step_name: str,
    run_type: str,
) -> tuple[str, ...]:
    if step_name == "LOAD_RAW_DATA":
        return ("INGESTION",)

    if step_name == "RUN_TRANSFORMATIONS":
        if run_type == "BACKFILL":
            return (
                "CLEANING",
                "TRANSFORMATION",
                "QUALITY",
            )

        return (
            "INCREMENTAL_LOAD",
            "TRANSFORMATION",
            "QUALITY",
        )

    return ()


def is_pawchoice_lineage_edge(
    upstream_asset_key: str,
    downstream_asset_key: str,
) -> bool:
    pawchoice_asset_keys = {
        "file://pawchoice/pawchoice_payments.xlsx",
        "sqlite://staging/stg_influencer_payments",
        "sqlite://core/campaigns",
        "sqlite://core/influencers",
        "sqlite://core/influencer_payments",
        "sqlite://core/rejected_influencer_records",
    }
    return (
        upstream_asset_key in pawchoice_asset_keys
        or downstream_asset_key in pawchoice_asset_keys
    )


def record_lineage_events_for_step(
    run_id: str,
    step_name: str,
    attempt_number: int,
    execution_status: str,
    pipeline_mode: str,
    run_type: str,
) -> int:
    transformation_types = get_runtime_lineage_types(
        step_name=step_name,
        run_type=run_type,
    )
    if not transformation_types:
        return 0

    if not lineage_schema_available():
        warning_message = (
            "Lineage schema not available; runtime lineage event recording skipped "
            f"for step={step_name} run_id={run_id}"
        )
        print(f"[LINEAGE WARNING] {warning_message}")
        write_log(f"WARNING | RUNTIME_LINEAGE | {warning_message}")
        return 0

    placeholders = ", ".join("?" for _ in transformation_types)

    try:
        with sqlite3.connect(DATABASE_PATH) as connection:
            connection.execute("PRAGMA foreign_keys = ON;")

            lineage_edges = connection.execute(
                f"""
                SELECT
                    e.lineage_edge_id,
                    u.asset_key AS upstream_asset_key,
                    d.asset_key AS downstream_asset_key
                FROM lineage_edges AS e
                INNER JOIN data_assets AS u
                    ON u.asset_id = e.upstream_asset_id
                INNER JOIN data_assets AS d
                    ON d.asset_id = e.downstream_asset_id
                WHERE
                    e.is_active = 1
                    AND e.lineage_level = 'DATASET'
                    AND e.transformation_type IN ({placeholders})
                ORDER BY e.lineage_edge_id;
                """,
                transformation_types,
            ).fetchall()

            recorded_count = 0

            for (
                lineage_edge_id,
                upstream_asset_key,
                downstream_asset_key,
            ) in lineage_edges:
                edge_status = execution_status

                if (
                    pipeline_mode == "demo"
                    and is_pawchoice_lineage_edge(
                        upstream_asset_key,
                        downstream_asset_key,
                    )
                ):
                    edge_status = "SKIPPED"

                connection.execute(
                    """
                    INSERT INTO lineage_run_events (
                        lineage_edge_id,
                        run_id,
                        execution_status,
                        step_name,
                        attempt_number
                    )
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT DO UPDATE SET
                        execution_status = excluded.execution_status,
                        recorded_at = CURRENT_TIMESTAMP;
                    """,
                    (
                        lineage_edge_id,
                        run_id,
                        edge_status,
                        step_name,
                        attempt_number,
                    ),
                )
                recorded_count += 1

            connection.commit()

        if recorded_count:
            print(
                "[LINEAGE] "
                f"step={step_name} | attempt={attempt_number} | "
                f"events={recorded_count}"
            )
            write_log(
                "RUNTIME_LINEAGE | "
                f"run_id={run_id} | step={step_name} | "
                f"attempt={attempt_number} | events={recorded_count} | "
                f"status={execution_status}"
            )

        return recorded_count

    except sqlite3.Error as error:
        warning_message = (
            "ไม่สามารถบันทึก Runtime Lineage ได้ | "
            f"run_id={run_id} | step={step_name} | "
            f"attempt={attempt_number} | error={error}"
        )
        print(f"[LINEAGE WARNING] {warning_message}")
        write_log(f"WARNING | RUNTIME_LINEAGE | {warning_message}")
        return 0


def start_pipeline_audit(run_id: str, started_at: str) -> int:
    with sqlite3.connect(DATABASE_PATH) as connection:
        cursor = connection.execute(
            """
            INSERT INTO pipeline_audit (
                pipeline_name,
                run_id,
                step_name,
                run_status,
                rows_processed,
                rows_inserted,
                rows_updated,
                rows_rejected,
                error_message,
                started_at,
                completed_at
            )
            VALUES (?, ?, 'PIPELINE_TOTAL', 'RUNNING', 0, 0, 0, 0, NULL, ?, NULL);
            """,
            (PIPELINE_NAME, run_id, started_at),
        )
        connection.commit()
        return int(cursor.lastrowid)


def finish_pipeline_audit(
    audit_id: int,
    run_status: str,
    error_message: str | None,
    completed_at: str,
) -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            UPDATE pipeline_audit
            SET run_status = ?, error_message = ?, completed_at = ?
            WHERE audit_id = ?;
            """,
            (run_status, error_message, completed_at, audit_id),
        )
        connection.commit()


def validate_recovery_source(recovery_of_run_id: str) -> None:
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        recovery_source = connection.execute(
            """
            SELECT run_status
            FROM pipeline_audit
            WHERE
                pipeline_name = ?
                AND run_id = ?
                AND step_name = 'PIPELINE_TOTAL'
            ORDER BY audit_id DESC
            LIMIT 1;
            """,
            (
                PIPELINE_NAME,
                recovery_of_run_id,
            ),
        ).fetchone()
    finally:
        connection.close()

    if recovery_source is None:
        raise ValueError(
            f"Recovery source run_id does not exist: {recovery_of_run_id}"
        )

    if recovery_source[0] != "FAILED":
        raise ValueError(
            "Recovery source must be a FAILED pipeline run. "
            f"run_id={recovery_of_run_id} | status={recovery_source[0]}"
        )


def stamp_pipeline_audit_metadata(
    run_id: str,
    run_type: str,
    recovery_of_run_id: str | None,
    backfill_start_date: str | None = None,
    backfill_end_date: str | None = None,
) -> None:
    connection = sqlite3.connect(DATABASE_PATH)

    try:
        connection.execute(
            """
            UPDATE pipeline_audit
            SET
                run_type = ?,
                recovery_of_run_id = ?,
                backfill_start_date = ?,
                backfill_end_date = ?
            WHERE run_id = ?;
            """,
            (
                run_type,
                recovery_of_run_id,
                backfill_start_date,
                backfill_end_date,
                run_id,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def insert_pipeline_audit_record(
    run_id: str,
    step_name: str,
    run_status: str,
    error_message: str | None,
    started_at: str,
    completed_at: str,
    rows_processed: int = 0,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    rows_rejected: int = 0,
) -> None:
    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(DATABASE_PATH)
        connection.execute(
            """
            INSERT INTO pipeline_audit (
                pipeline_name,
                run_id,
                step_name,
                run_status,
                rows_processed,
                rows_inserted,
                rows_updated,
                rows_rejected,
                error_message,
                started_at,
                completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                PIPELINE_NAME,
                run_id,
                step_name,
                run_status,
                rows_processed,
                rows_inserted,
                rows_updated,
                rows_rejected,
                error_message,
                started_at,
                completed_at,
            ),
        )
        connection.commit()
    except sqlite3.Error as error:
        warning_message = f"ไม่สามารถบันทึก Audit ของขั้นตอน {step_name}: {error}"
        print(f"[WARNING] {warning_message}")
        write_log(f"WARNING | PIPELINE_AUDIT | {warning_message}")
    finally:
        if connection is not None:
            connection.close()


def insert_step_log_start(
    run_id: str,
    step_number: int,
    step_name: str,
    script_name: str,
    attempt_number: int,
    started_at: str,
    sla_threshold_seconds: float | None,
) -> int:
    with sqlite3.connect(DATABASE_PATH) as connection:
        cursor = connection.execute(
            """
            INSERT INTO pipeline_step_log (
                pipeline_name,
                run_id,
                step_number,
                step_name,
                script_name,
                attempt_number,
                status,
                start_time,
                end_time,
                duration_seconds,
                rows_read,
                rows_written,
                rows_rejected,
                error_type,
                error_message,
                sla_threshold_seconds,
                sla_status
            )
            VALUES (?, ?, ?, ?, ?, ?, 'RUNNING', ?, NULL, NULL, 0, 0, 0, NULL, NULL, ?, 'NOT_EVALUATED');
            """,
            (
                PIPELINE_NAME,
                run_id,
                step_number,
                step_name,
                script_name,
                attempt_number,
                started_at,
                sla_threshold_seconds,
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)


def update_step_log_end(
    step_log_id: int,
    status: str,
    completed_at: str,
    duration_seconds: float,
    rows_read: int,
    rows_written: int,
    rows_rejected: int,
    error_type: str | None,
    error_message: str | None,
    sla_status: str,
) -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            UPDATE pipeline_step_log
            SET
                status = ?,
                end_time = ?,
                duration_seconds = ?,
                rows_read = ?,
                rows_written = ?,
                rows_rejected = ?,
                error_type = ?,
                error_message = ?,
                sla_status = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE step_log_id = ?;
            """,
            (
                status,
                completed_at,
                duration_seconds,
                rows_read,
                rows_written,
                rows_rejected,
                error_type,
                error_message,
                sla_status,
                step_log_id,
            ),
        )
        connection.commit()


def insert_sla_metric(
    run_id: str,
    step_name: str,
    attempt_number: int,
    step_run_status: str,
    duration_seconds: float,
    sla_threshold_seconds: float,
    sla_status: str,
    measured_at: str,
) -> None:
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            """
            INSERT INTO pipeline_sla_metrics (
                pipeline_name,
                run_id,
                step_name,
                attempt_number,
                step_run_status,
                duration_seconds,
                sla_threshold_seconds,
                sla_status,
                measured_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (pipeline_name, run_id, step_name, attempt_number)
            DO UPDATE SET
                step_run_status = excluded.step_run_status,
                duration_seconds = excluded.duration_seconds,
                sla_threshold_seconds = excluded.sla_threshold_seconds,
                sla_status = excluded.sla_status,
                measured_at = excluded.measured_at;
            """,
            (
                PIPELINE_NAME,
                run_id,
                step_name,
                attempt_number,
                step_run_status,
                duration_seconds,
                sla_threshold_seconds,
                sla_status,
                measured_at,
            ),
        )
        connection.commit()


def determine_sla_status(
    duration_seconds: float,
    sla_enabled: bool,
    sla_threshold_seconds: float | None,
) -> str:
    if not sla_enabled or sla_threshold_seconds is None:
        return "NOT_EVALUATED"
    return "BREACHED" if duration_seconds > sla_threshold_seconds else "ON_TIME"


def normalize_alert_error_signature(
    error_type: str | None,
    error_message: str | None,
) -> str:
    normalized_type = (error_type or "none").strip().lower()
    normalized_message = (error_message or "no error").strip().lower()

    if "database is locked" in normalized_message:
        normalized_message = "database is locked"
    else:
        normalized_message = re.sub(
            r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
            "<uuid>",
            normalized_message,
            flags=re.IGNORECASE,
        )
        normalized_message = re.sub(
            r"\b\d{4}-\d{2}-\d{2}[ t]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:z|[+-]\d{2}:?\d{2})?\b",
            "<timestamp>",
            normalized_message,
            flags=re.IGNORECASE,
        )
        normalized_message = re.sub(
            r"\bafter\s+\d+(?:\.\d+)?\s*(?:sec|secs|second|seconds)\b",
            "after <duration>",
            normalized_message,
            flags=re.IGNORECASE,
        )
        normalized_message = re.sub(r"\s+", " ", normalized_message).strip()

    return f"{normalized_type}::{normalized_message}"


def build_alert_fingerprint(
    pipeline_name: str,
    step_name: str,
    alert_type: str,
    error_type: str | None,
    error_message: str | None,
) -> str:
    normalized_signature = normalize_alert_error_signature(
        error_type=error_type,
        error_message=error_message,
    )
    fingerprint_source = "::".join(
        (
            pipeline_name.strip().lower(),
            step_name.strip().upper(),
            alert_type.strip().upper(),
            normalized_signature,
        )
    )
    return hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()


def build_alert_key(
    pipeline_name: str,
    run_id: str,
    step_name: str,
    attempt_number: int,
    alert_type: str,
) -> str:
    return "::".join(
        (
            pipeline_name,
            run_id,
            step_name,
            str(attempt_number),
            alert_type,
        )
    )


def record_step_alert(
    pipeline_name: str,
    run_id: str,
    step_name: str,
    attempt_number: int,
    step_status: str,
    sla_status: str,
    error_type: str | None,
    error_message: str | None,
    detected_at: str,
) -> None:
    if step_status == "FAILED":
        alert_type = "STEP_FAILURE"
        severity = "CRITICAL"
        title = f"Pipeline step failed: {step_name}"

        error_detail = error_message or "No error message was provided."
        type_detail = error_type or "UnknownError"

        message = (
            f"Step {step_name} failed with {type_detail}: "
            f"{error_detail} | SLA status={sla_status}"
        )

    elif step_status == "SUCCESS" and sla_status == "BREACHED":
        alert_type = "SLA_BREACH"
        severity = "WARNING"
        title = f"Pipeline SLA breached: {step_name}"
        message = (
            f"Step {step_name} completed successfully but "
            "its SLA status is BREACHED."
        )

    else:
        return

    normalized_error_signature = normalize_alert_error_signature(
        error_type=error_type,
        error_message=error_message,
    )
    alert_fingerprint = build_alert_fingerprint(
        pipeline_name=pipeline_name,
        step_name=step_name,
        alert_type=alert_type,
        error_type=error_type,
        error_message=error_message,
    )

    connection: sqlite3.Connection | None = None

    try:
        connection = sqlite3.connect(DATABASE_PATH)
        connection.execute("PRAGMA foreign_keys = ON;")

        alert_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(pipeline_alerts);"
            ).fetchall()
        }
        occurrence_table_exists = connection.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type = 'table'
              AND name = 'pipeline_alert_occurrences';
            """
        ).fetchone() is not None

        modern_alert_schema = (
            "alert_fingerprint" in alert_columns
            and occurrence_table_exists
        )

        if modern_alert_schema:
            connection.execute("BEGIN IMMEDIATE;")

            existing_alert = connection.execute(
                """
                SELECT alert_id
                FROM pipeline_alerts
                WHERE alert_fingerprint = ?;
                """,
                (alert_fingerprint,),
            ).fetchone()

            if existing_alert is None:
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
                        ?, ?, 'ORCHESTRATOR', ?, ?, 'OPEN',
                        ?, ?, ?, ?, ?, ?, ?, ?, 1
                    );
                    """,
                    (
                        alert_fingerprint,
                        alert_fingerprint,
                        alert_type,
                        severity,
                        pipeline_name,
                        run_id,
                        step_name,
                        attempt_number,
                        title,
                        message,
                        detected_at,
                        detected_at,
                    ),
                )
                alert_id = int(cursor.lastrowid)
            else:
                alert_id = int(existing_alert[0])
                connection.execute(
                    """
                    UPDATE pipeline_alerts
                    SET
                        run_id = ?,
                        attempt_number = ?,
                        title = ?,
                        message = ?,
                        last_detected_at = ?,
                        occurrence_count = occurrence_count + 1,
                        status = CASE
                            WHEN status = 'RESOLVED'
                                THEN 'OPEN'
                            ELSE status
                        END,
                        acknowledged_at = CASE
                            WHEN status = 'RESOLVED'
                                THEN NULL
                            ELSE acknowledged_at
                        END,
                        resolved_at = CASE
                            WHEN status = 'RESOLVED'
                                THEN NULL
                            ELSE resolved_at
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE alert_id = ?;
                    """,
                    (
                        run_id,
                        attempt_number,
                        title,
                        message,
                        detected_at,
                        alert_id,
                    ),
                )

            connection.execute(
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
                    error_message,
                    normalized_error_signature,
                ),
            )
            connection.commit()
            return

        # Backward-compatible fallback for isolated/legacy schemas that
        # predate stable fingerprints and occurrence history.
        alert_key = build_alert_key(
            pipeline_name=pipeline_name,
            run_id=run_id,
            step_name=step_name,
            attempt_number=attempt_number,
            alert_type=alert_type,
        )

        connection.execute(
            """
            INSERT INTO pipeline_alerts (
                alert_key,
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
                ?, 'ORCHESTRATOR', ?, ?, 'OPEN',
                ?, ?, ?, ?, ?, ?, ?, ?, 1
            )
            ON CONFLICT (alert_key)
            DO UPDATE SET
                title = excluded.title,
                message = excluded.message,
                last_detected_at = excluded.last_detected_at,
                occurrence_count = pipeline_alerts.occurrence_count + 1,
                updated_at = CURRENT_TIMESTAMP;
            """,
            (
                alert_key,
                alert_type,
                severity,
                pipeline_name,
                run_id,
                step_name,
                attempt_number,
                title,
                message,
                detected_at,
                detected_at,
            ),
        )
        connection.commit()
    except sqlite3.Error as error:
        if connection is not None:
            connection.rollback()

        warning_message = (
            f"[ALERT WRITE WARNING] {step_name} | "
            f"{type(error).__name__}: {error}"
        )
        print(warning_message)

        try:
            write_log(warning_message)
        except OSError:
            pass
    finally:
        if connection is not None:
            connection.close()

def get_child_audit_totals(run_id: str, pipeline_name: str) -> dict[str, int]:
    empty_totals = {
        "rows_processed": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_rejected": 0,
    }

    if not DATABASE_PATH.exists():
        return empty_totals

    with sqlite3.connect(DATABASE_PATH) as connection:
        cursor = connection.execute(
            """
            SELECT
                COALESCE(SUM(rows_processed), 0),
                COALESCE(SUM(rows_inserted), 0),
                COALESCE(SUM(rows_updated), 0),
                COALESCE(SUM(rows_rejected), 0)
            FROM pipeline_audit
            WHERE run_id = ? AND pipeline_name = ?;
            """,
            (run_id, pipeline_name),
        )
        row = cursor.fetchone()

    return {
        "rows_processed": int(row[0]),
        "rows_inserted": int(row[1]),
        "rows_updated": int(row[2]),
        "rows_rejected": int(row[3]),
    }


def collect_step_metrics(step_name: str, run_id: str) -> dict[str, int]:
    if step_name == "SETUP_DATABASE":
        return {"rows_read": 0, "rows_written": 0, "rows_rejected": 0}

    if step_name == "LOAD_RAW_DATA":
        staging_rows = get_total_row_count(STAGING_TABLES)
        return {
            "rows_read": staging_rows,
            "rows_written": staging_rows,
            "rows_rejected": 0,
        }

    if step_name == "RUN_TRANSFORMATIONS":
        totals = get_child_audit_totals(
            run_id,
            "ecommerce_transformation_pipeline",
        )
        return {
            "rows_read": totals["rows_processed"],
            "rows_written": totals["rows_inserted"] + totals["rows_updated"],
            "rows_rejected": totals["rows_rejected"],
        }

    if step_name == "RUN_QUALITY_CHECKS":
        quality_scope_rows = get_total_row_count(QUALITY_SCOPE_TABLES)
        totals = get_child_audit_totals(
            run_id,
            "ecommerce_quality_check_pipeline",
        )
        return {
            "rows_read": quality_scope_rows,
            "rows_written": 0,
            "rows_rejected": totals["rows_rejected"],
        }

    return {"rows_read": 0, "rows_written": 0, "rows_rejected": 0}


def build_child_error_message(
    base_error_message: str,
    standard_output: str,
    standard_error: str,
) -> str:
    if standard_error:
        return f"{base_error_message} | stderr: {standard_error}"
    if standard_output:
        return f"{base_error_message} | stdout: {standard_output}"
    return base_error_message


def run_script(
    step_number: int,
    step_name: str,
    script_name: str,
    description: str,
    run_id: str,
    pipeline_mode: str,
    sla_enabled: bool,
    sla_threshold_seconds: float | None,
    attempt_number: int = 1,
    run_type: str = "NORMAL",
    recovery_of_run_id: str | None = None,
    backfill_start_date: str | None = None,
    backfill_end_date: str | None = None,
) -> float:
    script_path = SCRIPTS_DIRECTORY / script_name
    started_at_utc = current_utc_time()
    started_at_counter = time.perf_counter()
    standard_output = ""
    standard_error = ""

    step_log_id = insert_step_log_start(
        run_id=run_id,
        step_number=step_number,
        step_name=step_name,
        script_name=script_name,
        attempt_number=attempt_number,
        started_at=started_at_utc,
        sla_threshold_seconds=(sla_threshold_seconds if sla_enabled else None),
    )

    write_log(
        f"STEP RUNNING | {step_name} | run_id={run_id} | attempt={attempt_number}"
    )

    try:
        validate_script_exists(script_path)
        print_separator()
        print(f"[STEP {step_number}] {step_name}")
        print(f"[INFO] {description}")
        print(f"[INFO] กำลังรัน: {script_name}")
        print(f"[INFO] attempt: {attempt_number}")

        if sla_enabled and sla_threshold_seconds is not None:
            print(f"[INFO] SLA threshold: {sla_threshold_seconds:.2f} วินาที")

        write_log(f"START | {step_name} | {script_name}")

        process = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=PROJECT_ROOT,
            env=create_child_environment(
                run_id=run_id,
                run_type=run_type,
                recovery_of_run_id=recovery_of_run_id,
                backfill_start_date=backfill_start_date,
                backfill_end_date=backfill_end_date,
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )

        if process.stdout:
            standard_output = process.stdout.rstrip()
            print(standard_output)
            write_log(f"STDOUT | {step_name}\n{standard_output}")

        if process.stderr:
            standard_error = process.stderr.rstrip()
            print(standard_error, file=sys.stderr)
            write_log(f"STDERR | {step_name}\n{standard_error}")

        if process.returncode != 0:
            child_error_text = (
                standard_error
                or standard_output
                or (
                    f"ขั้นตอน {step_name} ล้มเหลว "
                    f"ด้วย Exit Code {process.returncode}"
                )
            )

            if "[FILE ERROR]" in child_error_text:
                raise FileNotFoundError(child_error_text)

            if "[VALIDATION ERROR]" in child_error_text:
                raise ValueError(child_error_text)

            if "[QUALITY ERROR]" in child_error_text:
                raise ValueError(child_error_text)

            raise RuntimeError(child_error_text)

    except Exception as error:
        completed_at_utc = current_utc_time()
        elapsed_seconds = time.perf_counter() - started_at_counter
        error_type = type(error).__name__
        base_error_message = str(error)
        audit_error_message = build_child_error_message(
            base_error_message,
            standard_output,
            standard_error,
        )
        metrics = collect_step_metrics(step_name, run_id)
        sla_status = determine_sla_status(
            elapsed_seconds,
            sla_enabled,
            sla_threshold_seconds,
        )

        update_step_log_end(
            step_log_id,
            "FAILED",
            completed_at_utc,
            elapsed_seconds,
            metrics["rows_read"],
            metrics["rows_written"],
            metrics["rows_rejected"],
            error_type,
            audit_error_message,
            sla_status,
        )

        if sla_enabled and sla_threshold_seconds is not None:
            insert_sla_metric(
                run_id,
                step_name,
                attempt_number,
                "FAILED",
                elapsed_seconds,
                sla_threshold_seconds,
                sla_status,
                completed_at_utc,
            )

        insert_pipeline_audit_record(
            run_id,
            step_name,
            "FAILED",
            audit_error_message,
            started_at_utc,
            completed_at_utc,
            rows_processed=metrics["rows_read"],
            rows_inserted=metrics["rows_written"],
            rows_updated=0,
            rows_rejected=metrics["rows_rejected"],
        )

        record_lineage_events_for_step(
            run_id=run_id,
            step_name=step_name,
            attempt_number=attempt_number,
            execution_status="FAILED",
            pipeline_mode=pipeline_mode,
            run_type=run_type,
        )

        record_step_alert(
            pipeline_name=PIPELINE_NAME,
            run_id=run_id,
            step_name=step_name,
            attempt_number=attempt_number,
            step_status="FAILED",
            sla_status=sla_status,
            error_type=error_type,
            error_message=audit_error_message,
            detected_at=completed_at_utc,
        )

        print(f"[FAILED] {step_name}")
        print(f"[ERROR TYPE] {error_type}")
        print(f"[ERROR] {base_error_message}")

        if sla_status == "BREACHED":
            print(
                f"[SLA BREACH] {step_name} | "
                f"{elapsed_seconds:.2f}s > {sla_threshold_seconds:.2f}s"
            )

        write_log(
            f"FAILED | {step_name} | {elapsed_seconds:.2f} seconds | "
            f"error_type={error_type} | error={base_error_message} | "
            f"sla_status={sla_status}"
        )
        raise

    completed_at_utc = current_utc_time()
    elapsed_seconds = time.perf_counter() - started_at_counter
    metrics = collect_step_metrics(step_name, run_id)
    sla_status = determine_sla_status(
        elapsed_seconds,
        sla_enabled,
        sla_threshold_seconds,
    )

    update_step_log_end(
        step_log_id,
        "SUCCESS",
        completed_at_utc,
        elapsed_seconds,
        metrics["rows_read"],
        metrics["rows_written"],
        metrics["rows_rejected"],
        None,
        None,
        sla_status,
    )

    if sla_enabled and sla_threshold_seconds is not None:
        insert_sla_metric(
            run_id,
            step_name,
            attempt_number,
            "SUCCESS",
            elapsed_seconds,
            sla_threshold_seconds,
            sla_status,
            completed_at_utc,
        )

    insert_pipeline_audit_record(
        run_id,
        step_name,
        "SUCCESS",
        None,
        started_at_utc,
        completed_at_utc,
        rows_processed=metrics["rows_read"],
        rows_inserted=metrics["rows_written"],
        rows_updated=0,
        rows_rejected=metrics["rows_rejected"],
    )

    record_lineage_events_for_step(
        run_id=run_id,
        step_name=step_name,
        attempt_number=attempt_number,
        execution_status="SUCCESS",
        pipeline_mode=pipeline_mode,
        run_type=run_type,
    )

    record_step_alert(
        pipeline_name=PIPELINE_NAME,
        run_id=run_id,
        step_name=step_name,
        attempt_number=attempt_number,
        step_status="SUCCESS",
        sla_status=sla_status,
        error_type=None,
        error_message=None,
        detected_at=completed_at_utc,
    )

    print(f"[SUCCESS] {step_name} สำเร็จ ใช้เวลา {elapsed_seconds:.2f} วินาที")
    print(
        "[METRICS] "
        f"rows_read={metrics['rows_read']} | "
        f"rows_written={metrics['rows_written']} | "
        f"rows_rejected={metrics['rows_rejected']}"
    )

    if sla_enabled and sla_threshold_seconds is not None:
        if sla_status == "BREACHED":
            print(
                f"[SLA BREACH] {step_name} | "
                f"{elapsed_seconds:.2f}s > {sla_threshold_seconds:.2f}s"
            )
        else:
            print(
                f"[SLA] {step_name} | "
                f"{elapsed_seconds:.2f}s <= {sla_threshold_seconds:.2f}s | ON_TIME"
            )
    else:
        print(f"[SLA] {step_name} | NOT_EVALUATED")

    write_log(
        f"SUCCESS | {step_name} | {elapsed_seconds:.2f} seconds | "
        f"rows_read={metrics['rows_read']} | "
        f"rows_written={metrics['rows_written']} | "
        f"rows_rejected={metrics['rows_rejected']} | "
        f"sla_status={sla_status}"
    )

    return elapsed_seconds


def validate_backfill_dates(
    backfill_start_date: str | None,
    backfill_end_date: str | None,
) -> None:
    if bool(backfill_start_date) != bool(backfill_end_date):
        raise ValueError(
            "Both --backfill-start and --backfill-end are required together."
        )

    if not backfill_start_date:
        return

    try:
        start_date = datetime.strptime(
            backfill_start_date,
            "%Y-%m-%d",
        ).date()

        end_date = datetime.strptime(
            backfill_end_date,
            "%Y-%m-%d",
        ).date()

    except ValueError as error:
        raise ValueError(
            "Backfill dates must use YYYY-MM-DD format."
        ) from error

    if start_date > end_date:
        raise ValueError(
            "Backfill start date must be on or before backfill end date."
        )


def run_pipeline(
    recovery_of_run_id: str | None = None,
    backfill_start_date: str | None = None,
    backfill_end_date: str | None = None,
) -> None:
    ensure_required_directories()
    config = read_pipeline_config()
    pipeline_mode = get_pipeline_mode(config)
    sla_enabled, step_sla_seconds = get_monitoring_config(config)
    pipeline_run_id = str(uuid.uuid4())
    pipeline_started_at_counter = time.perf_counter()

    print(f"[INFO] Pre-run pipeline run_id: {pipeline_run_id}")
    write_log(
        "PIPELINE PRE-RUN | "
        f"run_id={pipeline_run_id} | mode={pipeline_mode}"
    )

    try:
        run_database_operation_with_retry(
            operation_name="BOOTSTRAP_MONITORING_SCHEMA",
            operation=bootstrap_monitoring_schema,
            run_id=pipeline_run_id,
        )
    except sqlite3.Error as error:
        print_separator()
        print("[DATABASE ERROR] ไม่สามารถเข้าถึง Monitoring Database")
        print(f"[INFO] run_id: {pipeline_run_id}")
        print(f"[ERROR TYPE] {type(error).__name__}")
        print(f"[ERROR] {error}")

        write_log(
            "PIPELINE FAILED | DATABASE ERROR | "
            f"run_id={pipeline_run_id} | error={error}"
        )

        raise

    if recovery_of_run_id:
        run_type = "RECOVERY"
    elif backfill_start_date and backfill_end_date:
        run_type = "BACKFILL"
    else:
        run_type = "NORMAL"

    if recovery_of_run_id:
        run_database_operation_with_retry(
            operation_name="VALIDATE_RECOVERY_SOURCE",
            operation=lambda: validate_recovery_source(
                recovery_of_run_id
            ),
            run_id=pipeline_run_id,
        )

        print(
            f"[INFO] Recovery mode: recovering from "
            f"{recovery_of_run_id}"
        )

    if run_type == "BACKFILL":
        print(
            "[INFO] Backfill mode: "
            f"{backfill_start_date} -> {backfill_end_date}"
        )

    pipeline_start_time = current_utc_time()

    pipeline_audit_id = run_database_operation_with_retry(
        operation_name="START_PIPELINE_AUDIT",
        operation=lambda: start_pipeline_audit(
            pipeline_run_id,
            pipeline_start_time,
        ),
        run_id=pipeline_run_id,
    )

    run_database_operation_with_retry(
        operation_name="STAMP_PIPELINE_AUDIT_METADATA",
        operation=lambda: stamp_pipeline_audit_metadata(
            run_id=pipeline_run_id,
            run_type=run_type,
            recovery_of_run_id=recovery_of_run_id,
            backfill_start_date=backfill_start_date,
            backfill_end_date=backfill_end_date,
        ),
        run_id=pipeline_run_id,
    )

    print_separator()
    print("[START] E-COMMERCE DATA PIPELINE")
    print_pipeline_sources(pipeline_mode)
    print(f"[INFO] Pipeline run_id: {pipeline_run_id}")
    print(f"[INFO] เริ่มทำงานเวลา UTC: {pipeline_start_time}")
    print(f"[INFO] SLA Monitoring: {'ENABLED' if sla_enabled else 'DISABLED'}")

    write_log(
        "PIPELINE START | "
        f"run_id={pipeline_run_id} | mode={pipeline_mode} | "
        f"run_type={run_type} | "
        f"backfill_start={backfill_start_date} | "
        f"backfill_end={backfill_end_date} | "
        f"sla_enabled={sla_enabled} | {PIPELINE_NAME}"
    )

    step_durations: dict[str, float] = {}

    try:
        for pipeline_step in PIPELINE_STEPS:
            step_name = pipeline_step["step_name"]
            sla_threshold_seconds = (
                step_sla_seconds.get(step_name) if sla_enabled else None
            )

            for attempt_number in range(
                1,
                DATABASE_RETRY_MAX_ATTEMPTS + 1,
            ):
                try:
                    elapsed_seconds = run_script(
                        step_number=pipeline_step["step_number"],
                        step_name=step_name,
                        script_name=pipeline_step["script_name"],
                        description=pipeline_step["description"],
                        run_id=pipeline_run_id,
                        pipeline_mode=pipeline_mode,
                        sla_enabled=sla_enabled,
                        sla_threshold_seconds=sla_threshold_seconds,
                        attempt_number=attempt_number,
                        run_type=run_type,
                        recovery_of_run_id=recovery_of_run_id,
                        backfill_start_date=backfill_start_date,
                        backfill_end_date=backfill_end_date,
                    )

                    step_durations[step_name] = elapsed_seconds
                    break

                except Exception as error:
                    if not is_retryable_error(error):
                        print(
                            f"[NO RETRY] {step_name} | "
                            "error is not retryable"
                        )
                        raise

                    if attempt_number >= DATABASE_RETRY_MAX_ATTEMPTS:
                        print(
                            f"[RETRY EXHAUSTED] {step_name} | "
                            f"attempts={DATABASE_RETRY_MAX_ATTEMPTS}"
                        )
                        raise

                    print(
                        f"[RETRY] {step_name} | "
                        f"attempt {attempt_number} failed | "
                        f"retrying as attempt {attempt_number + 1} "
                        f"in {DATABASE_RETRY_DELAY_SECONDS:.0f} seconds"
                    )

                    write_log(
                        f"RETRY SCHEDULED | {step_name} | "
                        f"run_id={pipeline_run_id} | "
                        f"failed_attempt={attempt_number} | "
                        f"next_attempt={attempt_number + 1} | "
                        f"delay={DATABASE_RETRY_DELAY_SECONDS:.0f}s"
                    )

                    time.sleep(DATABASE_RETRY_DELAY_SECONDS)

    except Exception as error:
        pipeline_completed_at = current_utc_time()
        total_elapsed_seconds = (
            time.perf_counter() - pipeline_started_at_counter
        )

        finish_pipeline_audit(
            pipeline_audit_id,
            "FAILED",
            str(error),
            pipeline_completed_at,
        )

        stamp_pipeline_audit_metadata(
            run_id=pipeline_run_id,
            run_type=run_type,
            recovery_of_run_id=recovery_of_run_id,
            backfill_start_date=backfill_start_date,
            backfill_end_date=backfill_end_date,
        )

        print_separator()
        print("[FAILED] PIPELINE หยุดทำงานเนื่องจาก Step ล้มเหลว")
        print(f"[INFO] run_id: {pipeline_run_id}")
        print(
            f"[INFO] เวลาก่อนล้มเหลว: "
            f"{total_elapsed_seconds:.2f} วินาที"
        )

        write_log(
            "PIPELINE FAILED | "
            f"run_id={pipeline_run_id} | "
            f"duration={total_elapsed_seconds:.2f} seconds | "
            f"error={error}"
        )
        raise

    total_elapsed_seconds = (
        time.perf_counter() - pipeline_started_at_counter
    )
    pipeline_completed_at = current_utc_time()

    finish_pipeline_audit(
        pipeline_audit_id,
        "SUCCESS",
        None,
        pipeline_completed_at,
    )

    stamp_pipeline_audit_metadata(
        run_id=pipeline_run_id,
        run_type=run_type,
        recovery_of_run_id=recovery_of_run_id,
        backfill_start_date=backfill_start_date,
        backfill_end_date=backfill_end_date,
    )

    print_separator()
    print("[SUCCESS] PIPELINE ทำงานครบทุกขั้นตอน")
    print(f"[INFO] Pipeline mode: {pipeline_mode.upper()}")
    print(f"[INFO] Pipeline run_id: {pipeline_run_id}")
    print(f"[INFO] ฐานข้อมูล: {DATABASE_PATH}")
    print(f"[INFO] Log: {PIPELINE_LOG_PATH}")
    print("[INFO] ระยะเวลาของแต่ละขั้นตอน:")

    for step_name, duration in step_durations.items():
        print(f"  - {step_name}: {duration:.2f} วินาที")

    print(f"[INFO] เวลารวม: {total_elapsed_seconds:.2f} วินาที")
    print_separator()

    write_log(
        "PIPELINE SUCCESS | "
        f"run_id={pipeline_run_id} | mode={pipeline_mode} | "
        f"run_type={run_type} | "
        f"backfill_start={backfill_start_date} | "
        f"backfill_end={backfill_end_date} | "
        f"duration={total_elapsed_seconds:.2f} seconds"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the hybrid e-commerce data pipeline."
    )
    parser.add_argument(
        "--recovery-of",
        dest="recovery_of_run_id",
        default=None,
        help="Failed pipeline run_id that this run is recovering from.",
    )
    parser.add_argument(
        "--backfill-start",
        dest="backfill_start_date",
        default=None,
        help="Backfill start date in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--backfill-end",
        dest="backfill_end_date",
        default=None,
        help="Backfill end date in YYYY-MM-DD format.",
    )

    args = parser.parse_args()

    if args.recovery_of_run_id and (
        args.backfill_start_date or args.backfill_end_date
    ):
        parser.error(
            "--recovery-of cannot be used together with "
            "--backfill-start/--backfill-end."
        )

    try:
        validate_backfill_dates(
            args.backfill_start_date,
            args.backfill_end_date,
        )

        run_pipeline(
            recovery_of_run_id=args.recovery_of_run_id,
            backfill_start_date=args.backfill_start_date,
            backfill_end_date=args.backfill_end_date,
        )

    except FileNotFoundError as error:
        print_separator()
        print(f"[FILE ERROR] {error}")
        write_log(f"PIPELINE FAILED | FILE ERROR | {error}")
        sys.exit(1)

    except json.JSONDecodeError as error:
        print_separator()
        print(f"[CONFIG ERROR] {error}")
        write_log(f"PIPELINE FAILED | CONFIG ERROR | {error}")
        sys.exit(1)

    except ValueError as error:
        print_separator()
        print(f"[CONFIG/VALIDATION ERROR] {error}")
        write_log(f"PIPELINE FAILED | CONFIG/VALIDATION ERROR | {error}")
        sys.exit(1)

    except sqlite3.Error as error:
        print_separator()
        print(f"[DATABASE ERROR] {error}")
        write_log(f"PIPELINE FAILED | DATABASE ERROR | {error}")
        sys.exit(1)

    except Exception as error:
        print_separator()
        print(f"[UNEXPECTED ERROR] {error}")
        write_log(f"PIPELINE FAILED | UNEXPECTED ERROR | {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()

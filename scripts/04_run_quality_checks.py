from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import re
import sqlite3
import sys
import uuid


PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)

CONFIG_PATH = (
    PROJECT_ROOT
    / "config"
    / "pipeline_config.json"
)

QUALITY_DIRECTORY = PROJECT_ROOT / "quality_checks"

NULL_CHECK_FILE = QUALITY_DIRECTORY / "01_null_checks.sql"
DUPLICATE_CHECK_FILE = QUALITY_DIRECTORY / "02_duplicate_checks.sql"
REFERENTIAL_CHECK_FILE = QUALITY_DIRECTORY / "03_referential_integrity.sql"
RECONCILIATION_CHECK_FILE = QUALITY_DIRECTORY / "04_reconciliation_checks.sql"
BUSINESS_RULE_CHECK_FILE = QUALITY_DIRECTORY / "05_business_rule_checks.sql"
INFLUENCER_CHECK_FILE = QUALITY_DIRECTORY / "06_influencer_payment_checks.sql"
FRESHNESS_CHECK_FILE = QUALITY_DIRECTORY / "07_freshness_checks.sql"

QUALITY_CHECK_FILES = [
    NULL_CHECK_FILE,
    DUPLICATE_CHECK_FILE,
    REFERENTIAL_CHECK_FILE,
    RECONCILIATION_CHECK_FILE,
    BUSINESS_RULE_CHECK_FILE,
    INFLUENCER_CHECK_FILE,
    FRESHNESS_CHECK_FILE,
]

PIPELINE_NAME = "ecommerce_quality_check_pipeline"

VALID_RUN_TYPES = {
    "NORMAL",
    "RECOVERY",
    "BACKFILL",
}

FRESHNESS_THRESHOLD_PLACEHOLDER = "__FRESHNESS_THRESHOLD_HOURS__"
AMOUNT_TOLERANCE_PLACEHOLDER = "__AMOUNT_TOLERANCE__"
ALLOWED_ORDER_STATUSES_PLACEHOLDER = "__ALLOWED_ORDER_STATUSES__"
ALLOWED_PAYMENT_METHODS_PLACEHOLDER = "__ALLOWED_PAYMENT_METHODS__"
ALLOWED_PAYMENT_STATUSES_PLACEHOLDER = "__ALLOWED_PAYMENT_STATUSES__"
ALLOWED_INFLUENCER_PAYMENT_STATUSES_PLACEHOLDER = (
    "__ALLOWED_INFLUENCER_PAYMENT_STATUSES__"
)

CORE_TABLES = {
    "customers",
    "products",
    "orders",
    "order_items",
    "payments",
    "campaigns",
    "influencers",
    "influencer_payments",
    "rejected_influencer_records",
}

FILE_SCOPE_TABLES = {
    "01_null_checks.sql": CORE_TABLES,
    "02_duplicate_checks.sql": {
        "stg_customers",
        "customers",
        "products",
        "orders",
        "order_items",
        "payments",
        "campaigns",
        "influencers",
        "influencer_payments",
    },
    "03_referential_integrity.sql": {
        "stg_orders",
        "orders",
        "order_items",
        "payments",
        "influencer_payments",
    },
    "04_reconciliation_checks.sql": {
        "orders",
        "order_items",
        "payments",
    },
    "05_business_rule_checks.sql": {
        "customers",
        "products",
        "orders",
        "order_items",
        "payments",
    },
    "06_influencer_payment_checks.sql": {
        "campaigns",
        "influencers",
        "influencer_payments",
        "rejected_influencer_records",
    },
    "07_freshness_checks.sql": {
        "stg_customers",
        "stg_products",
        "stg_orders",
        "stg_order_items",
        "stg_payments",
    },
}

INFLUENCER_CRITICAL_CHECKS = {
    "MISSING_CAMPAIGN_REFERENCE",
    "MISSING_INFLUENCER_REFERENCE",
    "DUPLICATE_SOURCE_LOCATION",
    "DUPLICATE_RECORD_HASH",
    "UNMASKED_ACCOUNT_NAME",
    "INVALID_BANK_ACCOUNT_HASH",
    "INVALID_PHONE_HASH",
    "RAW_PHONE_FOUND_IN_NOTES",
}

INFLUENCER_WARNING_CHECKS = {
    "UNKNOWN_CAMPAIGN_NAME",
    "UNKNOWN_SOURCE_SECTION",
}


def current_utc_time() -> str:
    return datetime.now(
        timezone.utc
    ).strftime("%Y-%m-%d %H:%M:%S")


def read_pipeline_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(
            f"ไม่พบ Pipeline Config: {CONFIG_PATH}"
        )

    with CONFIG_PATH.open(
        mode="r",
        encoding="utf-8",
    ) as config_file:
        config = json.load(config_file)

    if not isinstance(config, dict):
        raise ValueError(
            "pipeline_config.json ต้องเป็น JSON object"
        )

    return config


def get_positive_number(
    config: dict,
    key: str,
) -> float:
    quality_config = config.get("quality", {})
    raw_value = quality_config.get(key)

    if raw_value is None:
        raise ValueError(
            f"ไม่พบ quality.{key} ใน pipeline_config.json"
        )

    if isinstance(raw_value, bool):
        raise ValueError(
            f"quality.{key} ต้องเป็นตัวเลข"
        )

    try:
        value = float(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"quality.{key} ต้องเป็นตัวเลข"
        ) from error

    if value <= 0:
        raise ValueError(
            f"quality.{key} ต้องมากกว่า 0"
        )

    return value


def get_nonnegative_number(
    config: dict,
    key: str,
) -> float:
    quality_config = config.get("quality", {})
    raw_value = quality_config.get(key)

    if raw_value is None:
        raise ValueError(
            f"ไม่พบ quality.{key} ใน pipeline_config.json"
        )

    if isinstance(raw_value, bool):
        raise ValueError(
            f"quality.{key} ต้องเป็นตัวเลข"
        )

    try:
        value = float(raw_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"quality.{key} ต้องเป็นตัวเลข"
        ) from error

    if value < 0:
        raise ValueError(
            f"quality.{key} ต้องไม่น้อยกว่า 0"
        )

    return value


def get_allowed_values(
    config: dict,
    key: str,
) -> list[str]:
    quality_config = config.get("quality", {})
    values = quality_config.get(key)

    if not isinstance(values, list) or not values:
        raise ValueError(
            f"quality.{key} ต้องเป็น list ที่ไม่ว่าง"
        )

    cleaned_values = []
    for value in values:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"quality.{key} ต้องมีแต่ข้อความที่ไม่ว่าง"
            )
        cleaned_values.append(value.strip().upper())

    return cleaned_values


def get_threshold_config(config: dict) -> tuple[int, float]:
    quality_config = config.get("quality", {})
    thresholds = quality_config.get("thresholds", {})

    raw_count = thresholds.get("error_max_issue_count")
    raw_rate = thresholds.get("error_max_issue_rate_percent")

    if isinstance(raw_count, bool):
        raise ValueError(
            "quality.thresholds.error_max_issue_count "
            "ต้องเป็นจำนวนเต็ม"
        )

    try:
        max_count = int(raw_count)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "quality.thresholds.error_max_issue_count "
            "ต้องเป็นจำนวนเต็ม"
        ) from error

    try:
        max_rate = float(raw_rate)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "quality.thresholds.error_max_issue_rate_percent "
            "ต้องเป็นตัวเลข"
        ) from error

    if max_count < 0:
        raise ValueError(
            "error_max_issue_count ต้องไม่น้อยกว่า 0"
        )

    if max_rate < 0 or max_rate > 100:
        raise ValueError(
            "error_max_issue_rate_percent ต้องอยู่ระหว่าง 0 ถึง 100"
        )

    return max_count, max_rate


def sql_quote_list(values: list[str]) -> str:
    return ", ".join(
        "'" + value.replace("'", "''") + "'"
        for value in values
    )


def get_pipeline_run_type() -> str:
    run_type = (
        os.environ.get(
            "PIPELINE_RUN_TYPE",
            "NORMAL",
        )
        .strip()
        .upper()
    )

    if run_type not in VALID_RUN_TYPES:
        raise ValueError(
            "PIPELINE_RUN_TYPE ไม่ถูกต้อง: "
            f"{run_type}. รองรับ NORMAL, RECOVERY, BACKFILL"
        )

    return run_type


def get_quality_check_files_for_run(
    run_type: str,
) -> list[Path]:
    if run_type != "BACKFILL":
        return QUALITY_CHECK_FILES

    return [
        file_path
        for file_path in QUALITY_CHECK_FILES
        if file_path != FRESHNESS_CHECK_FILE
    ]


def read_sql_file(file_path: Path) -> str:
    if not file_path.exists():
        raise FileNotFoundError(
            f"ไม่พบไฟล์ Quality Check: {file_path}"
        )

    sql_script = file_path.read_text(
        encoding="utf-8"
    )

    if not sql_script.strip():
        raise ValueError(
            f"ไฟล์ Quality Check ว่างเปล่า: {file_path}"
        )

    return sql_script


def render_quality_check_sql(
    file_path: Path,
    sql_script: str,
    config: dict,
) -> str:
    replacements = {}

    if file_path == FRESHNESS_CHECK_FILE:
        replacements[FRESHNESS_THRESHOLD_PLACEHOLDER] = str(
            get_positive_number(
                config,
                "freshness_threshold_hours",
            )
        )

    elif file_path == RECONCILIATION_CHECK_FILE:
        replacements[AMOUNT_TOLERANCE_PLACEHOLDER] = str(
            get_nonnegative_number(
                config,
                "amount_tolerance",
            )
        )

    elif file_path == BUSINESS_RULE_CHECK_FILE:
        replacements[ALLOWED_ORDER_STATUSES_PLACEHOLDER] = (
            sql_quote_list(
                get_allowed_values(
                    config,
                    "allowed_order_statuses",
                )
            )
        )
        replacements[ALLOWED_PAYMENT_METHODS_PLACEHOLDER] = (
            sql_quote_list(
                get_allowed_values(
                    config,
                    "allowed_payment_methods",
                )
            )
        )
        replacements[ALLOWED_PAYMENT_STATUSES_PLACEHOLDER] = (
            sql_quote_list(
                get_allowed_values(
                    config,
                    "allowed_payment_statuses",
                )
            )
        )

    elif file_path == INFLUENCER_CHECK_FILE:
        replacements[
            ALLOWED_INFLUENCER_PAYMENT_STATUSES_PLACEHOLDER
        ] = sql_quote_list(
            get_allowed_values(
                config,
                "allowed_influencer_payment_statuses",
            )
        )

    rendered_sql = sql_script

    for placeholder, replacement in replacements.items():
        if placeholder not in rendered_sql:
            raise ValueError(
                f"{file_path.name} ไม่มี placeholder {placeholder}"
            )
        rendered_sql = rendered_sql.replace(
            placeholder,
            replacement,
        )

    unresolved_placeholders = re_placeholder_tokens(
        rendered_sql
    )
    if unresolved_placeholders:
        raise ValueError(
            f"{file_path.name} ยังมี placeholder ที่ไม่ได้แทนค่า: "
            f"{sorted(unresolved_placeholders)}"
        )

    return rendered_sql


def re_placeholder_tokens(sql_script: str) -> set[str]:
    import re

    return set(
        re.findall(
            r"__[A-Z0-9_]+__",
            sql_script,
        )
    )


def execute_check_queries(
    connection: sqlite3.Connection,
    sql_script: str,
) -> list[sqlite3.Row]:
    result_rows = []

    statements = [
        statement.strip()
        for statement in sql_script.split(";")
        if statement.strip()
    ]

    for statement in statements:
        cursor = connection.execute(statement)

        if cursor.description is not None:
            result_rows.extend(
                cursor.fetchall()
            )

    return result_rows


def table_exists(
    connection: sqlite3.Connection,
    table_name: str,
) -> bool:
    cursor = connection.execute(
        """
        SELECT COUNT(*)
        FROM sqlite_master
        WHERE type = 'table'
          AND name = ?;
        """,
        (table_name,),
    )
    return cursor.fetchone()[0] == 1


def get_scope_row_count(
    connection: sqlite3.Connection,
    file_name: str,
) -> int:
    total = 0

    for table_name in sorted(
        FILE_SCOPE_TABLES.get(file_name, set())
    ):
        if not table_exists(connection, table_name):
            continue

        cursor = connection.execute(
            f"SELECT COUNT(*) FROM {table_name};"
        )
        total += int(cursor.fetchone()[0])

    return total


def get_affected_count(
    file_name: str,
    row: sqlite3.Row,
) -> int:
    row_values = dict(row)

    if "null_count" in row_values:
        return max(int(row_values["null_count"]), 0)

    if "duplicate_count" in row_values:
        # Count only duplicate rows beyond the first valid occurrence.
        return max(
            int(row_values["duplicate_count"]) - 1,
            1,
        )

    if "affected_rows" in row_values:
        return max(int(row_values["affected_rows"]), 0)

    return 1


def classify_issue(
    file_name: str,
    row: sqlite3.Row,
) -> str:
    row_values = dict(row)

    if file_name == "01_null_checks.sql":
        return "ERROR"

    if file_name == "02_duplicate_checks.sql":
        table_name = str(
            row_values.get("table_name", "")
        )
        if table_name.startswith("stg_"):
            return "WARNING"
        return "CRITICAL"

    if file_name == "03_referential_integrity.sql":
        child_table = str(
            row_values.get("child_table", "")
        )
        if child_table.startswith("stg_"):
            return "WARNING"
        return "CRITICAL"

    if file_name == "04_reconciliation_checks.sql":
        return "CRITICAL"

    if file_name == "05_business_rule_checks.sql":
        return "ERROR"

    if file_name == "06_influencer_payment_checks.sql":
        check_name = str(
            row_values.get("check_name", "")
        ).upper()

        if check_name in INFLUENCER_CRITICAL_CHECKS:
            return "CRITICAL"

        if check_name in INFLUENCER_WARNING_CHECKS:
            return "WARNING"

        return "ERROR"

    if file_name == "07_freshness_checks.sql":
        freshness_status = str(
            row_values.get("freshness_status", "")
        ).upper()

        if freshness_status == "NOT_LOADED":
            return "CRITICAL"

        return "ERROR"

    return "ERROR"


def summarize_issues(
    file_name: str,
    result_rows: list[sqlite3.Row],
) -> dict:
    summary = {
        "CRITICAL": 0,
        "ERROR": 0,
        "WARNING": 0,
    }

    for row in result_rows:
        severity = classify_issue(
            file_name,
            row,
        )
        summary[severity] += get_affected_count(
            file_name,
            row,
        )

    return summary


def evaluate_quality_result(
    file_name: str,
    result_rows: list[sqlite3.Row],
    evaluated_rows: int,
    error_max_issue_count: int,
    error_max_issue_rate_percent: float,
) -> dict:
    summary = summarize_issues(
        file_name,
        result_rows,
    )

    critical_count = summary["CRITICAL"]
    error_count = summary["ERROR"]
    warning_count = summary["WARNING"]

    denominator = max(evaluated_rows, 1)
    error_rate_percent = (
        error_count / denominator
    ) * 100

    if critical_count > 0:
        outcome = "FAIL"
        reason = (
            f"CRITICAL issue detected: {critical_count}"
        )

    elif (
        error_count > error_max_issue_count
        or error_rate_percent
        > error_max_issue_rate_percent
    ):
        outcome = "FAIL"
        reason = (
            "ERROR threshold exceeded: "
            f"count={error_count}/"
            f"{error_max_issue_count}, "
            f"rate={error_rate_percent:.4f}%/"
            f"{error_max_issue_rate_percent:.4f}%"
        )

    elif error_count > 0 or warning_count > 0:
        outcome = "WARN"
        reason = (
            "Issues detected within tolerance: "
            f"ERROR={error_count}, "
            f"WARNING={warning_count}, "
            f"error_rate={error_rate_percent:.4f}%"
        )

    else:
        outcome = "PASS"
        reason = "No data quality issues detected"

    return {
        "outcome": outcome,
        "critical_count": critical_count,
        "error_count": error_count,
        "warning_count": warning_count,
        "issue_count": (
            critical_count
            + error_count
            + warning_count
        ),
        "evaluated_rows": evaluated_rows,
        "error_rate_percent": error_rate_percent,
        "reason": reason,
    }


def insert_audit_record(
    connection: sqlite3.Connection,
    run_id: str,
    step_name: str,
    run_status: str,
    rows_processed: int,
    rows_rejected: int,
    error_message: str | None,
    started_at: str,
    completed_at: str,
) -> None:
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
        VALUES (
            ?, ?, ?, ?, ?, 0, 0,
            ?, ?, ?, ?
        );
        """,
        (
            PIPELINE_NAME,
            run_id,
            step_name,
            run_status,
            rows_processed,
            rows_rejected,
            error_message,
            started_at,
            completed_at,
        ),
    )

    connection.commit()



def normalize_quality_alert_signature(
    error_type: str | None,
    message: str | None,
) -> str:
    normalized_type = (error_type or "none").strip().lower()
    normalized_message = (message or "no error").strip().lower()

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
        r"\b\d+(?:\.\d+)?%",
        "<percent>",
        normalized_message,
    )
    normalized_message = re.sub(
        r"\b\d+(?:\.\d+)?\b",
        "<number>",
        normalized_message,
    )
    normalized_message = re.sub(
        r"\s+",
        " ",
        normalized_message,
    ).strip()

    return f"{normalized_type}::{normalized_message}"


def build_quality_alert_fingerprint(
    pipeline_name: str,
    step_name: str,
    alert_type: str,
    severity: str,
    error_type: str | None,
    message: str | None,
) -> str:
    normalized_signature = normalize_quality_alert_signature(
        error_type=error_type,
        message=message,
    )

    fingerprint_source = "::".join(
        (
            pipeline_name.strip().lower(),
            step_name.strip().upper(),
            alert_type.strip().upper(),
            severity.strip().upper(),
            normalized_signature,
        )
    )

    return hashlib.sha256(
        fingerprint_source.encode("utf-8")
    ).hexdigest()


def record_quality_alert(
    run_id: str,
    step_name: str,
    evaluation: dict,
    detected_at: str,
) -> None:
    outcome = str(
        evaluation.get("outcome", "")
    ).strip().upper()

    if outcome == "PASS":
        return

    if outcome == "WARN":
        alert_type = "DATA_QUALITY_WARNING"
        severity = "WARNING"
        error_type = "DataQualityWarning"
        title = f"Data quality warning: {step_name}"

    elif outcome == "FAIL":
        alert_type = "DATA_QUALITY_FAILURE"

        if int(evaluation.get("critical_count", 0)) > 0:
            severity = "CRITICAL"
            error_type = "DataQualityCriticalFailure"
        else:
            severity = "ERROR"
            error_type = "DataQualityFailure"

        title = f"Data quality failure: {step_name}"

    else:
        return

    critical_count = int(
        evaluation.get("critical_count", 0)
    )
    error_count = int(
        evaluation.get("error_count", 0)
    )
    warning_count = int(
        evaluation.get("warning_count", 0)
    )
    error_rate_percent = float(
        evaluation.get("error_rate_percent", 0.0)
    )
    reason = str(
        evaluation.get(
            "reason",
            "No quality evaluation reason was provided.",
        )
    )

    message = (
        f"Quality check {step_name} outcome={outcome}; "
        f"CRITICAL={critical_count}; "
        f"ERROR={error_count}; "
        f"WARNING={warning_count}; "
        f"error_rate={error_rate_percent:.4f}%; "
        f"{reason}"
    )

    signature_message = (
        f"outcome={outcome}; "
        f"has_critical={critical_count > 0}; "
        f"has_error={error_count > 0}; "
        f"has_warning={warning_count > 0}; "
        f"reason={reason}"
    )

    normalized_error_signature = (
        normalize_quality_alert_signature(
            error_type=error_type,
            message=signature_message,
        )
    )

    alert_fingerprint = (
        build_quality_alert_fingerprint(
            pipeline_name=PIPELINE_NAME,
            step_name=step_name,
            alert_type=alert_type,
            severity=severity,
            error_type=error_type,
            message=signature_message,
        )
    )

    connection: sqlite3.Connection | None = None

    try:
        connection = sqlite3.connect(
            DATABASE_PATH
        )
        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )
        connection.execute(
            "BEGIN IMMEDIATE;"
        )

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
                    ?, ?, 'QUALITY_GATE', ?, ?, 'OPEN',
                    ?, ?, ?, 1, ?, ?, ?, ?, 1
                );
                """,
                (
                    alert_fingerprint,
                    alert_fingerprint,
                    alert_type,
                    severity,
                    PIPELINE_NAME,
                    run_id,
                    step_name,
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
                    attempt_number = 1,
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
            VALUES (?, ?, 1, ?, ?, ?, ?);
            """,
            (
                alert_id,
                run_id,
                detected_at,
                error_type,
                message,
                normalized_error_signature,
            ),
        )

        connection.commit()

    except sqlite3.Error as error:
        if connection is not None:
            connection.rollback()

        print(
            "[QUALITY ALERT WRITE WARNING] "
            f"{step_name} | "
            f"{type(error).__name__}: {error}"
        )

    finally:
        if connection is not None:
            connection.close()

def print_check_results(
    file_name: str,
    result_rows: list[sqlite3.Row],
    evaluation: dict,
) -> None:
    outcome = evaluation["outcome"]

    print(
        f"[{outcome}] {file_name}: "
        f"evaluated={evaluation['evaluated_rows']}, "
        f"CRITICAL={evaluation['critical_count']}, "
        f"ERROR={evaluation['error_count']}, "
        f"WARNING={evaluation['warning_count']}, "
        f"error_rate="
        f"{evaluation['error_rate_percent']:.4f}%"
    )

    if not result_rows:
        return

    for row_number, row in enumerate(
        result_rows,
        start=1,
    ):
        severity = classify_issue(
            file_name,
            row,
        )
        affected_count = get_affected_count(
            file_name,
            row,
        )

        print(
            f"  {row_number}. "
            f"severity={severity}, "
            f"affected={affected_count}, "
            f"data={dict(row)}"
        )


def run_quality_check(
    connection: sqlite3.Connection,
    run_id: str,
    file_path: Path,
    config: dict,
    error_max_issue_count: int,
    error_max_issue_rate_percent: float,
) -> dict:
    step_name = file_path.stem
    started_at = current_utc_time()

    try:
        sql_script = read_sql_file(
            file_path
        )

        sql_script = render_quality_check_sql(
            file_path=file_path,
            sql_script=sql_script,
            config=config,
        )

        result_rows = execute_check_queries(
            connection=connection,
            sql_script=sql_script,
        )

        evaluated_rows = get_scope_row_count(
            connection,
            file_path.name,
        )

        evaluation = evaluate_quality_result(
            file_name=file_path.name,
            result_rows=result_rows,
            evaluated_rows=evaluated_rows,
            error_max_issue_count=(
                error_max_issue_count
            ),
            error_max_issue_rate_percent=(
                error_max_issue_rate_percent
            ),
        )

        completed_at = current_utc_time()

        run_status = (
            "FAILED"
            if evaluation["outcome"] == "FAIL"
            else "SUCCESS"
        )

        audit_message = (
            None
            if evaluation["outcome"] == "PASS"
            else (
                f"outcome={evaluation['outcome']}; "
                f"CRITICAL={evaluation['critical_count']}; "
                f"ERROR={evaluation['error_count']}; "
                f"WARNING={evaluation['warning_count']}; "
                f"error_rate="
                f"{evaluation['error_rate_percent']:.4f}%; "
                f"{evaluation['reason']}"
            )
        )

        insert_audit_record(
            connection=connection,
            run_id=run_id,
            step_name=step_name,
            run_status=run_status,
            rows_processed=evaluated_rows,
            rows_rejected=evaluation["issue_count"],
            error_message=audit_message,
            started_at=started_at,
            completed_at=completed_at,
        )

        print_check_results(
            file_name=file_path.name,
            result_rows=result_rows,
            evaluation=evaluation,
        )

        record_quality_alert(
            run_id=run_id,
            step_name=step_name,
            evaluation=evaluation,
            detected_at=completed_at,
        )

        return evaluation

    except Exception as error:
        completed_at = current_utc_time()

        insert_audit_record(
            connection=connection,
            run_id=run_id,
            step_name=step_name,
            run_status="FAILED",
            rows_processed=0,
            rows_rejected=0,
            error_message=str(error),
            started_at=started_at,
            completed_at=completed_at,
        )

        raise


def run_all_quality_checks() -> None:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            "ยังไม่พบฐานข้อมูล กรุณารัน "
            "scripts/01_setup_database.py ก่อน"
        )

    run_id = (
        os.environ.get("PIPELINE_RUN_ID")
        or str(uuid.uuid4())
    )

    run_type = get_pipeline_run_type()
    config = read_pipeline_config()

    freshness_threshold_hours = get_positive_number(
        config,
        "freshness_threshold_hours",
    )
    amount_tolerance = get_nonnegative_number(
        config,
        "amount_tolerance",
    )

    error_max_issue_count, error_max_issue_rate_percent = (
        get_threshold_config(config)
    )

    quality_check_files = (
        get_quality_check_files_for_run(
            run_type
        )
    )

    print(
        f"[INFO] Quality check run_id: {run_id}"
    )
    print(
        f"[INFO] Pipeline run_type: {run_type}"
    )
    print(
        "[INFO] Freshness threshold: "
        f"{freshness_threshold_hours:g} hours"
    )
    print(
        "[INFO] Amount tolerance: "
        f"{amount_tolerance:g}"
    )
    print(
        "[INFO] ERROR threshold: "
        f"count <= {error_max_issue_count}, "
        f"rate <= {error_max_issue_rate_percent:g}%"
    )
    print(
        "[INFO] CRITICAL policy: "
        "any issue fails"
    )
    print(
        "[INFO] WARNING policy: "
        "report only; does not stop pipeline"
    )

    if run_type == "BACKFILL":
        print(
            "[INFO] BACKFILL mode: "
            "ข้าม 07_freshness_checks.sql "
            "เพื่อป้องกัน Historical Backfill "
            "กระทบ Normal Watermark Freshness"
        )

    total_critical = 0
    total_error = 0
    total_warning = 0
    failed_files = []

    with sqlite3.connect(
        DATABASE_PATH
    ) as connection:
        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON;"
        )

        for quality_check_file in (
            quality_check_files
        ):
            evaluation = run_quality_check(
                connection=connection,
                run_id=run_id,
                file_path=quality_check_file,
                config=config,
                error_max_issue_count=(
                    error_max_issue_count
                ),
                error_max_issue_rate_percent=(
                    error_max_issue_rate_percent
                ),
            )

            total_critical += (
                evaluation["critical_count"]
            )
            total_error += (
                evaluation["error_count"]
            )
            total_warning += (
                evaluation["warning_count"]
            )

            if evaluation["outcome"] == "FAIL":
                failed_files.append(
                    quality_check_file.name
                )

    print("-" * 60)
    print(
        "[SUMMARY] "
        f"CRITICAL={total_critical}, "
        f"ERROR={total_error}, "
        f"WARNING={total_warning}"
    )

    if not failed_files:
        print(
            "[SUCCESS] ข้อมูลผ่าน Quality Gate "
            "(รวม issues ที่อยู่ภายใน tolerance)"
        )
        return

    print(
        "[FAILED] Quality Gate ไม่ผ่าน: "
        + ", ".join(failed_files)
    )

    raise ValueError(
        "Quality Checks ไม่ผ่าน "
        f"{len(failed_files)} rule file(s)"
    )


def main() -> None:
    try:
        run_all_quality_checks()

    except FileNotFoundError as error:
        print(
            f"[FILE ERROR] {error}"
        )
        sys.exit(1)

    except json.JSONDecodeError as error:
        print(
            f"[CONFIG ERROR] JSON ไม่ถูกต้อง: {error}"
        )
        sys.exit(1)

    except ValueError as error:
        print(
            f"[QUALITY ERROR] {error}"
        )
        sys.exit(1)

    except sqlite3.Error as error:
        print(
            f"[DATABASE ERROR] {error}"
        )
        sys.exit(1)

    except Exception as error:
        print(
            f"[UNEXPECTED ERROR] {error}"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()

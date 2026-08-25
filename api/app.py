from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from pydantic import BaseModel


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DB_PATH = PROJECT_ROOT / "database" / "ecommerce_data_engineering.db"

app = FastAPI(
    title="Project 01 E-Commerce Serving API",
    version="1.0.0",
    description=(
        "Read-only REST API over curated SQLite serving views. "
        "Raw source files and write operations are intentionally excluded."
    ),
)


class HealthResponse(BaseModel):
    status: str
    database: str
    read_only: bool


class DailySalesResponse(BaseModel):
    order_date: str
    total_orders: int
    unique_customers: int
    units_sold: int
    total_revenue: float
    average_order_value: float


class ProductSalesResponse(BaseModel):
    product_id: int
    product_name: str
    category: str
    unit_price: float
    stock_quantity: int
    total_orders: int
    units_sold: int
    total_revenue: float


class PipelineRunResponse(BaseModel):
    run_id: str
    pipeline_name: str
    pipeline_started_at: str | None
    pipeline_completed_at: str | None
    total_steps: int
    total_rows_processed: int
    total_rows_inserted: int
    total_rows_updated: int
    total_rows_rejected: int
    pipeline_status: str


class QualityIssueResponse(BaseModel):
    quality_source: str
    issue_type: str
    issue_count: int
    affected_source_count: int
    first_detected_at: str | None
    latest_detected_at: str | None


class AlertResponse(BaseModel):
    alert_id: int
    alert_type: str
    severity: str
    status: str
    pipeline_name: str
    step_name: str | None
    title: str
    first_detected_at: str
    last_detected_at: str
    occurrence_count: int


def _connect_read_only() -> sqlite3.Connection:
    database_uri = f"file:{DB_PATH.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(database_uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _fetch_all(
    sql: str,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    with closing(_connect_read_only()) as connection:
        rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    with closing(_connect_read_only()) as connection:
        connection.execute("SELECT 1;").fetchone()

    return HealthResponse(
        status="ok",
        database=DB_PATH.name,
        read_only=True,
    )


@app.get(
    "/api/v1/sales/daily",
    response_model=list[DailySalesResponse],
)
def get_daily_sales(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    if start_date is not None:
        conditions.append("order_date >= ?")
        params.append(start_date)

    if end_date is not None:
        conditions.append("order_date <= ?")
        params.append(end_date)

    where_clause = (
        f"WHERE {' AND '.join(conditions)}"
        if conditions
        else ""
    )

    return _fetch_all(
        f"""
        SELECT
            order_date,
            total_orders,
            unique_customers,
            units_sold,
            total_revenue,
            average_order_value
        FROM vw_daily_sales_summary
        {where_clause}
        ORDER BY order_date DESC
        LIMIT ?
        """,
        tuple(params + [limit]),
    )


@app.get(
    "/api/v1/products/sales",
    response_model=list[ProductSalesResponse],
)
def get_product_sales(
    category: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    if category is None:
        return _fetch_all(
            """
            SELECT
                product_id,
                product_name,
                category,
                unit_price,
                stock_quantity,
                total_orders,
                units_sold,
                total_revenue
            FROM vw_product_sales_summary
            ORDER BY total_revenue DESC, product_id
            LIMIT ?
            """,
            (limit,),
        )

    return _fetch_all(
        """
        SELECT
            product_id,
            product_name,
            category,
            unit_price,
            stock_quantity,
            total_orders,
            units_sold,
            total_revenue
        FROM vw_product_sales_summary
        WHERE category = ?
        ORDER BY total_revenue DESC, product_id
        LIMIT ?
        """,
        (category, limit),
    )


@app.get(
    "/api/v1/pipelines/runs",
    response_model=list[PipelineRunResponse],
)
def get_pipeline_runs(
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    if status is None:
        return _fetch_all(
            """
            SELECT
                run_id,
                pipeline_name,
                pipeline_started_at,
                pipeline_completed_at,
                total_steps,
                total_rows_processed,
                total_rows_inserted,
                total_rows_updated,
                total_rows_rejected,
                pipeline_status
            FROM vw_pipeline_run_summary
            ORDER BY pipeline_started_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    return _fetch_all(
        """
        SELECT
            run_id,
            pipeline_name,
            pipeline_started_at,
            pipeline_completed_at,
            total_steps,
            total_rows_processed,
            total_rows_inserted,
            total_rows_updated,
            total_rows_rejected,
            pipeline_status
        FROM vw_pipeline_run_summary
        WHERE pipeline_status = ?
        ORDER BY pipeline_started_at DESC
        LIMIT ?
        """,
        (status.upper(), limit),
    )


@app.get(
    "/api/v1/quality/issues",
    response_model=list[QualityIssueResponse],
)
def get_quality_issues(
    source: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    if source is None:
        return _fetch_all(
            """
            SELECT
                quality_source,
                issue_type,
                issue_count,
                affected_source_count,
                first_detected_at,
                latest_detected_at
            FROM vw_data_quality_summary
            ORDER BY latest_detected_at DESC, issue_count DESC
            LIMIT ?
            """,
            (limit,),
        )

    return _fetch_all(
        """
        SELECT
            quality_source,
            issue_type,
            issue_count,
            affected_source_count,
            first_detected_at,
            latest_detected_at
        FROM vw_data_quality_summary
        WHERE quality_source = ?
        ORDER BY latest_detected_at DESC, issue_count DESC
        LIMIT ?
        """,
        (source, limit),
    )


@app.get(
    "/api/v1/alerts",
    response_model=list[AlertResponse],
)
def get_alerts(
    status: str | None = None,
    severity: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    conditions: list[str] = []
    params: list[Any] = []

    if status is not None:
        conditions.append("status = ?")
        params.append(status.upper())

    if severity is not None:
        conditions.append("severity = ?")
        params.append(severity.upper())

    where_clause = (
        f"WHERE {' AND '.join(conditions)}"
        if conditions
        else ""
    )

    return _fetch_all(
        f"""
        SELECT
            alert_id,
            alert_type,
            severity,
            status,
            pipeline_name,
            step_name,
            title,
            first_detected_at,
            last_detected_at,
            occurrence_count
        FROM vw_pipeline_alert_monitoring
        {where_clause}
        ORDER BY
            status_priority,
            severity_priority,
            last_detected_at DESC,
            alert_id DESC
        LIMIT ?
        """,
        tuple(params + [limit]),
    )

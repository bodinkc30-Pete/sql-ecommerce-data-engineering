from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

import api.app as api_app


class RestApiIntegrationTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = Path(cls.temp_dir.name) / "api_test.db"

        with closing(sqlite3.connect(cls.db_path)) as conn:
            conn.executescript(
                """
                CREATE TABLE vw_daily_sales_summary (
                    order_date TEXT,
                    total_orders INTEGER,
                    unique_customers INTEGER,
                    units_sold INTEGER,
                    total_revenue REAL,
                    average_order_value REAL
                );

                CREATE TABLE vw_product_sales_summary (
                    product_id INTEGER,
                    product_name TEXT,
                    category TEXT,
                    unit_price REAL,
                    stock_quantity INTEGER,
                    total_orders INTEGER,
                    units_sold INTEGER,
                    total_revenue REAL
                );

                CREATE TABLE vw_pipeline_run_summary (
                    run_id TEXT,
                    pipeline_name TEXT,
                    pipeline_started_at TEXT,
                    pipeline_completed_at TEXT,
                    total_steps INTEGER,
                    total_rows_processed INTEGER,
                    total_rows_inserted INTEGER,
                    total_rows_updated INTEGER,
                    total_rows_rejected INTEGER,
                    pipeline_status TEXT
                );

                CREATE TABLE vw_data_quality_summary (
                    quality_source TEXT,
                    issue_type TEXT,
                    issue_count INTEGER,
                    affected_source_count INTEGER,
                    first_detected_at TEXT,
                    latest_detected_at TEXT
                );

                CREATE TABLE vw_pipeline_alert_monitoring (
                    alert_id INTEGER,
                    alert_type TEXT,
                    severity TEXT,
                    status TEXT,
                    status_priority INTEGER,
                    severity_priority INTEGER,
                    pipeline_name TEXT,
                    step_name TEXT,
                    title TEXT,
                    first_detected_at TEXT,
                    last_detected_at TEXT,
                    occurrence_count INTEGER,
                    message TEXT,
                    latest_raw_error_message TEXT
                );
                """
            )

            conn.executemany(
                "INSERT INTO vw_daily_sales_summary VALUES (?, ?, ?, ?, ?, ?)",
                [
                    ("2026-01-17", 1, 1, 2, 3780.0, 3780.0),
                    ("2026-01-18", 1, 1, 1, 890.0, 890.0),
                    ("2026-01-19", 1, 1, 1, 1450.0, 1450.0),
                ],
            )

            conn.executemany(
                "INSERT INTO vw_product_sales_summary VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (101, "Mechanical Keyboard", "Accessories", 2500.5, 25, 1, 1, 2500.5),
                    (102, "Wireless Mouse", "Accessories", 890.0, 40, 2, 3, 2670.0),
                    (105, "Webcam HD", "Electronics", 1890.0, 15, 1, 2, 3780.0),
                ],
            )

            conn.executemany(
                "INSERT INTO vw_pipeline_run_summary VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        "run-success",
                        "hybrid_ecommerce_data_pipeline",
                        "2026-08-24 15:28:23",
                        "2026-08-24 15:28:30",
                        5,
                        54,
                        27,
                        0,
                        0,
                        "SUCCESS",
                    ),
                    (
                        "run-failed",
                        "hybrid_ecommerce_data_pipeline",
                        "2026-08-23 15:19:50",
                        "2026-08-23 15:19:51",
                        2,
                        10,
                        5,
                        0,
                        1,
                        "FAILED",
                    ),
                ],
            )

            conn.executemany(
                "INSERT INTO vw_data_quality_summary VALUES (?, ?, ?, ?, ?, ?)",
                [
                    (
                        "pipeline_audit",
                        "03_referential_integrity",
                        3,
                        3,
                        "2026-08-10 18:14:37",
                        "2026-08-23 19:01:46",
                    ),
                    (
                        "rejected_source_records",
                        "SCHEMA_DRIFT",
                        1,
                        1,
                        "2026-08-22 20:30:16",
                        "2026-08-22 20:30:16",
                    ),
                ],
            )

            conn.executemany(
                "INSERT INTO vw_pipeline_alert_monitoring VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        1,
                        "STEP_FAILURE",
                        "CRITICAL",
                        "OPEN",
                        1,
                        1,
                        "hybrid_ecommerce_data_pipeline",
                        "LOAD_RAW_DATA",
                        "Pipeline step failed: LOAD_RAW_DATA",
                        "2026-08-22 20:30:16",
                        "2026-08-22 20:30:16",
                        1,
                        "private message must not be served",
                        "private raw error must not be served",
                    ),
                    (
                        2,
                        "SLA_BREACH",
                        "WARNING",
                        "OPEN",
                        1,
                        3,
                        "hybrid_ecommerce_data_pipeline",
                        "LOAD_RAW_DATA",
                        "Pipeline SLA breached: LOAD_RAW_DATA",
                        "2026-08-23 12:43:04",
                        "2026-08-23 12:43:04",
                        1,
                        "another private message",
                        "another private raw error",
                    ),
                ],
            )

            conn.commit()

        cls.original_db_path = api_app.DB_PATH
        api_app.DB_PATH = cls.db_path
        cls.client = TestClient(api_app.app)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client.close()
        api_app.DB_PATH = cls.original_db_path
        cls.temp_dir.cleanup()

    def test_health_reports_read_only_database(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "status": "ok",
                "database": "api_test.db",
                "read_only": True,
            },
        )

    def test_daily_sales_filters_date_range_and_limit(self) -> None:
        response = self.client.get(
            "/api/v1/sales/daily",
            params={
                "start_date": "2026-01-17",
                "end_date": "2026-01-18",
                "limit": 100,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            [row["order_date"] for row in payload],
            ["2026-01-18", "2026-01-17"],
        )

    def test_product_sales_filters_category(self) -> None:
        response = self.client.get(
            "/api/v1/products/sales",
            params={"category": "Accessories", "limit": 10},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 2)
        self.assertTrue(
            all(row["category"] == "Accessories" for row in payload)
        )

    def test_pipeline_runs_filters_status(self) -> None:
        response = self.client.get(
            "/api/v1/pipelines/runs",
            params={"status": "SUCCESS", "limit": 10},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["run_id"], "run-success")
        self.assertEqual(payload[0]["pipeline_status"], "SUCCESS")

    def test_quality_issues_filters_source(self) -> None:
        response = self.client.get(
            "/api/v1/quality/issues",
            params={"source": "pipeline_audit", "limit": 10},
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["quality_source"], "pipeline_audit")

    def test_alerts_filter_and_hide_sensitive_details(self) -> None:
        response = self.client.get(
            "/api/v1/alerts",
            params={
                "status": "OPEN",
                "severity": "CRITICAL",
                "limit": 10,
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)

        alert = payload[0]
        self.assertEqual(alert["status"], "OPEN")
        self.assertEqual(alert["severity"], "CRITICAL")
        self.assertNotIn("message", alert)
        self.assertNotIn("latest_raw_error_message", alert)

    def test_api_rejects_mutating_method(self) -> None:
        response = self.client.post(
            "/api/v1/sales/daily",
            json={"order_date": "2026-01-20"},
        )
        self.assertEqual(response.status_code, 405)

    def test_limit_validation_rejects_out_of_range_values(self) -> None:
        response = self.client.get(
            "/api/v1/sales/daily",
            params={"limit": 501},
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()

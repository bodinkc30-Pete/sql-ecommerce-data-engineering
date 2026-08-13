from pathlib import Path
import sqlite3
import unittest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = (
    PROJECT_ROOT
    / "database"
    / "ecommerce_data_engineering.db"
)


class GovernanceLineageAcceptanceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not DATABASE_PATH.exists():
            raise FileNotFoundError(
                f"ไม่พบฐานข้อมูลสำหรับ Governance Acceptance Test: {DATABASE_PATH}"
            )

        cls.connection = sqlite3.connect(DATABASE_PATH)
        cls.connection.execute("PRAGMA foreign_keys = ON;")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.connection.close()

    def test_required_governance_objects_exist(self) -> None:
        required_tables = {
            "data_assets",
            "lineage_edges",
            "lineage_run_events",
        }
        required_views = {
            "vw_data_lineage",
            "vw_lineage_run_history",
            "vw_asset_upstream_dependencies",
            "vw_asset_downstream_dependencies",
        }

        actual_tables = {
            row[0]
            for row in self.connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table';
                """
            )
        }
        actual_views = {
            row[0]
            for row in self.connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'view';
                """
            )
        }

        self.assertTrue(
            required_tables.issubset(actual_tables),
            f"Governance tables missing: {sorted(required_tables - actual_tables)}",
        )
        self.assertTrue(
            required_views.issubset(actual_views),
            f"Governance views missing: {sorted(required_views - actual_views)}",
        )

    def test_asset_keys_are_unique(self) -> None:
        total_assets, distinct_asset_keys = self.connection.execute(
            """
            SELECT
                COUNT(*),
                COUNT(DISTINCT asset_key)
            FROM data_assets;
            """
        ).fetchone()

        self.assertGreater(total_assets, 0)
        self.assertEqual(total_assets, distinct_asset_keys)

        duplicates = self.connection.execute(
            """
            SELECT asset_key, COUNT(*)
            FROM data_assets
            GROUP BY asset_key
            HAVING COUNT(*) > 1;
            """
        ).fetchall()

        self.assertEqual([], duplicates)

    def test_lineage_edges_have_no_orphans_or_self_loops(self) -> None:
        orphan_edges = self.connection.execute(
            """
            SELECT e.lineage_edge_id
            FROM lineage_edges AS e
            LEFT JOIN data_assets AS u
                ON u.asset_id = e.upstream_asset_id
            LEFT JOIN data_assets AS d
                ON d.asset_id = e.downstream_asset_id
            WHERE
                u.asset_id IS NULL
                OR d.asset_id IS NULL;
            """
        ).fetchall()

        self_loops = self.connection.execute(
            """
            SELECT lineage_edge_id
            FROM lineage_edges
            WHERE upstream_asset_id = downstream_asset_id;
            """
        ).fetchall()

        self.assertEqual([], orphan_edges)
        self.assertEqual([], self_loops)

    def test_sqlite_foreign_key_integrity_is_clean(self) -> None:
        violations = self.connection.execute(
            "PRAGMA foreign_key_check;"
        ).fetchall()

        self.assertEqual([], violations)

    def test_recursive_orders_lineage_is_correct_and_deduplicated(self) -> None:
        upstream_rows = self.connection.execute(
            """
            SELECT
                dependency_asset_name,
                depth,
                lineage_path
            FROM vw_asset_upstream_dependencies
            WHERE root_asset_name = 'orders'
            ORDER BY depth, dependency_asset_name;
            """
        ).fetchall()

        downstream_rows = self.connection.execute(
            """
            SELECT
                dependency_asset_name,
                depth,
                lineage_path
            FROM vw_asset_downstream_dependencies
            WHERE root_asset_name = 'orders'
            ORDER BY depth, dependency_asset_name;
            """
        ).fetchall()

        self.assertEqual(
            [
                ("stg_orders", 1, "orders <- stg_orders"),
                ("orders.csv", 2, "orders <- stg_orders <- orders.csv"),
            ],
            upstream_rows,
        )

        self.assertEqual(
            {
                "vw_customer_order_summary",
                "vw_daily_sales_summary",
                "vw_payment_reconciliation",
            },
            {row[0] for row in downstream_rows},
        )

        self.assertEqual(
            len(downstream_rows),
            len({(row[0], row[1], row[2]) for row in downstream_rows}),
        )

    def test_pii_assets_have_valid_classification(self) -> None:
        invalid_pii_assets = self.connection.execute(
            """
            SELECT
                asset_key,
                classification
            FROM data_assets
            WHERE
                contains_pii = 1
                AND classification NOT IN (
                    'CONFIDENTIAL',
                    'RESTRICTED'
                );
            """
        ).fetchall()

        pii_asset_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM data_assets
            WHERE contains_pii = 1;
            """
        ).fetchone()[0]

        self.assertGreater(
            pii_asset_count,
            0,
            "ควรมีอย่างน้อย 1 asset ที่ถูกจัดเป็น PII",
        )
        self.assertEqual([], invalid_pii_assets)

    def test_runtime_lineage_events_have_no_orphans_and_link_to_pipeline_run(self) -> None:
        orphan_events = self.connection.execute(
            """
            SELECT r.lineage_run_event_id
            FROM lineage_run_events AS r
            LEFT JOIN lineage_edges AS e
                ON e.lineage_edge_id = r.lineage_edge_id
            WHERE e.lineage_edge_id IS NULL;
            """
        ).fetchall()

        events_without_pipeline_run = self.connection.execute(
            """
            SELECT DISTINCT r.run_id
            FROM lineage_run_events AS r
            LEFT JOIN pipeline_audit AS p
                ON p.run_id = r.run_id
               AND p.step_name = 'PIPELINE_TOTAL'
            WHERE p.audit_id IS NULL;
            """
        ).fetchall()

        event_count = self.connection.execute(
            """
            SELECT COUNT(*)
            FROM lineage_run_events;
            """
        ).fetchone()[0]

        self.assertGreater(
            event_count,
            0,
            "ยังไม่มี runtime lineage event ให้ตรวจสอบ",
        )
        self.assertEqual([], orphan_events)
        self.assertEqual([], events_without_pipeline_run)

    def test_demo_runtime_lineage_marks_pawchoice_as_skipped(self) -> None:
        # Locate the newest successful runtime-lineage run that contains
        # PawChoice SKIPPED events. This avoids hard-coding a run_id.
        candidate = self.connection.execute(
            """
            SELECT r.run_id
            FROM lineage_run_events AS r
            INNER JOIN pipeline_audit AS p
                ON p.run_id = r.run_id
               AND p.step_name = 'PIPELINE_TOTAL'
               AND p.run_status = 'SUCCESS'
            INNER JOIN lineage_edges AS e
                ON e.lineage_edge_id = r.lineage_edge_id
            INNER JOIN data_assets AS u
                ON u.asset_id = e.upstream_asset_id
            INNER JOIN data_assets AS d
                ON d.asset_id = e.downstream_asset_id
            WHERE
                r.execution_status = 'SKIPPED'
                AND (
                    u.asset_key LIKE 'file://pawchoice/%'
                    OR u.asset_key = 'sqlite://staging/stg_influencer_payments'
                    OR d.asset_key = 'sqlite://staging/stg_influencer_payments'
                    OR d.asset_key IN (
                        'sqlite://core/campaigns',
                        'sqlite://core/influencers',
                        'sqlite://core/influencer_payments',
                        'sqlite://core/rejected_influencer_records'
                    )
                )
            ORDER BY r.lineage_run_event_id DESC
            LIMIT 1;
            """
        ).fetchone()

        self.assertIsNotNone(
            candidate,
            "ไม่พบ successful DEMO-style runtime lineage run ที่มี PawChoice SKIPPED",
        )

        run_id = candidate[0]

        status_counts = dict(
            self.connection.execute(
                """
                SELECT execution_status, COUNT(*)
                FROM lineage_run_events
                WHERE run_id = ?
                GROUP BY execution_status;
                """,
                (run_id,),
            ).fetchall()
        )

        pawchoice_non_skipped = self.connection.execute(
            """
            SELECT
                r.lineage_run_event_id,
                r.execution_status,
                u.asset_name,
                d.asset_name
            FROM lineage_run_events AS r
            INNER JOIN lineage_edges AS e
                ON e.lineage_edge_id = r.lineage_edge_id
            INNER JOIN data_assets AS u
                ON u.asset_id = e.upstream_asset_id
            INNER JOIN data_assets AS d
                ON d.asset_id = e.downstream_asset_id
            WHERE
                r.run_id = ?
                AND (
                    u.asset_key LIKE 'file://pawchoice/%'
                    OR u.asset_key = 'sqlite://staging/stg_influencer_payments'
                    OR d.asset_key = 'sqlite://staging/stg_influencer_payments'
                    OR d.asset_key IN (
                        'sqlite://core/campaigns',
                        'sqlite://core/influencers',
                        'sqlite://core/influencer_payments',
                        'sqlite://core/rejected_influencer_records'
                    )
                )
                AND r.execution_status <> 'SKIPPED';
            """,
            (run_id,),
        ).fetchall()

        self.assertEqual(10, status_counts.get("SUCCESS", 0))
        self.assertEqual(5, status_counts.get("SKIPPED", 0))
        self.assertEqual(0, status_counts.get("FAILED", 0))
        self.assertEqual([], pawchoice_non_skipped)


if __name__ == "__main__":
    unittest.main(verbosity=2)

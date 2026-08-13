PRAGMA foreign_keys = ON;

-- Governance / Lineage
-- Step G3C: Correct dataset-level lineage after validation against
-- schema/04_create_views.sql.
--
-- Corrections:
-- 1) Remove orders -> vw_product_sales_summary because that view reads only
--    products + order_items.
-- 2) Add order_items -> vw_customer_order_summary.
-- 3) Add order_items -> vw_daily_sales_summary.
-- 4) Add order_items -> vw_payment_reconciliation.

DELETE FROM lineage_edges
WHERE lineage_edge_id IN (
    SELECT e.lineage_edge_id
    FROM lineage_edges AS e
    JOIN data_assets AS u
        ON u.asset_id = e.upstream_asset_id
    JOIN data_assets AS d
        ON d.asset_id = e.downstream_asset_id
    WHERE
        u.asset_key = 'sqlite://core/orders'
        AND d.asset_key = 'sqlite://mart/vw_product_sales_summary'
        AND e.transformation_name = 'BUILD_PRODUCT_SALES_SUMMARY_ORDERS'
        AND e.lineage_level = 'DATASET'
);

INSERT INTO lineage_edges (
    upstream_asset_id,
    downstream_asset_id,
    transformation_name,
    transformation_type,
    process_reference,
    lineage_level,
    run_id,
    is_active
)
SELECT
    u.asset_id,
    d.asset_id,
    seed.transformation_name,
    seed.transformation_type,
    'schema/04_create_views.sql',
    'DATASET',
    NULL,
    1
FROM (
    SELECT
        'sqlite://core/order_items' AS upstream_key,
        'sqlite://mart/vw_customer_order_summary' AS downstream_key,
        'BUILD_CUSTOMER_ORDER_SUMMARY_ORDER_ITEMS' AS transformation_name,
        'AGGREGATION' AS transformation_type
    UNION ALL
    SELECT
        'sqlite://core/order_items',
        'sqlite://mart/vw_daily_sales_summary',
        'BUILD_DAILY_SALES_SUMMARY_ORDER_ITEMS',
        'AGGREGATION'
    UNION ALL
    SELECT
        'sqlite://core/order_items',
        'sqlite://mart/vw_payment_reconciliation',
        'BUILD_PAYMENT_RECONCILIATION_ORDER_ITEMS',
        'RECONCILIATION'
) AS seed
JOIN data_assets AS u
    ON u.asset_key = seed.upstream_key
JOIN data_assets AS d
    ON d.asset_key = seed.downstream_key

ON CONFLICT (
    upstream_asset_id,
    downstream_asset_id,
    transformation_name,
    lineage_level
)
DO UPDATE SET
    transformation_type = excluded.transformation_type,
    process_reference = excluded.process_reference,
    is_active = excluded.is_active,
    updated_at = CURRENT_TIMESTAMP;

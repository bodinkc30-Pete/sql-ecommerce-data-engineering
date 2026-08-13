-- ============================================================
-- Performance Validation
-- SQL E-commerce Data Engineering
--
-- Purpose:
--   1. Refresh SQLite planner statistics.
--   2. Inventory explicit indexes currently present.
--   3. Detect missing project indexes against the current schema.
--   4. Confirm that customers.email is protected by a UNIQUE autoindex
--      instead of a redundant explicit idx_customers_email index.
--   5. Inspect table cardinality and representative query plans.
--
-- Notes:
--   - The permanent optimized composite indexes are:
--       idx_orders_status_date(order_status, order_date)
--       idx_payments_date_status(payment_date, payment_status)
--   - idx_orders_order_status and idx_payments_payment_date were replaced.
--   - idx_customers_email was intentionally removed because
--     customers.email UNIQUE already creates a SQLite autoindex.
-- ============================================================

ANALYZE;


-- ============================================================
-- 1. Explicit index inventory
-- ============================================================

SELECT
    name AS index_name,
    tbl_name AS table_name,
    sql AS index_definition
FROM sqlite_master
WHERE
    type = 'index'
    AND name NOT LIKE 'sqlite_autoindex_%'
ORDER BY
    tbl_name,
    name;


-- ============================================================
-- 2. Missing-index validation against the current schema
--
-- Expected result:
--   zero rows
-- ============================================================

WITH expected_indexes(index_name) AS (
    VALUES
        ('idx_campaigns_campaign_name'),
        ('idx_campaigns_source_section'),
        ('idx_customers_signup_date'),
        ('idx_data_assets_classification'),
        ('idx_data_assets_domain_layer'),
        ('idx_data_assets_type'),
        ('idx_influencer_payments_campaign_id'),
        ('idx_influencer_payments_influencer_id'),
        ('idx_influencer_payments_payment_round_date'),
        ('idx_influencer_payments_payment_status'),
        ('idx_influencer_payments_post_date'),
        ('idx_influencer_payments_source_location'),
        ('idx_influencers_bank_account_hash'),
        ('idx_influencers_contact_phone_hash'),
        ('idx_influencers_handle'),
        ('idx_lineage_edges_active'),
        ('idx_lineage_edges_downstream'),
        ('idx_lineage_edges_run_id'),
        ('idx_lineage_edges_type'),
        ('idx_lineage_edges_upstream'),
        ('idx_lineage_run_events_edge'),
        ('idx_lineage_run_events_run_id'),
        ('idx_lineage_run_events_status'),
        ('idx_lineage_run_events_step'),
        ('idx_order_items_order_id'),
        ('idx_order_items_product_id'),
        ('idx_orders_customer_id'),
        ('idx_orders_order_date'),
        ('idx_orders_status_date'),
        ('idx_payments_date_status'),
        ('idx_payments_order_id'),
        ('idx_payments_payment_status'),
        ('idx_pipeline_audit_run_id'),
        ('idx_pipeline_audit_run_status'),
        ('idx_pipeline_audit_started_at'),
        ('idx_pipeline_sla_metrics_measured_at'),
        ('idx_pipeline_sla_metrics_run_id'),
        ('idx_pipeline_sla_metrics_sla_status'),
        ('idx_pipeline_sla_metrics_step_name'),
        ('idx_pipeline_step_log_run_id'),
        ('idx_pipeline_step_log_run_step'),
        ('idx_pipeline_step_log_start_time'),
        ('idx_pipeline_step_log_status'),
        ('idx_pipeline_step_log_step_name'),
        ('idx_products_category'),
        ('idx_products_product_name'),
        ('idx_rejected_influencer_rejected_at'),
        ('idx_rejected_influencer_source_location'),
        ('ux_lineage_run_events_identity')
)
SELECT
    expected.index_name AS missing_index
FROM expected_indexes AS expected
LEFT JOIN sqlite_master AS actual
    ON actual.type = 'index'
    AND actual.name = expected.index_name
WHERE actual.name IS NULL
ORDER BY
    expected.index_name;


-- ============================================================
-- 3. Guard against indexes intentionally removed as redundant
--
-- Expected result:
--   zero rows
-- ============================================================

WITH retired_indexes(index_name) AS (
    VALUES
        ('idx_customers_email'),
        ('idx_orders_order_status'),
        ('idx_payments_payment_date')
)
SELECT
    retired.index_name AS redundant_or_retired_index_still_present
FROM retired_indexes AS retired
INNER JOIN sqlite_master AS actual
    ON actual.type = 'index'
    AND actual.name = retired.index_name
ORDER BY
    retired.index_name;


-- ============================================================
-- 4. Verify customers.email still has UNIQUE index protection
--
-- SQLite creates an autoindex for a UNIQUE column/constraint.
-- Expected result:
--   at least one UNIQUE index entry for customers.
-- ============================================================

PRAGMA index_list('customers');


-- ============================================================
-- 5. SQLite planner statistics
-- ============================================================

SELECT
    tbl AS table_name,
    idx AS index_name,
    stat AS index_statistics
FROM sqlite_stat1
ORDER BY
    tbl,
    idx;


-- ============================================================
-- 6. Representative table cardinalities
-- ============================================================

SELECT
    'customers' AS table_name,
    COUNT(*) AS total_rows
FROM customers

UNION ALL

SELECT
    'products',
    COUNT(*)
FROM products

UNION ALL

SELECT
    'orders',
    COUNT(*)
FROM orders

UNION ALL

SELECT
    'order_items',
    COUNT(*)
FROM order_items

UNION ALL

SELECT
    'payments',
    COUNT(*)
FROM payments

UNION ALL

SELECT
    'campaigns',
    COUNT(*)
FROM campaigns

UNION ALL

SELECT
    'influencers',
    COUNT(*)
FROM influencers

UNION ALL

SELECT
    'influencer_payments',
    COUNT(*)
FROM influencer_payments

UNION ALL

SELECT
    'pipeline_audit',
    COUNT(*)
FROM pipeline_audit

UNION ALL

SELECT
    'pipeline_step_log',
    COUNT(*)
FROM pipeline_step_log

UNION ALL

SELECT
    'pipeline_sla_metrics',
    COUNT(*)
FROM pipeline_sla_metrics

UNION ALL

SELECT
    'data_assets',
    COUNT(*)
FROM data_assets

UNION ALL

SELECT
    'lineage_edges',
    COUNT(*)
FROM lineage_edges

UNION ALL

SELECT
    'lineage_run_events',
    COUNT(*)
FROM lineage_run_events

ORDER BY
    total_rows DESC,
    table_name;


-- ============================================================
-- 7. Query-plan validation: optimized daily sales aggregation
--
-- Target index:
--   idx_orders_status_date(order_status, order_date)
-- ============================================================

EXPLAIN QUERY PLAN
SELECT
    order_date,
    COUNT(*) AS orders,
    SUM(order_total) AS revenue
FROM orders
WHERE order_status = 'COMPLETED'
GROUP BY
    order_date
ORDER BY
    order_date;


-- ============================================================
-- 8. Query-plan validation: optimized payment aggregation
--
-- Target index:
--   idx_payments_date_status(payment_date, payment_status)
-- ============================================================

EXPLAIN QUERY PLAN
SELECT
    payment_date,
    payment_status,
    SUM(payment_amount) AS amount
FROM payments
GROUP BY
    payment_date,
    payment_status
ORDER BY
    payment_date;


-- ============================================================
-- 9. Query-plan validation: order-status lookup
--
-- Target index:
--   idx_orders_status_date(order_status, order_date)
-- ============================================================

EXPLAIN QUERY PLAN
SELECT
    order_id,
    customer_id,
    order_date,
    order_total
FROM orders
WHERE order_status = 'COMPLETED';


-- ============================================================
-- 10. Query-plan validation: payment-date lookup
--
-- Target index:
--   idx_payments_date_status(payment_date, payment_status)
-- ============================================================

EXPLAIN QUERY PLAN
SELECT
    payment_id,
    order_id,
    payment_status,
    payment_amount
FROM payments
WHERE payment_date = DATE('now');


-- ============================================================
-- 11. Query-plan validation: customer order lookup
--
-- Supporting indexes:
--   idx_orders_customer_id
--   customers PRIMARY KEY
-- ============================================================

EXPLAIN QUERY PLAN
SELECT
    o.order_id,
    o.order_date,
    c.customer_name,
    o.order_total
FROM orders AS o
INNER JOIN customers AS c
    ON o.customer_id = c.customer_id
WHERE
    o.customer_id = 1
    AND o.order_date >= DATE('now', '-30 days');


-- ============================================================
-- 12. Query-plan validation: order item / product lookup
--
-- Supporting indexes:
--   idx_order_items_order_id
--   products PRIMARY KEY
-- ============================================================

EXPLAIN QUERY PLAN
SELECT
    oi.order_id,
    p.product_name,
    oi.quantity,
    oi.line_total
FROM order_items AS oi
INNER JOIN products AS p
    ON oi.product_id = p.product_id
WHERE oi.order_id = 1;


-- ============================================================
-- 13. Query-plan validation: pipeline failure monitoring
--
-- Supporting indexes:
--   idx_pipeline_audit_run_status
--   idx_pipeline_audit_started_at
-- ============================================================

EXPLAIN QUERY PLAN
SELECT
    run_id,
    pipeline_name,
    step_name,
    run_status,
    started_at
FROM pipeline_audit
WHERE
    run_status = 'FAILED'
    AND started_at >= DATETIME('now', '-7 days')
ORDER BY
    started_at DESC;


-- ============================================================
-- 14. Query-plan validation: governance lineage traversal
--
-- Supporting indexes:
--   idx_lineage_edges_upstream
--   idx_lineage_edges_downstream
--   idx_lineage_edges_active
-- ============================================================

EXPLAIN QUERY PLAN
SELECT
    lineage_edge_id,
    upstream_asset_id,
    downstream_asset_id,
    transformation_type
FROM lineage_edges
WHERE
    upstream_asset_id = 1
    AND is_active = 1;


EXPLAIN QUERY PLAN
SELECT
    lineage_edge_id,
    upstream_asset_id,
    downstream_asset_id,
    transformation_type
FROM lineage_edges
WHERE
    downstream_asset_id = 1
    AND is_active = 1;


-- ============================================================
-- 15. Current view inventory
-- ============================================================

SELECT
    name AS view_name,
    sql AS view_definition
FROM sqlite_master
WHERE type = 'view'
ORDER BY
    name;

ANALYZE;


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


WITH expected_indexes AS (
    SELECT 'idx_customers_email' AS index_name
    UNION ALL
    SELECT 'idx_customers_signup_date'
    UNION ALL
    SELECT 'idx_products_category'
    UNION ALL
    SELECT 'idx_products_product_name'
    UNION ALL
    SELECT 'idx_orders_customer_id'
    UNION ALL
    SELECT 'idx_orders_order_date'
    UNION ALL
    SELECT 'idx_orders_order_status'
    UNION ALL
    SELECT 'idx_order_items_order_id'
    UNION ALL
    SELECT 'idx_order_items_product_id'
    UNION ALL
    SELECT 'idx_payments_order_id'
    UNION ALL
    SELECT 'idx_payments_payment_date'
    UNION ALL
    SELECT 'idx_payments_payment_status'
    UNION ALL
    SELECT 'idx_pipeline_audit_run_id'
    UNION ALL
    SELECT 'idx_pipeline_audit_run_status'
    UNION ALL
    SELECT 'idx_pipeline_audit_started_at'
)
SELECT
    ei.index_name AS missing_index
FROM expected_indexes AS ei
LEFT JOIN sqlite_master AS sm
    ON ei.index_name = sm.name
    AND sm.type = 'index'
WHERE sm.name IS NULL
ORDER BY
    ei.index_name;


SELECT
    tbl AS table_name,
    idx AS index_name,
    stat AS index_statistics
FROM sqlite_stat1
ORDER BY
    tbl,
    idx;


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
    'pipeline_audit',
    COUNT(*)
FROM pipeline_audit

ORDER BY
    total_rows DESC;


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


EXPLAIN QUERY PLAN
SELECT
    payment_id,
    order_id,
    payment_amount,
    payment_status
FROM payments
WHERE
    order_id = 1
    AND payment_status = 'PAID';


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


SELECT
    name AS view_name,
    sql AS view_definition
FROM sqlite_master
WHERE type = 'view'
ORDER BY
    name;
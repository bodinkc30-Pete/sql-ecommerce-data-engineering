SELECT
    'stg_customers' AS table_name,
    MAX(loaded_at) AS latest_loaded_at,
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(loaded_at))
        ) * 24,
        2
    ) AS hours_since_last_load,
    COUNT(*) AS total_rows
FROM stg_customers

UNION ALL

SELECT
    'stg_products',
    MAX(loaded_at),
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(loaded_at))
        ) * 24,
        2
    ),
    COUNT(*)
FROM stg_products

UNION ALL

SELECT
    'stg_orders',
    MAX(loaded_at),
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(loaded_at))
        ) * 24,
        2
    ),
    COUNT(*)
FROM stg_orders

UNION ALL

SELECT
    'stg_order_items',
    MAX(loaded_at),
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(loaded_at))
        ) * 24,
        2
    ),
    COUNT(*)
FROM stg_order_items

UNION ALL

SELECT
    'stg_payments',
    MAX(loaded_at),
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(loaded_at))
        ) * 24,
        2
    ),
    COUNT(*)
FROM stg_payments

ORDER BY
    hours_since_last_load DESC;


SELECT
    table_name,
    last_loaded_at,
    updated_at,
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(last_loaded_at)
        ) * 24,
        2
    ) AS hours_since_watermark,
    CASE
        WHEN last_loaded_at = '1900-01-01 00:00:00'
            THEN 'NOT_LOADED'
        WHEN (
            JULIANDAY('now')
            - JULIANDAY(last_loaded_at)
        ) * 24 > 24
            THEN 'STALE'
        ELSE 'FRESH'
    END AS freshness_status
FROM pipeline_watermark
ORDER BY
    hours_since_watermark DESC;


SELECT
    table_name,
    last_loaded_at,
    updated_at
FROM pipeline_watermark
WHERE
    last_loaded_at = '1900-01-01 00:00:00'
    OR (
        JULIANDAY('now')
        - JULIANDAY(last_loaded_at)
    ) * 24 > 24
ORDER BY
    last_loaded_at;


SELECT
    'customers' AS table_name,
    MAX(updated_at) AS latest_updated_at,
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(updated_at))
        ) * 24,
        2
    ) AS hours_since_last_update,
    COUNT(*) AS total_rows
FROM customers

UNION ALL

SELECT
    'products',
    MAX(updated_at),
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(updated_at))
        ) * 24,
        2
    ),
    COUNT(*)
FROM products

UNION ALL

SELECT
    'orders',
    MAX(updated_at),
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(updated_at))
        ) * 24,
        2
    ),
    COUNT(*)
FROM orders

UNION ALL

SELECT
    'order_items',
    MAX(updated_at),
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(updated_at))
        ) * 24,
        2
    ),
    COUNT(*)
FROM order_items

UNION ALL

SELECT
    'payments',
    MAX(updated_at),
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(updated_at))
        ) * 24,
        2
    ),
    COUNT(*)
FROM payments

ORDER BY
    hours_since_last_update DESC;


SELECT
    run_id,
    pipeline_name,
    MAX(completed_at) AS latest_completed_at,
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(completed_at))
        ) * 24,
        2
    ) AS hours_since_last_success
FROM pipeline_audit
WHERE run_status = 'SUCCESS'
GROUP BY
    run_id,
    pipeline_name
ORDER BY
    latest_completed_at DESC
LIMIT 10;


SELECT
    pipeline_name,
    MAX(completed_at) AS latest_successful_run,
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(MAX(completed_at))
        ) * 24,
        2
    ) AS hours_since_last_success,
    CASE
        WHEN MAX(completed_at) IS NULL
            THEN 'NO_SUCCESSFUL_RUN'
        WHEN (
            JULIANDAY('now')
            - JULIANDAY(MAX(completed_at))
        ) * 24 > 24
            THEN 'STALE'
        ELSE 'FRESH'
    END AS pipeline_freshness_status
FROM pipeline_audit
WHERE run_status = 'SUCCESS'
GROUP BY
    pipeline_name
ORDER BY
    hours_since_last_success DESC;
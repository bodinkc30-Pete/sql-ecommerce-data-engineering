PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

WITH cleaned_orders AS (
    SELECT
        CAST(TRIM(order_id) AS INTEGER) AS order_id,
        CAST(TRIM(customer_id) AS INTEGER) AS customer_id,
        DATE(TRIM(order_date)) AS order_date,
        UPPER(TRIM(order_status)) AS order_status,
        loaded_at,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(order_id)
            ORDER BY loaded_at DESC
        ) AS order_row_number
    FROM stg_orders
    WHERE
        order_id IS NOT NULL
        AND TRIM(order_id) <> ''
        AND TRIM(order_id) NOT GLOB '*[^0-9]*'
        AND customer_id IS NOT NULL
        AND TRIM(customer_id) <> ''
        AND TRIM(customer_id) NOT GLOB '*[^0-9]*'
        AND order_date IS NOT NULL
        AND DATE(TRIM(order_date)) IS NOT NULL
        AND order_status IS NOT NULL
        AND UPPER(TRIM(order_status)) IN (
            'PENDING',
            'PROCESSING',
            'COMPLETED',
            'CANCELLED',
            'REFUNDED'
        )
)
INSERT INTO orders (
    order_id,
    customer_id,
    order_date,
    order_status,
    order_total,
    created_at,
    updated_at
)
SELECT
    co.order_id,
    co.customer_id,
    co.order_date,
    co.order_status,
    0,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM cleaned_orders AS co
WHERE
    co.order_row_number = 1
    AND EXISTS (
        SELECT 1
        FROM customers AS c
        WHERE c.customer_id = co.customer_id
    )
ON CONFLICT(order_id) DO UPDATE SET
    customer_id = excluded.customer_id,
    order_date = excluded.order_date,
    order_status = excluded.order_status,
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

WITH cleaned_order_items AS (
    SELECT
        CAST(TRIM(order_item_id) AS INTEGER) AS order_item_id,
        CAST(TRIM(order_id) AS INTEGER) AS order_id,
        CAST(TRIM(product_id) AS INTEGER) AS product_id,
        CAST(TRIM(quantity) AS INTEGER) AS quantity,
        CAST(TRIM(unit_price) AS REAL) AS unit_price,
        CAST(TRIM(quantity) AS INTEGER)
            * CAST(TRIM(unit_price) AS REAL) AS line_total,
        loaded_at,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(order_item_id)
            ORDER BY loaded_at DESC
        ) AS order_item_row_number
    FROM stg_order_items
    WHERE
        order_item_id IS NOT NULL
        AND TRIM(order_item_id) <> ''
        AND TRIM(order_item_id) NOT GLOB '*[^0-9]*'
        AND order_id IS NOT NULL
        AND TRIM(order_id) <> ''
        AND TRIM(order_id) NOT GLOB '*[^0-9]*'
        AND product_id IS NOT NULL
        AND TRIM(product_id) <> ''
        AND TRIM(product_id) NOT GLOB '*[^0-9]*'
        AND quantity IS NOT NULL
        AND TRIM(quantity) <> ''
        AND TRIM(quantity) NOT GLOB '*[^0-9]*'
        AND CAST(TRIM(quantity) AS INTEGER) > 0
        AND unit_price IS NOT NULL
        AND TRIM(unit_price) <> ''
        AND TRIM(unit_price) NOT GLOB '*[^0-9.]*'
        AND CAST(TRIM(unit_price) AS REAL) >= 0
)
INSERT INTO order_items (
    order_item_id,
    order_id,
    product_id,
    quantity,
    unit_price,
    line_total,
    created_at,
    updated_at
)
SELECT
    coi.order_item_id,
    coi.order_id,
    coi.product_id,
    coi.quantity,
    coi.unit_price,
    coi.line_total,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM cleaned_order_items AS coi
WHERE
    coi.order_item_row_number = 1
    AND EXISTS (
        SELECT 1
        FROM orders AS o
        WHERE o.order_id = coi.order_id
    )
    AND EXISTS (
        SELECT 1
        FROM products AS p
        WHERE p.product_id = coi.product_id
    )
ON CONFLICT(order_item_id) DO UPDATE SET
    order_id = excluded.order_id,
    product_id = excluded.product_id,
    quantity = excluded.quantity,
    unit_price = excluded.unit_price,
    line_total = excluded.line_total,
    updated_at = CURRENT_TIMESTAMP;

UPDATE orders
SET
    order_total = COALESCE(
        (
            SELECT SUM(oi.line_total)
            FROM order_items AS oi
            WHERE oi.order_id = orders.order_id
        ),
        0
    ),
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
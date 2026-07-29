PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

WITH cleaned_products AS (
    SELECT
        CAST(TRIM(product_id) AS INTEGER) AS product_id,
        TRIM(product_name) AS product_name,
        TRIM(category) AS category,
        CAST(TRIM(unit_price) AS REAL) AS unit_price,
        CAST(TRIM(stock_quantity) AS INTEGER) AS stock_quantity,
        loaded_at,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(product_id)
            ORDER BY loaded_at DESC
        ) AS product_row_number
    FROM stg_products
    WHERE
        product_id IS NOT NULL
        AND TRIM(product_id) <> ''
        AND TRIM(product_id) NOT GLOB '*[^0-9]*'
        AND product_name IS NOT NULL
        AND TRIM(product_name) <> ''
        AND category IS NOT NULL
        AND TRIM(category) <> ''
        AND unit_price IS NOT NULL
        AND TRIM(unit_price) <> ''
        AND TRIM(unit_price) NOT GLOB '*[^0-9.]*'
        AND CAST(TRIM(unit_price) AS REAL) >= 0
        AND stock_quantity IS NOT NULL
        AND TRIM(stock_quantity) <> ''
        AND TRIM(stock_quantity) NOT GLOB '*[^0-9]*'
        AND CAST(TRIM(stock_quantity) AS INTEGER) >= 0
)
INSERT INTO products (
    product_id,
    product_name,
    category,
    unit_price,
    stock_quantity,
    created_at,
    updated_at
)
SELECT
    product_id,
    product_name,
    category,
    unit_price,
    stock_quantity,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM cleaned_products
WHERE product_row_number = 1
ON CONFLICT(product_id) DO UPDATE SET
    product_name = excluded.product_name,
    category = excluded.category,
    unit_price = excluded.unit_price,
    stock_quantity = excluded.stock_quantity,
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
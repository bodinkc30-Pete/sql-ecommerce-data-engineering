-- NORMAL incremental-load controller.
-- IMPORTANT:
-- `scripts/03_run_transformations.py` intentionally skips this file
-- when PIPELINE_RUN_TYPE=BACKFILL. Backfill staging has already been
-- filtered by business date, and historical reruns must NOT advance
-- the normal `pipeline_watermark`.
--
-- Keep this SQL dedicated to NORMAL incremental processing.
-- The runner injects __INCREMENTAL_LOOKBACK_MINUTES__ and
-- __WATERMARK_FUTURE_TOLERANCE_MINUTES__ from pipeline_config.json.

PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

INSERT OR IGNORE INTO pipeline_watermark (
    table_name,
    last_loaded_at
)
VALUES
    ('stg_customers', '1900-01-01 00:00:00'),
    ('stg_products', '1900-01-01 00:00:00'),
    ('stg_orders', '1900-01-01 00:00:00'),
    ('stg_order_items', '1900-01-01 00:00:00'),
    ('stg_payments', '1900-01-01 00:00:00');

WITH incremental_customers AS (
    SELECT
        CAST(TRIM(customer_id) AS INTEGER) AS customer_id,
        TRIM(customer_name) AS customer_name,
        LOWER(TRIM(email)) AS email,
        NULLIF(TRIM(city), '') AS city,
        DATE(TRIM(signup_date)) AS signup_date,
        loaded_at,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(customer_id)
            ORDER BY loaded_at DESC
        ) AS row_number
    FROM stg_customers
    WHERE
        datetime(loaded_at) >= datetime(
            (
                SELECT last_loaded_at
                FROM pipeline_watermark
                WHERE table_name = 'stg_customers'
            ),
            '-' || __INCREMENTAL_LOOKBACK_MINUTES__ || ' minutes'
        )
        AND customer_id IS NOT NULL
        AND TRIM(customer_id) <> ''
        AND TRIM(customer_id) NOT GLOB '*[^0-9]*'
        AND customer_name IS NOT NULL
        AND TRIM(customer_name) <> ''
        AND email IS NOT NULL
        AND LOWER(TRIM(email)) LIKE '%_@_%._%'
        AND signup_date IS NOT NULL
        AND DATE(TRIM(signup_date)) IS NOT NULL
)
,
deduplicated_customers AS (
    SELECT
        customer_id,
        customer_name,
        email,
        city,
        signup_date,
        loaded_at,
        ROW_NUMBER() OVER (
            PARTITION BY email
            ORDER BY loaded_at DESC
        ) AS email_row_number
    FROM incremental_customers
    WHERE row_number = 1
)
INSERT INTO customers (
    customer_id,
    customer_name,
    email,
    city,
    signup_date,
    created_at,
    updated_at
)
SELECT
    customer_id,
    customer_name,
    email,
    city,
    signup_date,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM deduplicated_customers
WHERE email_row_number = 1
ON CONFLICT(customer_id) DO UPDATE SET
    customer_name = excluded.customer_name,
    email = excluded.email,
    city = excluded.city,
    signup_date = excluded.signup_date,
    updated_at = CURRENT_TIMESTAMP;

WITH incremental_products AS (
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
        ) AS row_number
    FROM stg_products
    WHERE
        datetime(loaded_at) >= datetime(
            (
                SELECT last_loaded_at
                FROM pipeline_watermark
                WHERE table_name = 'stg_products'
            ),
            '-' || __INCREMENTAL_LOOKBACK_MINUTES__ || ' minutes'
        )
        AND product_id IS NOT NULL
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
FROM incremental_products
WHERE row_number = 1
ON CONFLICT(product_id) DO UPDATE SET
    product_name = excluded.product_name,
    category = excluded.category,
    unit_price = excluded.unit_price,
    stock_quantity = excluded.stock_quantity,
    updated_at = CURRENT_TIMESTAMP;

WITH incremental_orders AS (
    SELECT
        CAST(TRIM(order_id) AS INTEGER) AS order_id,
        CAST(TRIM(customer_id) AS INTEGER) AS customer_id,
        DATE(TRIM(order_date)) AS order_date,
        UPPER(TRIM(order_status)) AS order_status,
        loaded_at,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(order_id)
            ORDER BY loaded_at DESC
        ) AS row_number
    FROM stg_orders
    WHERE
        datetime(loaded_at) >= datetime(
            (
                SELECT last_loaded_at
                FROM pipeline_watermark
                WHERE table_name = 'stg_orders'
            ),
            '-' || __INCREMENTAL_LOOKBACK_MINUTES__ || ' minutes'
        )
        AND order_id IS NOT NULL
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
    io.order_id,
    io.customer_id,
    io.order_date,
    io.order_status,
    0,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM incremental_orders AS io
WHERE
    io.row_number = 1
    AND EXISTS (
        SELECT 1
        FROM customers AS c
        WHERE c.customer_id = io.customer_id
    )
ON CONFLICT(order_id) DO UPDATE SET
    customer_id = excluded.customer_id,
    order_date = excluded.order_date,
    order_status = excluded.order_status,
    updated_at = CURRENT_TIMESTAMP;

WITH incremental_order_items AS (
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
        ) AS row_number
    FROM stg_order_items
    WHERE
        datetime(loaded_at) >= datetime(
            (
                SELECT last_loaded_at
                FROM pipeline_watermark
                WHERE table_name = 'stg_order_items'
            ),
            '-' || __INCREMENTAL_LOOKBACK_MINUTES__ || ' minutes'
        )
        AND order_item_id IS NOT NULL
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
    ioi.order_item_id,
    ioi.order_id,
    ioi.product_id,
    ioi.quantity,
    ioi.unit_price,
    ioi.line_total,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM incremental_order_items AS ioi
WHERE
    ioi.row_number = 1
    AND EXISTS (
        SELECT 1
        FROM orders AS o
        WHERE o.order_id = ioi.order_id
    )
    AND EXISTS (
        SELECT 1
        FROM products AS p
        WHERE p.product_id = ioi.product_id
    )
ON CONFLICT(order_item_id) DO UPDATE SET
    order_id = excluded.order_id,
    product_id = excluded.product_id,
    quantity = excluded.quantity,
    unit_price = excluded.unit_price,
    line_total = excluded.line_total,
    updated_at = CURRENT_TIMESTAMP;

WITH incremental_payments AS (
    SELECT
        CAST(TRIM(payment_id) AS INTEGER) AS payment_id,
        CAST(TRIM(order_id) AS INTEGER) AS order_id,
        DATE(TRIM(payment_date)) AS payment_date,
        UPPER(TRIM(payment_method)) AS payment_method,
        CAST(TRIM(payment_amount) AS REAL) AS payment_amount,
        UPPER(TRIM(payment_status)) AS payment_status,
        loaded_at,
        ROW_NUMBER() OVER (
            PARTITION BY TRIM(payment_id)
            ORDER BY loaded_at DESC
        ) AS row_number
    FROM stg_payments
    WHERE
        datetime(loaded_at) >= datetime(
            (
                SELECT last_loaded_at
                FROM pipeline_watermark
                WHERE table_name = 'stg_payments'
            ),
            '-' || __INCREMENTAL_LOOKBACK_MINUTES__ || ' minutes'
        )
        AND payment_id IS NOT NULL
        AND TRIM(payment_id) <> ''
        AND TRIM(payment_id) NOT GLOB '*[^0-9]*'
        AND order_id IS NOT NULL
        AND TRIM(order_id) <> ''
        AND TRIM(order_id) NOT GLOB '*[^0-9]*'
        AND payment_date IS NOT NULL
        AND DATE(TRIM(payment_date)) IS NOT NULL
        AND payment_method IS NOT NULL
        AND UPPER(TRIM(payment_method)) IN (
            'CREDIT_CARD',
            'DEBIT_CARD',
            'BANK_TRANSFER',
            'E_WALLET',
            'CASH'
        )
        AND payment_amount IS NOT NULL
        AND TRIM(payment_amount) <> ''
        AND TRIM(payment_amount) NOT GLOB '*[^0-9.]*'
        AND CAST(TRIM(payment_amount) AS REAL) >= 0
        AND payment_status IS NOT NULL
        AND UPPER(TRIM(payment_status)) IN (
            'PENDING',
            'PAID',
            'FAILED',
            'REFUNDED',
            'CANCELLED'
        )
)
INSERT INTO payments (
    payment_id,
    order_id,
    payment_date,
    payment_method,
    payment_amount,
    payment_status,
    created_at,
    updated_at
)
SELECT
    ip.payment_id,
    ip.order_id,
    ip.payment_date,
    ip.payment_method,
    ip.payment_amount,
    ip.payment_status,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM incremental_payments AS ip
WHERE
    ip.row_number = 1
    AND EXISTS (
        SELECT 1
        FROM orders AS o
        WHERE o.order_id = ip.order_id
    )
ON CONFLICT(payment_id) DO UPDATE SET
    order_id = excluded.order_id,
    payment_date = excluded.payment_date,
    payment_method = excluded.payment_method,
    payment_amount = excluded.payment_amount,
    payment_status = excluded.payment_status,
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
    updated_at = CURRENT_TIMESTAMP
WHERE order_id IN (
    SELECT DISTINCT
        CAST(TRIM(order_id) AS INTEGER)
    FROM stg_order_items
    WHERE datetime(loaded_at) >= datetime(
            (
                SELECT last_loaded_at
                FROM pipeline_watermark
                WHERE table_name = 'stg_order_items'
            ),
            '-' || __INCREMENTAL_LOOKBACK_MINUTES__ || ' minutes'
        )
);

UPDATE pipeline_watermark
SET
    last_loaded_at = COALESCE(
        (
            SELECT MAX(loaded_at)
            FROM stg_customers
            WHERE datetime(loaded_at) <= datetime(
                'now',
                '+' || __WATERMARK_FUTURE_TOLERANCE_MINUTES__ || ' minutes'
            )
        ),
        last_loaded_at
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE table_name = 'stg_customers';

UPDATE pipeline_watermark
SET
    last_loaded_at = COALESCE(
        (
            SELECT MAX(loaded_at)
            FROM stg_products
            WHERE datetime(loaded_at) <= datetime(
                'now',
                '+' || __WATERMARK_FUTURE_TOLERANCE_MINUTES__ || ' minutes'
            )
        ),
        last_loaded_at
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE table_name = 'stg_products';

UPDATE pipeline_watermark
SET
    last_loaded_at = COALESCE(
        (
            SELECT MAX(loaded_at)
            FROM stg_orders
            WHERE datetime(loaded_at) <= datetime(
                'now',
                '+' || __WATERMARK_FUTURE_TOLERANCE_MINUTES__ || ' minutes'
            )
        ),
        last_loaded_at
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE table_name = 'stg_orders';

UPDATE pipeline_watermark
SET
    last_loaded_at = COALESCE(
        (
            SELECT MAX(loaded_at)
            FROM stg_order_items
            WHERE datetime(loaded_at) <= datetime(
                'now',
                '+' || __WATERMARK_FUTURE_TOLERANCE_MINUTES__ || ' minutes'
            )
        ),
        last_loaded_at
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE table_name = 'stg_order_items';

UPDATE pipeline_watermark
SET
    last_loaded_at = COALESCE(
        (
            SELECT MAX(loaded_at)
            FROM stg_payments
            WHERE datetime(loaded_at) <= datetime(
                'now',
                '+' || __WATERMARK_FUTURE_TOLERANCE_MINUTES__ || ' minutes'
            )
        ),
        last_loaded_at
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE table_name = 'stg_payments';

COMMIT;
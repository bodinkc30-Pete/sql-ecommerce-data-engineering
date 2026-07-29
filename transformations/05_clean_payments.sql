PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

WITH cleaned_payments AS (
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
        ) AS payment_row_number
    FROM stg_payments
    WHERE
        payment_id IS NOT NULL
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
    cp.payment_id,
    cp.order_id,
    cp.payment_date,
    cp.payment_method,
    cp.payment_amount,
    cp.payment_status,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM cleaned_payments AS cp
WHERE
    cp.payment_row_number = 1
    AND EXISTS (
        SELECT 1
        FROM orders AS o
        WHERE o.order_id = cp.order_id
    )
ON CONFLICT(payment_id) DO UPDATE SET
    order_id = excluded.order_id,
    payment_date = excluded.payment_date,
    payment_method = excluded.payment_method,
    payment_amount = excluded.payment_amount,
    payment_status = excluded.payment_status,
    updated_at = CURRENT_TIMESTAMP;

COMMIT;
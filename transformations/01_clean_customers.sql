PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

WITH cleaned_customers AS (
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
        ) AS customer_row_number
    FROM stg_customers
    WHERE
        customer_id IS NOT NULL
        AND TRIM(customer_id) <> ''
        AND TRIM(customer_id) NOT GLOB '*[^0-9]*'
        AND customer_name IS NOT NULL
        AND TRIM(customer_name) <> ''
        AND email IS NOT NULL
        AND LOWER(TRIM(email)) LIKE '%_@_%._%'
        AND signup_date IS NOT NULL
        AND DATE(TRIM(signup_date)) IS NOT NULL
),
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
    FROM cleaned_customers
    WHERE customer_row_number = 1
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

COMMIT;
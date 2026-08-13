SELECT
    'stg_customers' AS table_name,
    'customer_id' AS duplicate_key,
    TRIM(customer_id) AS duplicate_value,
    COUNT(*) AS duplicate_count
FROM stg_customers
WHERE
    customer_id IS NOT NULL
    AND TRIM(customer_id) <> ''
GROUP BY TRIM(customer_id)
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'stg_customers',
    'email',
    LOWER(TRIM(email)),
    COUNT(*)
FROM stg_customers
WHERE
    email IS NOT NULL
    AND TRIM(email) <> ''
GROUP BY LOWER(TRIM(email))
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'customers' AS table_name,
    'customer_id' AS duplicate_key,
    customer_id AS duplicate_value,
    COUNT(*) AS duplicate_count
FROM customers
GROUP BY customer_id
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'customers',
    'email',
    email,
    COUNT(*)
FROM customers
GROUP BY email
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'products',
    'product_id',
    product_id,
    COUNT(*)
FROM products
GROUP BY product_id
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'orders',
    'order_id',
    order_id,
    COUNT(*)
FROM orders
GROUP BY order_id
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'order_items',
    'order_item_id',
    order_item_id,
    COUNT(*)
FROM order_items
GROUP BY order_item_id
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'payments',
    'payment_id',
    payment_id,
    COUNT(*)
FROM payments
GROUP BY payment_id
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'campaigns',
    'campaign_name + source_section',
    campaign_name || ' | ' || source_section,
    COUNT(*)
FROM campaigns
GROUP BY
    campaign_name,
    source_section
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'influencers',
    'influencer_handle',
    influencer_handle,
    COUNT(*)
FROM influencers
GROUP BY
    influencer_handle
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'influencer_payments',
    'record_hash',
    record_hash,
    COUNT(*)
FROM influencer_payments
GROUP BY
    record_hash
HAVING COUNT(*) > 1

UNION ALL

SELECT
    'influencer_payments',
    'source_location',
    source_file
        || ' | '
        || source_sheet
        || ' | row '
        || CAST(source_row_number AS TEXT),
    COUNT(*)
FROM influencer_payments
GROUP BY
    source_file,
    source_sheet,
    source_row_number
HAVING COUNT(*) > 1


ORDER BY
    table_name,
    duplicate_key,
    duplicate_value;
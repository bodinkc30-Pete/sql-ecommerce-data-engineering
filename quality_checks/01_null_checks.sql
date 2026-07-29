WITH null_check_results AS (
    SELECT
        'customers' AS table_name,
        'customer_id' AS column_name,
        COUNT(*) AS null_count
    FROM customers
    WHERE customer_id IS NULL

    UNION ALL

    SELECT
        'customers',
        'customer_name',
        COUNT(*)
    FROM customers
    WHERE customer_name IS NULL
       OR TRIM(customer_name) = ''

    UNION ALL

    SELECT
        'customers',
        'email',
        COUNT(*)
    FROM customers
    WHERE email IS NULL
       OR TRIM(email) = ''

    UNION ALL

    SELECT
        'customers',
        'signup_date',
        COUNT(*)
    FROM customers
    WHERE signup_date IS NULL

    UNION ALL

    SELECT
        'products',
        'product_id',
        COUNT(*)
    FROM products
    WHERE product_id IS NULL

    UNION ALL

    SELECT
        'products',
        'product_name',
        COUNT(*)
    FROM products
    WHERE product_name IS NULL
       OR TRIM(product_name) = ''

    UNION ALL

    SELECT
        'products',
        'category',
        COUNT(*)
    FROM products
    WHERE category IS NULL
       OR TRIM(category) = ''

    UNION ALL

    SELECT
        'products',
        'unit_price',
        COUNT(*)
    FROM products
    WHERE unit_price IS NULL

    UNION ALL

    SELECT
        'products',
        'stock_quantity',
        COUNT(*)
    FROM products
    WHERE stock_quantity IS NULL

    UNION ALL

    SELECT
        'orders',
        'order_id',
        COUNT(*)
    FROM orders
    WHERE order_id IS NULL

    UNION ALL

    SELECT
        'orders',
        'customer_id',
        COUNT(*)
    FROM orders
    WHERE customer_id IS NULL

    UNION ALL

    SELECT
        'orders',
        'order_date',
        COUNT(*)
    FROM orders
    WHERE order_date IS NULL

    UNION ALL

    SELECT
        'orders',
        'order_status',
        COUNT(*)
    FROM orders
    WHERE order_status IS NULL
       OR TRIM(order_status) = ''

    UNION ALL

    SELECT
        'orders',
        'order_total',
        COUNT(*)
    FROM orders
    WHERE order_total IS NULL

    UNION ALL

    SELECT
        'order_items',
        'order_item_id',
        COUNT(*)
    FROM order_items
    WHERE order_item_id IS NULL

    UNION ALL

    SELECT
        'order_items',
        'order_id',
        COUNT(*)
    FROM order_items
    WHERE order_id IS NULL

    UNION ALL

    SELECT
        'order_items',
        'product_id',
        COUNT(*)
    FROM order_items
    WHERE product_id IS NULL

    UNION ALL

    SELECT
        'order_items',
        'quantity',
        COUNT(*)
    FROM order_items
    WHERE quantity IS NULL

    UNION ALL

    SELECT
        'order_items',
        'unit_price',
        COUNT(*)
    FROM order_items
    WHERE unit_price IS NULL

    UNION ALL

    SELECT
        'order_items',
        'line_total',
        COUNT(*)
    FROM order_items
    WHERE line_total IS NULL

    UNION ALL

    SELECT
        'payments',
        'payment_id',
        COUNT(*)
    FROM payments
    WHERE payment_id IS NULL

    UNION ALL

    SELECT
        'payments',
        'order_id',
        COUNT(*)
    FROM payments
    WHERE order_id IS NULL

    UNION ALL

    SELECT
        'payments',
        'payment_date',
        COUNT(*)
    FROM payments
    WHERE payment_date IS NULL

    UNION ALL

    SELECT
        'payments',
        'payment_method',
        COUNT(*)
    FROM payments
    WHERE payment_method IS NULL
       OR TRIM(payment_method) = ''

    UNION ALL

    SELECT
        'payments',
        'payment_amount',
        COUNT(*)
    FROM payments
    WHERE payment_amount IS NULL

    UNION ALL

    SELECT
        'payments',
        'payment_status',
        COUNT(*)
    FROM payments
    WHERE payment_status IS NULL
       OR TRIM(payment_status) = ''

           UNION ALL

    SELECT
        'campaigns',
        'campaign_id',
        COUNT(*)
    FROM campaigns
    WHERE campaign_id IS NULL

    UNION ALL

    SELECT
        'campaigns',
        'campaign_name',
        COUNT(*)
    FROM campaigns
    WHERE campaign_name IS NULL
       OR TRIM(campaign_name) = ''

    UNION ALL

    SELECT
        'campaigns',
        'source_section',
        COUNT(*)
    FROM campaigns
    WHERE source_section IS NULL
       OR TRIM(source_section) = ''

    UNION ALL

    SELECT
        'influencers',
        'influencer_id',
        COUNT(*)
    FROM influencers
    WHERE influencer_id IS NULL

    UNION ALL

    SELECT
        'influencers',
        'influencer_handle',
        COUNT(*)
    FROM influencers
    WHERE influencer_handle IS NULL
       OR TRIM(influencer_handle) = ''

    UNION ALL

    SELECT
        'influencer_payments',
        'influencer_payment_id',
        COUNT(*)
    FROM influencer_payments
    WHERE influencer_payment_id IS NULL

    UNION ALL

    SELECT
        'influencer_payments',
        'campaign_id',
        COUNT(*)
    FROM influencer_payments
    WHERE campaign_id IS NULL

    UNION ALL

    SELECT
        'influencer_payments',
        'influencer_id',
        COUNT(*)
    FROM influencer_payments
    WHERE influencer_id IS NULL

    UNION ALL

    SELECT
        'influencer_payments',
        'fee_amount',
        COUNT(*)
    FROM influencer_payments
    WHERE fee_amount IS NULL

    UNION ALL

    SELECT
        'influencer_payments',
        'payment_status',
        COUNT(*)
    FROM influencer_payments
    WHERE payment_status IS NULL
       OR TRIM(payment_status) = ''

    UNION ALL

    SELECT
        'influencer_payments',
        'source_file',
        COUNT(*)
    FROM influencer_payments
    WHERE source_file IS NULL
       OR TRIM(source_file) = ''

    UNION ALL

    SELECT
        'influencer_payments',
        'source_sheet',
        COUNT(*)
    FROM influencer_payments
    WHERE source_sheet IS NULL
       OR TRIM(source_sheet) = ''

    UNION ALL

    SELECT
        'influencer_payments',
        'source_row_number',
        COUNT(*)
    FROM influencer_payments
    WHERE source_row_number IS NULL

    UNION ALL

    SELECT
        'influencer_payments',
        'record_hash',
        COUNT(*)
    FROM influencer_payments
    WHERE record_hash IS NULL
       OR TRIM(record_hash) = ''

    UNION ALL

    SELECT
        'rejected_influencer_records',
        'rejection_reason',
        COUNT(*)
    FROM rejected_influencer_records
    WHERE rejection_reason IS NULL
       OR TRIM(rejection_reason) = ''

    UNION ALL

    SELECT
        'rejected_influencer_records',
        'source_file',
        COUNT(*)
    FROM rejected_influencer_records
    WHERE source_file IS NULL
       OR TRIM(source_file) = ''

    UNION ALL

    SELECT
        'rejected_influencer_records',
        'source_sheet',
        COUNT(*)
    FROM rejected_influencer_records
    WHERE source_sheet IS NULL
       OR TRIM(source_sheet) = ''

    UNION ALL

    SELECT
        'rejected_influencer_records',
        'source_row_number',
        COUNT(*)
    FROM rejected_influencer_records
    WHERE source_row_number IS NULL
)
SELECT
    table_name,
    column_name,
    null_count
FROM null_check_results
WHERE null_count > 0
ORDER BY
    table_name,
    column_name;
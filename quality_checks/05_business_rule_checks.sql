SELECT
    'invalid_customer_signup_date' AS check_name,
    'customers' AS table_name,
    CAST(customer_id AS TEXT) AS record_id,
    signup_date AS invalid_value,
    'signup_date is in the future' AS issue_description
FROM customers
WHERE DATE(signup_date) > DATE('now')

UNION ALL

SELECT
    'invalid_product_price',
    'products',
    CAST(product_id AS TEXT),
    CAST(unit_price AS TEXT),
    'unit_price must be zero or greater'
FROM products
WHERE unit_price < 0

UNION ALL

SELECT
    'invalid_stock_quantity',
    'products',
    CAST(product_id AS TEXT),
    CAST(stock_quantity AS TEXT),
    'stock_quantity must be zero or greater'
FROM products
WHERE stock_quantity < 0

UNION ALL

SELECT
    'invalid_order_date',
    'orders',
    CAST(order_id AS TEXT),
    order_date,
    'order_date is in the future'
FROM orders
WHERE DATE(order_date) > DATE('now')

UNION ALL

SELECT
    'invalid_order_status',
    'orders',
    CAST(order_id AS TEXT),
    order_status,
    'order_status is not an allowed value'
FROM orders
WHERE order_status NOT IN (__ALLOWED_ORDER_STATUSES__)

UNION ALL

SELECT
    'completed_order_without_value',
    'orders',
    CAST(order_id AS TEXT),
    CAST(order_total AS TEXT),
    'completed order must have order_total greater than zero'
FROM orders
WHERE
    order_status = 'COMPLETED'
    AND order_total <= 0

UNION ALL

SELECT
    'cancelled_order_with_paid_payment',
    'orders',
    CAST(o.order_id AS TEXT),
    CAST(COALESCE(SUM(p.payment_amount), 0) AS TEXT),
    'cancelled order must not have active paid payments'
FROM orders AS o
INNER JOIN payments AS p
    ON o.order_id = p.order_id
WHERE
    o.order_status = 'CANCELLED'
    AND p.payment_status = 'PAID'
GROUP BY
    o.order_id
HAVING SUM(p.payment_amount) > 0

UNION ALL

SELECT
    'invalid_order_item_quantity',
    'order_items',
    CAST(order_item_id AS TEXT),
    CAST(quantity AS TEXT),
    'quantity must be greater than zero'
FROM order_items
WHERE quantity <= 0

UNION ALL

SELECT
    'invalid_order_item_price',
    'order_items',
    CAST(order_item_id AS TEXT),
    CAST(unit_price AS TEXT),
    'unit_price must be zero or greater'
FROM order_items
WHERE unit_price < 0

UNION ALL

SELECT
    'invalid_line_total',
    'order_items',
    CAST(order_item_id AS TEXT),
    CAST(line_total AS TEXT),
    'line_total must be zero or greater'
FROM order_items
WHERE line_total < 0

UNION ALL

SELECT
    'invalid_payment_date',
    'payments',
    CAST(payment_id AS TEXT),
    payment_date,
    'payment_date is in the future'
FROM payments
WHERE DATE(payment_date) > DATE('now')

UNION ALL

SELECT
    'payment_before_order_date',
    'payments',
    CAST(p.payment_id AS TEXT),
    p.payment_date,
    'payment_date cannot be earlier than order_date'
FROM payments AS p
INNER JOIN orders AS o
    ON p.order_id = o.order_id
WHERE DATE(p.payment_date) < DATE(o.order_date)

UNION ALL

SELECT
    'invalid_payment_method',
    'payments',
    CAST(payment_id AS TEXT),
    payment_method,
    'payment_method is not an allowed value'
FROM payments
WHERE payment_method NOT IN (__ALLOWED_PAYMENT_METHODS__)

UNION ALL

SELECT
    'invalid_payment_status',
    'payments',
    CAST(payment_id AS TEXT),
    payment_status,
    'payment_status is not an allowed value'
FROM payments
WHERE payment_status NOT IN (__ALLOWED_PAYMENT_STATUSES__)

UNION ALL

SELECT
    'invalid_payment_amount',
    'payments',
    CAST(payment_id AS TEXT),
    CAST(payment_amount AS TEXT),
    'payment_amount must be zero or greater'
FROM payments
WHERE payment_amount < 0

UNION ALL

SELECT
    'paid_payment_without_value',
    'payments',
    CAST(payment_id AS TEXT),
    CAST(payment_amount AS TEXT),
    'paid payment must have payment_amount greater than zero'
FROM payments
WHERE
    payment_status = 'PAID'
    AND payment_amount <= 0

UNION ALL

SELECT
    'completed_order_without_paid_payment',
    'orders',
    CAST(o.order_id AS TEXT),
    CAST(
        COALESCE(
            SUM(
                CASE
                    WHEN p.payment_status = 'PAID'
                        THEN p.payment_amount
                    ELSE 0
                END
            ),
            0
        ) AS TEXT
    ),
    'completed order must have at least one paid payment'
FROM orders AS o
LEFT JOIN payments AS p
    ON o.order_id = p.order_id
WHERE o.order_status = 'COMPLETED'
GROUP BY
    o.order_id
HAVING COALESCE(
    SUM(
        CASE
            WHEN p.payment_status = 'PAID'
                THEN p.payment_amount
            ELSE 0
        END
    ),
    0
) <= 0

ORDER BY
    check_name,
    table_name,
    record_id;
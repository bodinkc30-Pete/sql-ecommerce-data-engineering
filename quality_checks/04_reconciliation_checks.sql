SELECT
    'order_total_vs_order_items' AS check_name,
    CAST(o.order_id AS TEXT) AS record_id,
    ROUND(o.order_total, 2) AS stored_amount,
    ROUND(COALESCE(SUM(oi.line_total), 0), 2) AS calculated_amount,
    ROUND(
        o.order_total - COALESCE(SUM(oi.line_total), 0),
        2
    ) AS difference
FROM orders AS o
LEFT JOIN order_items AS oi
    ON o.order_id = oi.order_id
GROUP BY
    o.order_id,
    o.order_total
HAVING ABS(
    o.order_total - COALESCE(SUM(oi.line_total), 0)
) > 0.01

UNION ALL

SELECT
    'line_total_vs_quantity_price',
    CAST(oi.order_item_id AS TEXT),
    ROUND(oi.line_total, 2),
    ROUND(oi.quantity * oi.unit_price, 2),
    ROUND(
        oi.line_total - (oi.quantity * oi.unit_price),
        2
    )
FROM order_items AS oi
WHERE ABS(
    oi.line_total - (oi.quantity * oi.unit_price)
) > 0.01

UNION ALL

SELECT
    'paid_amount_vs_order_total',
    CAST(o.order_id AS TEXT),
    ROUND(o.order_total, 2),
    ROUND(
        COALESCE(
            SUM(
                CASE
                    WHEN p.payment_status = 'PAID'
                        THEN p.payment_amount
                    ELSE 0
                END
            ),
            0
        ),
        2
    ),
    ROUND(
        o.order_total
        - COALESCE(
            SUM(
                CASE
                    WHEN p.payment_status = 'PAID'
                        THEN p.payment_amount
                    ELSE 0
                END
            ),
            0
        ),
        2
    )
FROM orders AS o
LEFT JOIN payments AS p
    ON o.order_id = p.order_id
WHERE o.order_status = 'COMPLETED'
GROUP BY
    o.order_id,
    o.order_total
HAVING ABS(
    o.order_total
    - COALESCE(
        SUM(
            CASE
                WHEN p.payment_status = 'PAID'
                    THEN p.payment_amount
                ELSE 0
            END
        ),
        0
    )
) > 0.01

UNION ALL

SELECT
    'payment_total_exceeds_order_total',
    CAST(o.order_id AS TEXT),
    ROUND(o.order_total, 2),
    ROUND(
        COALESCE(SUM(p.payment_amount), 0),
        2
    ),
    ROUND(
        o.order_total - COALESCE(SUM(p.payment_amount), 0),
        2
    )
FROM orders AS o
INNER JOIN payments AS p
    ON o.order_id = p.order_id
WHERE p.payment_status = 'PAID'
GROUP BY
    o.order_id,
    o.order_total
HAVING COALESCE(SUM(p.payment_amount), 0)
    > o.order_total + 0.01

ORDER BY
    check_name,
    record_id;
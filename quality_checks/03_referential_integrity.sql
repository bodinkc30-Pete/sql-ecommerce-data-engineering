SELECT
    'orders' AS child_table,
    'customer_id' AS foreign_key_column,
    CAST(o.customer_id AS TEXT) AS missing_reference_value,
    COUNT(*) AS affected_rows
FROM orders AS o
LEFT JOIN customers AS c
    ON o.customer_id = c.customer_id
WHERE c.customer_id IS NULL
GROUP BY
    o.customer_id

UNION ALL

SELECT
    'order_items',
    'order_id',
    CAST(oi.order_id AS TEXT),
    COUNT(*)
FROM order_items AS oi
LEFT JOIN orders AS o
    ON oi.order_id = o.order_id
WHERE o.order_id IS NULL
GROUP BY
    oi.order_id

UNION ALL

SELECT
    'order_items',
    'product_id',
    CAST(oi.product_id AS TEXT),
    COUNT(*)
FROM order_items AS oi
LEFT JOIN products AS p
    ON oi.product_id = p.product_id
WHERE p.product_id IS NULL
GROUP BY
    oi.product_id

UNION ALL

SELECT
    'payments',
    'order_id',
    CAST(pay.order_id AS TEXT),
    COUNT(*)
FROM payments AS pay
LEFT JOIN orders AS o
    ON pay.order_id = o.order_id
WHERE o.order_id IS NULL
GROUP BY
    pay.order_id

UNION ALL

SELECT
    'influencer_payments',
    'campaign_id',
    CAST(ip.campaign_id AS TEXT),
    COUNT(*)
FROM influencer_payments AS ip
LEFT JOIN campaigns AS c
    ON ip.campaign_id = c.campaign_id
WHERE c.campaign_id IS NULL
GROUP BY
    ip.campaign_id

UNION ALL

SELECT
    'influencer_payments',
    'influencer_id',
    CAST(ip.influencer_id AS TEXT),
    COUNT(*)
FROM influencer_payments AS ip
LEFT JOIN influencers AS i
    ON ip.influencer_id = i.influencer_id
WHERE i.influencer_id IS NULL
GROUP BY
    ip.influencer_id
    
ORDER BY
    child_table,
    foreign_key_column,
    missing_reference_value;


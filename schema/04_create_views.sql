DROP VIEW IF EXISTS vw_order_details;
DROP VIEW IF EXISTS vw_customer_order_summary;
DROP VIEW IF EXISTS vw_product_sales_summary;
DROP VIEW IF EXISTS vw_daily_sales_summary;
DROP VIEW IF EXISTS vw_payment_summary;
DROP VIEW IF EXISTS vw_payment_reconciliation;
DROP VIEW IF EXISTS vw_data_quality_summary;
DROP VIEW IF EXISTS vw_pipeline_run_summary;
DROP VIEW IF EXISTS vw_pipeline_step_monitoring;
DROP VIEW IF EXISTS vw_pipeline_sla_monitoring;
DROP VIEW IF EXISTS vw_pipeline_alert_monitoring;

DROP VIEW IF EXISTS vw_influencer_payment_details;
DROP VIEW IF EXISTS vw_campaign_payment_summary;
DROP VIEW IF EXISTS vw_influencer_payment_summary;
DROP VIEW IF EXISTS vw_payment_status_summary;
DROP VIEW IF EXISTS vw_rejected_influencer_summary;


CREATE VIEW vw_order_details AS
SELECT
    o.order_id,
    o.order_date,
    o.order_status,
    o.order_total,
    c.customer_id,
    c.customer_name,
    c.email,
    c.city,
    oi.order_item_id,
    p.product_id,
    p.product_name,
    p.category,
    oi.quantity,
    oi.unit_price,
    oi.line_total,
    pay.payment_id,
    pay.payment_date,
    pay.payment_method,
    pay.payment_amount,
    pay.payment_status
FROM orders AS o
INNER JOIN customers AS c
    ON o.customer_id = c.customer_id
INNER JOIN order_items AS oi
    ON o.order_id = oi.order_id
INNER JOIN products AS p
    ON oi.product_id = p.product_id
LEFT JOIN payments AS pay
    ON o.order_id = pay.order_id;


CREATE VIEW vw_customer_order_summary AS
WITH order_level AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_date,
        o.order_total,
        COALESCE(
            SUM(oi.line_total),
            0
        ) AS order_spent
    FROM orders AS o
    LEFT JOIN order_items AS oi
        ON o.order_id = oi.order_id
    GROUP BY
        o.order_id,
        o.customer_id,
        o.order_date,
        o.order_total
)
SELECT
    c.customer_id,
    c.customer_name,
    c.email,
    c.city,
    COUNT(ol.order_id) AS total_orders,
    COALESCE(
        SUM(ol.order_spent),
        0
    ) AS total_spent,
    COALESCE(
        AVG(ol.order_total),
        0
    ) AS average_order_value,
    MIN(ol.order_date) AS first_order_date,
    MAX(ol.order_date) AS latest_order_date
FROM customers AS c
LEFT JOIN order_level AS ol
    ON c.customer_id = ol.customer_id
GROUP BY
    c.customer_id,
    c.customer_name,
    c.email,
    c.city;


CREATE VIEW vw_product_sales_summary AS
SELECT
    p.product_id,
    p.product_name,
    p.category,
    p.unit_price,
    p.stock_quantity,
    COUNT(
        DISTINCT oi.order_id
    ) AS total_orders,
    COALESCE(
        SUM(oi.quantity),
        0
    ) AS units_sold,
    COALESCE(
        SUM(oi.line_total),
        0
    ) AS total_revenue
FROM products AS p
LEFT JOIN order_items AS oi
    ON p.product_id = oi.product_id
GROUP BY
    p.product_id,
    p.product_name,
    p.category,
    p.unit_price,
    p.stock_quantity;


CREATE VIEW vw_daily_sales_summary AS
WITH order_level AS (
    SELECT
        o.order_id,
        o.customer_id,
        o.order_date,
        o.order_total,
        COALESCE(
            SUM(oi.quantity),
            0
        ) AS units_sold,
        COALESCE(
            SUM(oi.line_total),
            0
        ) AS total_revenue
    FROM orders AS o
    LEFT JOIN order_items AS oi
        ON o.order_id = oi.order_id
    GROUP BY
        o.order_id,
        o.customer_id,
        o.order_date,
        o.order_total
)
SELECT
    order_date,
    COUNT(order_id) AS total_orders,
    COUNT(DISTINCT customer_id) AS unique_customers,
    COALESCE(
        SUM(units_sold),
        0
    ) AS units_sold,
    COALESCE(
        SUM(total_revenue),
        0
    ) AS total_revenue,
    COALESCE(
        AVG(order_total),
        0
    ) AS average_order_value
FROM order_level
GROUP BY
    order_date;


CREATE VIEW vw_payment_summary AS
SELECT
    payment_method,
    payment_status,
    COUNT(
        payment_id
    ) AS total_payments,
    COALESCE(
        SUM(payment_amount),
        0
    ) AS total_payment_amount,
    COALESCE(
        AVG(payment_amount),
        0
    ) AS average_payment_amount,
    MIN(payment_date) AS first_payment_date,
    MAX(payment_date) AS latest_payment_date
FROM payments
GROUP BY
    payment_method,
    payment_status;


CREATE VIEW vw_payment_reconciliation AS
WITH order_item_totals AS (
    SELECT
        order_id,
        COALESCE(
            SUM(line_total),
            0
        ) AS calculated_order_total
    FROM order_items
    GROUP BY
        order_id
),
payment_totals AS (
    SELECT
        order_id,
        COALESCE(
            SUM(
                CASE
                    WHEN payment_status = 'PAID'
                        THEN payment_amount
                    ELSE 0
                END
            ),
            0
        ) AS paid_amount,
        COUNT(payment_id) AS payment_record_count
    FROM payments
    GROUP BY
        order_id
)
SELECT
    o.order_id,
    o.customer_id,
    o.order_date,
    o.order_status,
    o.order_total AS stored_order_total,
    COALESCE(
        oit.calculated_order_total,
        0
    ) AS calculated_order_total,
    COALESCE(
        pt.paid_amount,
        0
    ) AS paid_amount,
    COALESCE(
        pt.payment_record_count,
        0
    ) AS payment_record_count,
    ROUND(
        o.order_total
        - COALESCE(
            oit.calculated_order_total,
            0
        ),
        2
    ) AS order_total_difference,
    ROUND(
        o.order_total
        - COALESCE(
            pt.paid_amount,
            0
        ),
        2
    ) AS payment_difference,
    CASE
        WHEN ABS(
            o.order_total
            - COALESCE(
                oit.calculated_order_total,
                0
            )
        ) > 0.01
            THEN 'ORDER_TOTAL_MISMATCH'

        WHEN o.order_status = 'COMPLETED'
             AND ABS(
                 o.order_total
                 - COALESCE(
                     pt.paid_amount,
                     0
                 )
             ) > 0.01
            THEN 'PAYMENT_MISMATCH'

        ELSE 'MATCHED'
    END AS reconciliation_status
FROM orders AS o
LEFT JOIN order_item_totals AS oit
    ON o.order_id = oit.order_id
LEFT JOIN payment_totals AS pt
    ON o.order_id = pt.order_id;


CREATE VIEW vw_data_quality_summary AS
SELECT
    'rejected_influencer_records'
        AS quality_source,
    rejection_reason AS issue_type,
    COUNT(*) AS issue_count,
    COUNT(
        DISTINCT source_file
    ) AS affected_source_count,
    MIN(rejected_at) AS first_detected_at,
    MAX(rejected_at) AS latest_detected_at
FROM rejected_influencer_records
GROUP BY
    rejection_reason

UNION ALL

SELECT
    'pipeline_audit'
        AS quality_source,
    step_name AS issue_type,
    COUNT(*) AS issue_count,
    COUNT(
        DISTINCT run_id
    ) AS affected_source_count,
    MIN(started_at) AS first_detected_at,
    MAX(completed_at) AS latest_detected_at
FROM pipeline_audit
WHERE run_status = 'FAILED'
GROUP BY
    step_name;


CREATE VIEW vw_pipeline_run_summary AS
SELECT
    run_id,
    pipeline_name,
    MIN(started_at) AS pipeline_started_at,
    MAX(completed_at) AS pipeline_completed_at,
    COUNT(audit_id) AS total_steps,
    COALESCE(
        SUM(rows_processed),
        0
    ) AS total_rows_processed,
    COALESCE(
        SUM(rows_inserted),
        0
    ) AS total_rows_inserted,
    COALESCE(
        SUM(rows_updated),
        0
    ) AS total_rows_updated,
    COALESCE(
        SUM(rows_rejected),
        0
    ) AS total_rows_rejected,
    CASE
        WHEN SUM(
            CASE
                WHEN run_status = 'FAILED'
                    THEN 1
                ELSE 0
            END
        ) > 0
            THEN 'FAILED'

        WHEN SUM(
            CASE
                WHEN run_status = 'RUNNING'
                    THEN 1
                ELSE 0
            END
        ) > 0
            THEN 'RUNNING'

        ELSE 'SUCCESS'
    END AS pipeline_status
FROM pipeline_audit
GROUP BY
    run_id,
    pipeline_name;


CREATE VIEW vw_pipeline_step_monitoring AS
SELECT
    step_log_id,
    pipeline_name,
    run_id,
    step_number,
    step_name,
    script_name,
    attempt_number,
    status,

    start_time,
    end_time,

    ROUND(
        duration_seconds,
        4
    ) AS duration_seconds,

    rows_read,
    rows_written,
    rows_rejected,

    error_type,
    error_message,

    ROUND(
        sla_threshold_seconds,
        4
    ) AS sla_threshold_seconds,

    sla_status,

    CASE
        WHEN duration_seconds IS NULL
            OR sla_threshold_seconds IS NULL
            THEN NULL

        WHEN duration_seconds > sla_threshold_seconds
            THEN ROUND(
                duration_seconds - sla_threshold_seconds,
                4
            )

        ELSE 0
    END AS seconds_over_sla,

    CASE
        WHEN duration_seconds IS NULL
            OR sla_threshold_seconds IS NULL
            OR sla_threshold_seconds = 0
            THEN NULL

        ELSE ROUND(
            duration_seconds
            / sla_threshold_seconds
            * 100,
            2
        )
    END AS sla_utilization_percent,

    created_at,
    updated_at

FROM pipeline_step_log;

CREATE VIEW vw_pipeline_sla_monitoring AS
SELECT
    sla_metric_id,
    pipeline_name,
    run_id,
    step_name,
    attempt_number,
    step_run_status,
    ROUND(
        duration_seconds,
        4
    ) AS duration_seconds,
    ROUND(
        sla_threshold_seconds,
        4
    ) AS sla_threshold_seconds,
    ROUND(
        CASE
            WHEN duration_seconds
                 > sla_threshold_seconds
                THEN duration_seconds
                     - sla_threshold_seconds
            ELSE 0
        END,
        4
    ) AS seconds_over_sla,
    ROUND(
        duration_seconds
        / sla_threshold_seconds
        * 100,
        2
    ) AS sla_utilization_percent,
    sla_status,
    measured_at,
    created_at
FROM pipeline_sla_metrics;


CREATE VIEW vw_pipeline_alert_monitoring AS
SELECT
    a.alert_id,
    a.alert_key,
    a.alert_fingerprint,
    a.source_type,
    a.alert_type,
    a.severity,

    CASE a.severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'ERROR' THEN 2
        WHEN 'WARNING' THEN 3
        ELSE 99
    END AS severity_priority,

    a.status,

    CASE a.status
        WHEN 'OPEN' THEN 1
        WHEN 'ACKNOWLEDGED' THEN 2
        WHEN 'RESOLVED' THEN 3
        ELSE 99
    END AS status_priority,

    CASE
        WHEN a.status IN (
            'OPEN',
            'ACKNOWLEDGED'
        )
            THEN 1
        ELSE 0
    END AS is_active,

    a.pipeline_name,
    a.run_id AS alert_run_id,
    a.step_name,
    a.attempt_number AS alert_attempt_number,

    a.title,
    a.message,

    a.first_detected_at,
    a.last_detected_at,
    a.occurrence_count,

    a.acknowledged_at,
    a.resolved_at,

    a.created_at,
    a.updated_at,

    o.occurrence_id AS latest_occurrence_id,
    o.run_id AS latest_occurrence_run_id,
    o.attempt_number
        AS latest_occurrence_attempt_number,
    o.detected_at
        AS latest_occurrence_detected_at,
    o.error_type
        AS latest_error_type,
    o.raw_error_message
        AS latest_raw_error_message,
    o.normalized_error_signature
        AS latest_normalized_error_signature

FROM pipeline_alerts AS a
LEFT JOIN pipeline_alert_occurrences AS o
    ON o.occurrence_id = (
        SELECT o2.occurrence_id
        FROM pipeline_alert_occurrences AS o2
        WHERE o2.alert_id = a.alert_id
        ORDER BY
            o2.detected_at DESC,
            o2.occurrence_id DESC
        LIMIT 1
    );


CREATE VIEW vw_influencer_payment_details AS
SELECT
    ip.influencer_payment_id,
    c.campaign_id,
    c.campaign_name,
    c.source_section,
    i.influencer_id,
    i.influencer_handle,
    ip.source_sequence,
    ip.fee_amount,
    ip.post_date,
    ip.payment_round_date,
    ip.payment_status,
    ip.notes_sanitized,
    ip.source_file,
    ip.source_sheet,
    ip.source_row_number,
    ip.created_at,
    ip.updated_at
FROM influencer_payments AS ip
INNER JOIN campaigns AS c
    ON ip.campaign_id = c.campaign_id
INNER JOIN influencers AS i
    ON ip.influencer_id = i.influencer_id;


CREATE VIEW vw_campaign_payment_summary AS
SELECT
    c.campaign_id,
    c.campaign_name,
    c.source_section,
    COUNT(
        ip.influencer_payment_id
    ) AS total_payment_records,
    COUNT(
        DISTINCT ip.influencer_id
    ) AS total_influencers,
    COALESCE(
        SUM(ip.fee_amount),
        0
    ) AS total_fee_amount,
    COALESCE(
        SUM(
            CASE
                WHEN ip.payment_status = 'PAID'
                    THEN ip.fee_amount
                ELSE 0
            END
        ),
        0
    ) AS paid_amount,
    COALESCE(
        SUM(
            CASE
                WHEN ip.payment_status = 'UNPAID'
                    THEN ip.fee_amount
                ELSE 0
            END
        ),
        0
    ) AS unpaid_amount,
    COALESCE(
        SUM(
            CASE
                WHEN ip.payment_status = 'CANCELLED'
                    THEN ip.fee_amount
                ELSE 0
            END
        ),
        0
    ) AS cancelled_amount,
    MIN(ip.post_date) AS first_post_date,
    MAX(ip.post_date) AS latest_post_date
FROM campaigns AS c
LEFT JOIN influencer_payments AS ip
    ON c.campaign_id = ip.campaign_id
GROUP BY
    c.campaign_id,
    c.campaign_name,
    c.source_section;


CREATE VIEW vw_influencer_payment_summary AS
SELECT
    i.influencer_id,
    i.influencer_handle,
    COUNT(
        ip.influencer_payment_id
    ) AS total_payment_records,
    COUNT(
        DISTINCT ip.campaign_id
    ) AS total_campaigns,
    COALESCE(
        SUM(ip.fee_amount),
        0
    ) AS total_fee_amount,
    COALESCE(
        SUM(
            CASE
                WHEN ip.payment_status = 'PAID'
                    THEN ip.fee_amount
                ELSE 0
            END
        ),
        0
    ) AS total_paid_amount,
    COALESCE(
        SUM(
            CASE
                WHEN ip.payment_status = 'UNPAID'
                    THEN ip.fee_amount
                ELSE 0
            END
        ),
        0
    ) AS total_unpaid_amount,
    MIN(ip.post_date) AS first_post_date,
    MAX(ip.post_date) AS latest_post_date
FROM influencers AS i
LEFT JOIN influencer_payments AS ip
    ON i.influencer_id = ip.influencer_id
GROUP BY
    i.influencer_id,
    i.influencer_handle;


CREATE VIEW vw_payment_status_summary AS
SELECT
    payment_status,
    COUNT(
        influencer_payment_id
    ) AS total_records,
    COUNT(
        DISTINCT influencer_id
    ) AS total_influencers,
    COUNT(
        DISTINCT campaign_id
    ) AS total_campaigns,
    COALESCE(
        SUM(fee_amount),
        0
    ) AS total_fee_amount,
    COALESCE(
        AVG(fee_amount),
        0
    ) AS average_fee_amount,
    MIN(
        payment_round_date
    ) AS first_payment_round,
    MAX(
        payment_round_date
    ) AS latest_payment_round
FROM influencer_payments
GROUP BY
    payment_status;


CREATE VIEW vw_rejected_influencer_summary AS
SELECT
    rejection_reason,
    COUNT(
        rejection_id
    ) AS rejected_record_count,
    COUNT(
        DISTINCT source_file
    ) AS affected_source_files,
    MIN(rejected_at) AS first_rejected_at,
    MAX(rejected_at) AS latest_rejected_at
FROM rejected_influencer_records
GROUP BY
    rejection_reason;

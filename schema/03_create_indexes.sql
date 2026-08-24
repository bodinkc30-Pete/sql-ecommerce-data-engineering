DROP INDEX IF EXISTS idx_customers_email;
DROP INDEX IF EXISTS idx_customers_signup_date;

DROP INDEX IF EXISTS idx_products_category;
DROP INDEX IF EXISTS idx_products_product_name;

DROP INDEX IF EXISTS idx_orders_customer_id;
DROP INDEX IF EXISTS idx_orders_order_date;
DROP INDEX IF EXISTS idx_orders_order_status;
DROP INDEX IF EXISTS idx_orders_status_date;

DROP INDEX IF EXISTS idx_order_items_order_id;
DROP INDEX IF EXISTS idx_order_items_product_id;

DROP INDEX IF EXISTS idx_payments_order_id;
DROP INDEX IF EXISTS idx_payments_payment_date;
DROP INDEX IF EXISTS idx_payments_date_status;
DROP INDEX IF EXISTS idx_payments_payment_status;

DROP INDEX IF EXISTS idx_pipeline_audit_run_id;
DROP INDEX IF EXISTS idx_pipeline_audit_run_status;
DROP INDEX IF EXISTS idx_pipeline_audit_started_at;

DROP INDEX IF EXISTS idx_pipeline_step_log_run_id;
DROP INDEX IF EXISTS idx_pipeline_step_log_step_name;
DROP INDEX IF EXISTS idx_pipeline_step_log_status;
DROP INDEX IF EXISTS idx_pipeline_step_log_start_time;
DROP INDEX IF EXISTS idx_pipeline_step_log_run_step;

DROP INDEX IF EXISTS idx_pipeline_sla_metrics_run_id;
DROP INDEX IF EXISTS idx_pipeline_sla_metrics_step_name;
DROP INDEX IF EXISTS idx_pipeline_sla_metrics_sla_status;
DROP INDEX IF EXISTS idx_pipeline_sla_metrics_measured_at;

DROP INDEX IF EXISTS idx_pipeline_alerts_status_severity_last_detected;
DROP INDEX IF EXISTS idx_pipeline_alerts_source_type_alert_type_detected;
DROP INDEX IF EXISTS idx_pipeline_alert_occurrences_run_id;
DROP INDEX IF EXISTS idx_pipeline_alert_occurrences_alert_detected;


-- customers.email is already protected by the table-level
-- UNIQUE constraint, so no duplicate user-defined index is created here.

CREATE INDEX idx_customers_signup_date
ON customers(signup_date);


CREATE INDEX idx_products_category
ON products(category);

CREATE INDEX idx_products_product_name
ON products(product_name);


CREATE INDEX idx_orders_customer_id
ON orders(customer_id);

CREATE INDEX idx_orders_order_date
ON orders(order_date);

CREATE INDEX idx_orders_status_date
ON orders(
    order_status,
    order_date
);


CREATE INDEX idx_order_items_order_id
ON order_items(order_id);

CREATE INDEX idx_order_items_product_id
ON order_items(product_id);


CREATE INDEX idx_payments_order_id
ON payments(order_id);

CREATE INDEX idx_payments_date_status
ON payments(
    payment_date,
    payment_status
);

CREATE INDEX idx_payments_payment_status
ON payments(payment_status);


CREATE INDEX idx_pipeline_audit_run_id
ON pipeline_audit(run_id);

CREATE INDEX idx_pipeline_audit_run_status
ON pipeline_audit(run_status);

CREATE INDEX idx_pipeline_audit_started_at
ON pipeline_audit(started_at);


CREATE INDEX idx_pipeline_step_log_run_id
ON pipeline_step_log(run_id);

CREATE INDEX idx_pipeline_step_log_step_name
ON pipeline_step_log(step_name);

CREATE INDEX idx_pipeline_step_log_status
ON pipeline_step_log(status);

CREATE INDEX idx_pipeline_step_log_start_time
ON pipeline_step_log(start_time);

CREATE INDEX idx_pipeline_step_log_run_step
ON pipeline_step_log(
    run_id,
    step_name,
    attempt_number
);


CREATE INDEX idx_pipeline_sla_metrics_run_id
ON pipeline_sla_metrics(run_id);

CREATE INDEX idx_pipeline_sla_metrics_step_name
ON pipeline_sla_metrics(step_name);

CREATE INDEX idx_pipeline_sla_metrics_sla_status
ON pipeline_sla_metrics(sla_status);

CREATE INDEX idx_pipeline_sla_metrics_measured_at
ON pipeline_sla_metrics(measured_at);


CREATE INDEX idx_pipeline_alerts_status_severity_last_detected
ON pipeline_alerts(
    status,
    severity,
    last_detected_at
);

CREATE INDEX idx_pipeline_alerts_source_type_alert_type_detected
ON pipeline_alerts(
    source_type,
    alert_type,
    last_detected_at
);

CREATE INDEX idx_pipeline_alert_occurrences_run_id
ON pipeline_alert_occurrences(run_id);

CREATE INDEX idx_pipeline_alert_occurrences_alert_detected
ON pipeline_alert_occurrences(
    alert_id,
    detected_at
);


DROP INDEX IF EXISTS idx_campaigns_campaign_name;
DROP INDEX IF EXISTS idx_campaigns_source_section;

DROP INDEX IF EXISTS idx_influencers_handle;
DROP INDEX IF EXISTS idx_influencers_bank_account_hash;
DROP INDEX IF EXISTS idx_influencers_contact_phone_hash;

DROP INDEX IF EXISTS idx_influencer_payments_campaign_id;
DROP INDEX IF EXISTS idx_influencer_payments_influencer_id;
DROP INDEX IF EXISTS idx_influencer_payments_payment_status;
DROP INDEX IF EXISTS idx_influencer_payments_post_date;
DROP INDEX IF EXISTS idx_influencer_payments_payment_round_date;
DROP INDEX IF EXISTS idx_influencer_payments_source_location;

DROP INDEX IF EXISTS idx_rejected_influencer_source_location;
DROP INDEX IF EXISTS idx_rejected_influencer_rejected_at;


CREATE INDEX idx_campaigns_campaign_name
ON campaigns(campaign_name);

CREATE INDEX idx_campaigns_source_section
ON campaigns(source_section);


CREATE UNIQUE INDEX idx_influencers_handle
ON influencers(influencer_handle);

CREATE INDEX idx_influencers_bank_account_hash
ON influencers(bank_account_hash);

CREATE INDEX idx_influencers_contact_phone_hash
ON influencers(contact_phone_hash);


CREATE INDEX idx_influencer_payments_campaign_id
ON influencer_payments(campaign_id);

CREATE INDEX idx_influencer_payments_influencer_id
ON influencer_payments(influencer_id);

CREATE INDEX idx_influencer_payments_payment_status
ON influencer_payments(payment_status);

CREATE INDEX idx_influencer_payments_post_date
ON influencer_payments(post_date);

CREATE INDEX idx_influencer_payments_payment_round_date
ON influencer_payments(payment_round_date);

CREATE INDEX idx_influencer_payments_source_location
ON influencer_payments(
    source_file,
    source_sheet,
    source_row_number
);


CREATE INDEX idx_rejected_influencer_source_location
ON rejected_influencer_records(
    source_file,
    source_sheet,
    source_row_number
);

CREATE INDEX idx_rejected_influencer_rejected_at
ON rejected_influencer_records(rejected_at);
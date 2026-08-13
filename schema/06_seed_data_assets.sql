PRAGMA foreign_keys = ON;

INSERT INTO data_assets (
    asset_key, asset_name, asset_type, data_layer, data_domain,
    source_system, asset_location, data_format, classification,
    contains_pii, owner_name, description, is_active
)
VALUES
('file://synthetic/customers.csv','customers.csv','FILE','SOURCE','ECOMMERCE','LOCAL_FILESYSTEM','data/raw/synthetic/customers.csv','CSV','INTERNAL',1,'Data Engineering','Raw customer source used by the e-commerce pipeline.',1),
('file://synthetic/products.csv','products.csv','FILE','SOURCE','ECOMMERCE','LOCAL_FILESYSTEM','data/raw/synthetic/products.csv','CSV','INTERNAL',0,'Data Engineering','Raw product source used by the e-commerce pipeline.',1),
('file://synthetic/orders.csv','orders.csv','FILE','SOURCE','ECOMMERCE','LOCAL_FILESYSTEM','data/raw/synthetic/orders.csv','CSV','INTERNAL',0,'Data Engineering','Raw order source used by the e-commerce pipeline.',1),
('file://synthetic/order_items.csv','order_items.csv','FILE','SOURCE','ECOMMERCE','LOCAL_FILESYSTEM','data/raw/synthetic/order_items.csv','CSV','INTERNAL',0,'Data Engineering','Raw order item source used by the e-commerce pipeline.',1),
('file://synthetic/payments.csv','payments.csv','FILE','SOURCE','ECOMMERCE','LOCAL_FILESYSTEM','data/raw/synthetic/payments.csv','CSV','CONFIDENTIAL',0,'Data Engineering','Raw payment source used by the e-commerce pipeline.',1),
('file://pawchoice/pawchoice_payments.xlsx','pawchoice_payments.xlsx','FILE','SOURCE','INFLUENCER_PAYMENT','LOCAL_FILESYSTEM','data/raw/pawchoice/pawchoice_payments.xlsx','XLSX','RESTRICTED',1,'Data Engineering','Operational PawChoice influencer-payment workbook. Sensitive fields are protected during ingestion.',1),

('sqlite://staging/stg_customers','stg_customers','TABLE','STAGING','ECOMMERCE','SQLITE','stg_customers','SQLITE_TABLE','INTERNAL',1,'Data Engineering','Raw customer staging table.',1),
('sqlite://staging/stg_products','stg_products','TABLE','STAGING','ECOMMERCE','SQLITE','stg_products','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Raw product staging table.',1),
('sqlite://staging/stg_orders','stg_orders','TABLE','STAGING','ECOMMERCE','SQLITE','stg_orders','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Raw order staging table.',1),
('sqlite://staging/stg_order_items','stg_order_items','TABLE','STAGING','ECOMMERCE','SQLITE','stg_order_items','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Raw order-item staging table.',1),
('sqlite://staging/stg_payments','stg_payments','TABLE','STAGING','ECOMMERCE','SQLITE','stg_payments','SQLITE_TABLE','CONFIDENTIAL',0,'Data Engineering','Raw payment staging table.',1),
('sqlite://staging/stg_influencer_payments','stg_influencer_payments','TABLE','STAGING','INFLUENCER_PAYMENT','SQLITE','stg_influencer_payments','SQLITE_TABLE','RESTRICTED',1,'Data Engineering','PawChoice influencer-payment staging table with protected PII and source-row metadata.',1),

('sqlite://core/customers','customers','TABLE','CORE','ECOMMERCE','SQLITE','customers','SQLITE_TABLE','CONFIDENTIAL',1,'Data Engineering','Clean customer master table.',1),
('sqlite://core/products','products','TABLE','CORE','ECOMMERCE','SQLITE','products','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Clean product master table.',1),
('sqlite://core/orders','orders','TABLE','CORE','ECOMMERCE','SQLITE','orders','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Clean order transaction table.',1),
('sqlite://core/order_items','order_items','TABLE','CORE','ECOMMERCE','SQLITE','order_items','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Clean order-item transaction table.',1),
('sqlite://core/payments','payments','TABLE','CORE','ECOMMERCE','SQLITE','payments','SQLITE_TABLE','CONFIDENTIAL',0,'Data Engineering','Clean payment transaction table.',1),
('sqlite://core/campaigns','campaigns','TABLE','CORE','INFLUENCER_PAYMENT','SQLITE','campaigns','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Campaign master derived from operational payment data.',1),
('sqlite://core/influencers','influencers','TABLE','CORE','INFLUENCER_PAYMENT','SQLITE','influencers','SQLITE_TABLE','RESTRICTED',1,'Data Engineering','Influencer master containing protected PII representations.',1),
('sqlite://core/influencer_payments','influencer_payments','TABLE','CORE','INFLUENCER_PAYMENT','SQLITE','influencer_payments','SQLITE_TABLE','CONFIDENTIAL',0,'Data Engineering','Clean influencer-payment fact table with source-file/sheet/row lineage metadata.',1),
('sqlite://core/rejected_influencer_records','rejected_influencer_records','TABLE','CORE','INFLUENCER_PAYMENT','SQLITE','rejected_influencer_records','SQLITE_TABLE','RESTRICTED',1,'Data Engineering','Rejected operational records retained for audit and remediation.',1),

('sqlite://mart/vw_daily_sales_summary','vw_daily_sales_summary','VIEW','MART','ECOMMERCE','SQLITE','vw_daily_sales_summary','SQLITE_VIEW','INTERNAL',0,'Data Engineering','Daily sales analytical summary.',1),
('sqlite://mart/vw_customer_order_summary','vw_customer_order_summary','VIEW','MART','ECOMMERCE','SQLITE','vw_customer_order_summary','SQLITE_VIEW','CONFIDENTIAL',1,'Data Engineering','Customer-level order summary.',1),
('sqlite://mart/vw_product_sales_summary','vw_product_sales_summary','VIEW','MART','ECOMMERCE','SQLITE','vw_product_sales_summary','SQLITE_VIEW','INTERNAL',0,'Data Engineering','Product sales analytical summary.',1),
('sqlite://mart/vw_payment_reconciliation','vw_payment_reconciliation','VIEW','MART','ECOMMERCE','SQLITE','vw_payment_reconciliation','SQLITE_VIEW','CONFIDENTIAL',0,'Data Engineering','Order-payment reconciliation view.',1),
('sqlite://mart/vw_influencer_payment_summary','vw_influencer_payment_summary','VIEW','MART','INFLUENCER_PAYMENT','SQLITE','vw_influencer_payment_summary','SQLITE_VIEW','CONFIDENTIAL',0,'Data Engineering','Influencer payment analytical summary.',1),
('sqlite://mart/vw_campaign_payment_summary','vw_campaign_payment_summary','VIEW','MART','INFLUENCER_PAYMENT','SQLITE','vw_campaign_payment_summary','SQLITE_VIEW','CONFIDENTIAL',0,'Data Engineering','Campaign-level payment analytical summary.',1),

('sqlite://metadata/pipeline_audit','pipeline_audit','TABLE','METADATA','PIPELINE_OPERATIONS','SQLITE','pipeline_audit','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Pipeline-run audit metadata including run type, recovery and backfill context.',1),
('sqlite://metadata/pipeline_step_log','pipeline_step_log','TABLE','METADATA','PIPELINE_OPERATIONS','SQLITE','pipeline_step_log','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Step-level execution, retry, row-count, error and SLA metadata.',1),
('sqlite://metadata/pipeline_sla_metrics','pipeline_sla_metrics','TABLE','METADATA','PIPELINE_OPERATIONS','SQLITE','pipeline_sla_metrics','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Pipeline SLA measurement history.',1),
('sqlite://metadata/pipeline_watermark','pipeline_watermark','TABLE','METADATA','PIPELINE_OPERATIONS','SQLITE','pipeline_watermark','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Incremental-load watermark state.',1),
('sqlite://metadata/data_assets','data_assets','TABLE','METADATA','DATA_GOVERNANCE','SQLITE','data_assets','SQLITE_TABLE','INTERNAL',0,'Data Engineering','Governance registry for source, staging, core, mart and metadata assets.',1)

ON CONFLICT(asset_key) DO UPDATE SET
    asset_name=excluded.asset_name,
    asset_type=excluded.asset_type,
    data_layer=excluded.data_layer,
    data_domain=excluded.data_domain,
    source_system=excluded.source_system,
    asset_location=excluded.asset_location,
    data_format=excluded.data_format,
    classification=excluded.classification,
    contains_pii=excluded.contains_pii,
    owner_name=excluded.owner_name,
    description=excluded.description,
    is_active=excluded.is_active,
    updated_at=CURRENT_TIMESTAMP;

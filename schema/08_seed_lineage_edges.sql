PRAGMA foreign_keys = ON;

-- Governance / Lineage
-- Step G3B: Seed dataset-level lineage for the current project.
-- Idempotent: ON CONFLICT updates metadata instead of creating duplicates.

INSERT INTO lineage_edges (
    upstream_asset_id,
    downstream_asset_id,
    transformation_name,
    transformation_type,
    process_reference,
    lineage_level,
    run_id,
    is_active
)
SELECT
    up.asset_id,
    down.asset_id,
    seed.transformation_name,
    seed.transformation_type,
    seed.process_reference,
    'DATASET',
    NULL,
    1
FROM (
    -- =========================================================
    -- SOURCE -> STAGING
    -- =========================================================
    SELECT
        'file://synthetic/customers.csv' AS upstream_key,
        'sqlite://staging/stg_customers' AS downstream_key,
        'LOAD_CUSTOMERS_RAW' AS transformation_name,
        'INGESTION' AS transformation_type,
        'scripts/02_load_raw_data.py' AS process_reference
    UNION ALL SELECT
        'file://synthetic/products.csv',
        'sqlite://staging/stg_products',
        'LOAD_PRODUCTS_RAW',
        'INGESTION',
        'scripts/02_load_raw_data.py'
    UNION ALL SELECT
        'file://synthetic/orders.csv',
        'sqlite://staging/stg_orders',
        'LOAD_ORDERS_RAW',
        'INGESTION',
        'scripts/02_load_raw_data.py'
    UNION ALL SELECT
        'file://synthetic/order_items.csv',
        'sqlite://staging/stg_order_items',
        'LOAD_ORDER_ITEMS_RAW',
        'INGESTION',
        'scripts/02_load_raw_data.py'
    UNION ALL SELECT
        'file://synthetic/payments.csv',
        'sqlite://staging/stg_payments',
        'LOAD_PAYMENTS_RAW',
        'INGESTION',
        'scripts/02_load_raw_data.py'
    UNION ALL SELECT
        'file://pawchoice/pawchoice_payments.xlsx',
        'sqlite://staging/stg_influencer_payments',
        'LOAD_PAWCHOICE_INFLUENCER_PAYMENTS',
        'INGESTION',
        'scripts/02_load_raw_data.py'

    -- =========================================================
    -- STAGING -> CORE
    -- =========================================================
    UNION ALL SELECT
        'sqlite://staging/stg_customers',
        'sqlite://core/customers',
        'CLEAN_CUSTOMERS',
        'CLEANING',
        'transformations/01_clean_customers.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_products',
        'sqlite://core/products',
        'CLEAN_PRODUCTS',
        'CLEANING',
        'transformations/02_clean_products.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_orders',
        'sqlite://core/orders',
        'CLEAN_ORDERS',
        'CLEANING',
        'transformations/03_clean_orders.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_order_items',
        'sqlite://core/order_items',
        'CLEAN_ORDER_ITEMS',
        'CLEANING',
        'transformations/04_clean_order_items.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_payments',
        'sqlite://core/payments',
        'CLEAN_PAYMENTS',
        'CLEANING',
        'transformations/05_clean_payments.sql'

    -- Incremental controller edges
    UNION ALL SELECT
        'sqlite://staging/stg_customers',
        'sqlite://core/customers',
        'INCREMENTAL_CUSTOMERS',
        'INCREMENTAL_LOAD',
        'transformations/06_incremental_load.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_products',
        'sqlite://core/products',
        'INCREMENTAL_PRODUCTS',
        'INCREMENTAL_LOAD',
        'transformations/06_incremental_load.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_orders',
        'sqlite://core/orders',
        'INCREMENTAL_ORDERS',
        'INCREMENTAL_LOAD',
        'transformations/06_incremental_load.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_order_items',
        'sqlite://core/order_items',
        'INCREMENTAL_ORDER_ITEMS',
        'INCREMENTAL_LOAD',
        'transformations/06_incremental_load.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_payments',
        'sqlite://core/payments',
        'INCREMENTAL_PAYMENTS',
        'INCREMENTAL_LOAD',
        'transformations/06_incremental_load.sql'

    -- PawChoice staging fans out to multiple governed core assets.
    UNION ALL SELECT
        'sqlite://staging/stg_influencer_payments',
        'sqlite://core/campaigns',
        'BUILD_CAMPAIGNS',
        'TRANSFORMATION',
        'transformations/07_clean_influencer_payments.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_influencer_payments',
        'sqlite://core/influencers',
        'BUILD_INFLUENCERS',
        'TRANSFORMATION',
        'transformations/07_clean_influencer_payments.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_influencer_payments',
        'sqlite://core/influencer_payments',
        'BUILD_INFLUENCER_PAYMENTS',
        'TRANSFORMATION',
        'transformations/07_clean_influencer_payments.sql'
    UNION ALL SELECT
        'sqlite://staging/stg_influencer_payments',
        'sqlite://core/rejected_influencer_records',
        'ROUTE_REJECTED_INFLUENCER_RECORDS',
        'QUALITY',
        'transformations/07_clean_influencer_payments.sql'

    -- =========================================================
    -- CORE -> MART / ANALYTICAL VIEWS
    -- =========================================================
    UNION ALL SELECT
        'sqlite://core/orders',
        'sqlite://mart/vw_daily_sales_summary',
        'BUILD_DAILY_SALES_SUMMARY',
        'AGGREGATION',
        'schema/04_create_views.sql'

    UNION ALL SELECT
        'sqlite://core/customers',
        'sqlite://mart/vw_customer_order_summary',
        'BUILD_CUSTOMER_ORDER_SUMMARY_CUSTOMERS',
        'AGGREGATION',
        'schema/04_create_views.sql'
    UNION ALL SELECT
        'sqlite://core/orders',
        'sqlite://mart/vw_customer_order_summary',
        'BUILD_CUSTOMER_ORDER_SUMMARY_ORDERS',
        'AGGREGATION',
        'schema/04_create_views.sql'

    UNION ALL SELECT
        'sqlite://core/products',
        'sqlite://mart/vw_product_sales_summary',
        'BUILD_PRODUCT_SALES_SUMMARY_PRODUCTS',
        'AGGREGATION',
        'schema/04_create_views.sql'
    UNION ALL SELECT
        'sqlite://core/order_items',
        'sqlite://mart/vw_product_sales_summary',
        'BUILD_PRODUCT_SALES_SUMMARY_ORDER_ITEMS',
        'AGGREGATION',
        'schema/04_create_views.sql'
    UNION ALL SELECT
        'sqlite://core/orders',
        'sqlite://mart/vw_product_sales_summary',
        'BUILD_PRODUCT_SALES_SUMMARY_ORDERS',
        'AGGREGATION',
        'schema/04_create_views.sql'

    UNION ALL SELECT
        'sqlite://core/orders',
        'sqlite://mart/vw_payment_reconciliation',
        'BUILD_PAYMENT_RECONCILIATION_ORDERS',
        'RECONCILIATION',
        'schema/04_create_views.sql'
    UNION ALL SELECT
        'sqlite://core/payments',
        'sqlite://mart/vw_payment_reconciliation',
        'BUILD_PAYMENT_RECONCILIATION_PAYMENTS',
        'RECONCILIATION',
        'schema/04_create_views.sql'

    UNION ALL SELECT
        'sqlite://core/influencers',
        'sqlite://mart/vw_influencer_payment_summary',
        'BUILD_INFLUENCER_PAYMENT_SUMMARY_INFLUENCERS',
        'AGGREGATION',
        'schema/04_create_views.sql'
    UNION ALL SELECT
        'sqlite://core/influencer_payments',
        'sqlite://mart/vw_influencer_payment_summary',
        'BUILD_INFLUENCER_PAYMENT_SUMMARY_PAYMENTS',
        'AGGREGATION',
        'schema/04_create_views.sql'

    UNION ALL SELECT
        'sqlite://core/campaigns',
        'sqlite://mart/vw_campaign_payment_summary',
        'BUILD_CAMPAIGN_PAYMENT_SUMMARY_CAMPAIGNS',
        'AGGREGATION',
        'schema/04_create_views.sql'
    UNION ALL SELECT
        'sqlite://core/influencer_payments',
        'sqlite://mart/vw_campaign_payment_summary',
        'BUILD_CAMPAIGN_PAYMENT_SUMMARY_PAYMENTS',
        'AGGREGATION',
        'schema/04_create_views.sql'
) AS seed
JOIN data_assets AS up
    ON up.asset_key = seed.upstream_key
JOIN data_assets AS down
    ON down.asset_key = seed.downstream_key

ON CONFLICT (
    upstream_asset_id,
    downstream_asset_id,
    transformation_name,
    lineage_level
)
DO UPDATE SET
    transformation_type = excluded.transformation_type,
    process_reference = excluded.process_reference,
    is_active = excluded.is_active,
    updated_at = CURRENT_TIMESTAMP;

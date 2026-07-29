PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS stg_customers;

CREATE TABLE stg_customers (
    customer_id TEXT,
    customer_name TEXT,
    email TEXT,
    city TEXT,
    signup_date TEXT,
    source_file TEXT,
    loaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);

DROP TABLE IF EXISTS stg_products;

CREATE TABLE stg_products (
    product_id TEXT,
    product_name TEXT,
    category TEXT,
    unit_price TEXT,
    stock_quantity TEXT,
    source_file TEXT,
    loaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);
DROP TABLE IF EXISTS stg_orders;

CREATE TABLE stg_orders (
    order_id TEXT,
    customer_id TEXT,
    order_date TEXT,
    order_status TEXT,
    source_file TEXT,
    loaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);
DROP TABLE IF EXISTS stg_order_items;

CREATE TABLE stg_order_items (
    order_item_id TEXT,
    order_id TEXT,
    product_id TEXT,
    quantity TEXT,
    unit_price TEXT,
    source_file TEXT,
    loaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);
DROP TABLE IF EXISTS stg_payments;

CREATE TABLE stg_payments (
    payment_id TEXT,
    order_id TEXT,
    payment_date TEXT,
    payment_method TEXT,
    payment_amount TEXT,
    payment_status TEXT,
    source_file TEXT,
    loaded_at TEXT DEFAULT CURRENT_TIMESTAMP
);
DROP TABLE IF EXISTS stg_influencer_payments;

CREATE TABLE stg_influencer_payments (
    staging_row_id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_name TEXT,
    source_section TEXT,
    sequence_number TEXT,
    influencer_handle TEXT,
    fee_amount TEXT,
    post_date_text TEXT,
    bank_account_hash TEXT,
    payment_round_text TEXT,
    payment_status TEXT,
    contact_phone_hash TEXT,
    account_name_masked TEXT,
    notes_sanitized TEXT,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    loaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
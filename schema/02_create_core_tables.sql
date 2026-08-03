PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS payments;
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS pipeline_watermark;
DROP TABLE IF EXISTS pipeline_audit;

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    customer_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    city TEXT,
    signup_date DATE NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    product_name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    stock_quantity INTEGER NOT NULL DEFAULT 0 CHECK (stock_quantity >= 0),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date DATE NOT NULL,
    order_status TEXT NOT NULL,
    order_total REAL NOT NULL DEFAULT 0 CHECK (order_total >= 0),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price REAL NOT NULL CHECK (unit_price >= 0),
    line_total REAL NOT NULL CHECK (line_total >= 0),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    FOREIGN KEY (product_id)
        REFERENCES products(product_id)
);

CREATE TABLE payments (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    payment_date DATE NOT NULL,
    payment_method TEXT NOT NULL,
    payment_amount REAL NOT NULL CHECK (payment_amount >= 0),
    payment_status TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (order_id)
        REFERENCES orders(order_id)
);

CREATE TABLE pipeline_watermark (
    table_name TEXT PRIMARY KEY,
    last_loaded_at TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE pipeline_audit (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    pipeline_name TEXT NOT NULL,
    run_id TEXT NOT NULL,
    step_name TEXT NOT NULL,
    run_status TEXT NOT NULL,
    rows_processed INTEGER DEFAULT 0 CHECK (rows_processed >= 0),
    rows_inserted INTEGER DEFAULT 0 CHECK (rows_inserted >= 0),
    rows_updated INTEGER DEFAULT 0 CHECK (rows_updated >= 0),
    rows_rejected INTEGER DEFAULT 0 CHECK (rows_rejected >= 0),
    error_message TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

DROP TABLE IF EXISTS rejected_influencer_records;
DROP TABLE IF EXISTS influencer_payments;
DROP TABLE IF EXISTS influencers;
DROP TABLE IF EXISTS campaigns;

CREATE TABLE campaigns (
    campaign_id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_name TEXT NOT NULL,
    source_section TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (campaign_name, source_section)
);

CREATE TABLE influencers (
    influencer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    influencer_handle TEXT NOT NULL UNIQUE,
    bank_account_hash TEXT,
    contact_phone_hash TEXT,
    account_name_masked TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE influencer_payments (
    influencer_payment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id INTEGER NOT NULL,
    influencer_id INTEGER NOT NULL,
    source_sequence TEXT,
    fee_amount REAL NOT NULL CHECK (fee_amount >= 0),
    post_date TEXT,
    payment_round_date TEXT,
    payment_status TEXT NOT NULL,
    notes_sanitized TEXT,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (campaign_id)
        REFERENCES campaigns(campaign_id),
    FOREIGN KEY (influencer_id)
        REFERENCES influencers(influencer_id)
);

CREATE TABLE rejected_influencer_records (
    rejection_id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_name TEXT,
    source_section TEXT,
    sequence_number TEXT,
    influencer_handle TEXT,
    fee_amount_text TEXT,
    post_date_text TEXT,
    payment_round_text TEXT,
    payment_status_text TEXT,
    rejection_reason TEXT NOT NULL,
    source_file TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    source_row_number INTEGER NOT NULL,
    rejected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

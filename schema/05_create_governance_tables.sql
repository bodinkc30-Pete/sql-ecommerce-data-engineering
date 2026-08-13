PRAGMA foreign_keys = ON;

-- Governance / Data Asset Registry
-- Step G2: data_assets only.
-- lineage_edges will be added after this registry is accepted.

CREATE TABLE IF NOT EXISTS data_assets (
    asset_id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Stable logical identifier used by governance/lineage code.
    -- Examples:
    --   file://synthetic/orders.csv
    --   sqlite://staging/stg_orders
    --   sqlite://core/orders
    asset_key TEXT NOT NULL UNIQUE,

    asset_name TEXT NOT NULL,

    asset_type TEXT NOT NULL
        CHECK (
            asset_type IN (
                'FILE',
                'TABLE',
                'VIEW',
                'API',
                'STREAM',
                'REPORT',
                'DASHBOARD',
                'MODEL'
            )
        ),

    data_layer TEXT NOT NULL
        CHECK (
            data_layer IN (
                'SOURCE',
                'STAGING',
                'CORE',
                'MART',
                'OUTPUT',
                'METADATA'
            )
        ),

    -- Business / technical domain.
    -- Examples: ECOMMERCE, INFLUENCER_PAYMENT, PIPELINE_OPERATIONS
    data_domain TEXT NOT NULL,

    -- Source platform or storage engine.
    -- Examples: LOCAL_FILESYSTEM, SQLITE, TIKTOK_SELLER, ODOO
    source_system TEXT,

    -- Physical or logical location.
    -- Examples:
    --   data/raw/synthetic/orders.csv
    --   stg_orders
    --   orders
    asset_location TEXT NOT NULL,

    -- Examples: CSV, XLSX, SQLITE_TABLE, SQLITE_VIEW, JSON
    data_format TEXT,

    classification TEXT NOT NULL DEFAULT 'INTERNAL'
        CHECK (
            classification IN (
                'PUBLIC',
                'INTERNAL',
                'CONFIDENTIAL',
                'RESTRICTED'
            )
        ),

    contains_pii INTEGER NOT NULL DEFAULT 0
        CHECK (contains_pii IN (0, 1)),

    owner_name TEXT NOT NULL DEFAULT 'Data Engineering',

    description TEXT,

    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_data_assets_domain_layer
    ON data_assets (data_domain, data_layer);

CREATE INDEX IF NOT EXISTS idx_data_assets_classification
    ON data_assets (classification);

CREATE INDEX IF NOT EXISTS idx_data_assets_type
    ON data_assets (asset_type);

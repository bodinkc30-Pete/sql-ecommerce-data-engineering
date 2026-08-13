PRAGMA foreign_keys = ON;

-- Governance / Lineage
-- Step G3: Dataset-level lineage edges.
-- This table models relationships between registered data assets.
-- It is intentionally dataset-level first; row/column lineage can be added later.

CREATE TABLE IF NOT EXISTS lineage_edges (
    lineage_edge_id INTEGER PRIMARY KEY AUTOINCREMENT,

    upstream_asset_id INTEGER NOT NULL,
    downstream_asset_id INTEGER NOT NULL,

    -- Transformation / processing context.
    transformation_name TEXT NOT NULL,
    transformation_type TEXT NOT NULL
        CHECK (
            transformation_type IN (
                'INGESTION',
                'CLEANING',
                'TRANSFORMATION',
                'INCREMENTAL_LOAD',
                'AGGREGATION',
                'RECONCILIATION',
                'QUALITY',
                'EXPORT',
                'OTHER'
            )
        ),

    -- Optional script/query that implements the edge.
    process_reference TEXT,

    -- Lineage meaning.
    lineage_level TEXT NOT NULL DEFAULT 'DATASET'
        CHECK (
            lineage_level IN (
                'DATASET',
                'ROW',
                'COLUMN'
            )
        ),

    -- Optional linkage to one concrete pipeline execution.
    -- Dataset lineage can exist without a run_id; execution lineage can
    -- populate this later.
    run_id TEXT,

    is_active INTEGER NOT NULL DEFAULT 1
        CHECK (is_active IN (0, 1)),

    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (upstream_asset_id)
        REFERENCES data_assets(asset_id),

    FOREIGN KEY (downstream_asset_id)
        REFERENCES data_assets(asset_id),

    CHECK (upstream_asset_id <> downstream_asset_id),

    UNIQUE (
        upstream_asset_id,
        downstream_asset_id,
        transformation_name,
        lineage_level
    )
);

CREATE INDEX IF NOT EXISTS idx_lineage_edges_upstream
    ON lineage_edges (upstream_asset_id);

CREATE INDEX IF NOT EXISTS idx_lineage_edges_downstream
    ON lineage_edges (downstream_asset_id);

CREATE INDEX IF NOT EXISTS idx_lineage_edges_run_id
    ON lineage_edges (run_id);

CREATE INDEX IF NOT EXISTS idx_lineage_edges_type
    ON lineage_edges (transformation_type);

CREATE INDEX IF NOT EXISTS idx_lineage_edges_active
    ON lineage_edges (is_active);

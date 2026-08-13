PRAGMA foreign_keys = ON;

-- Governance / Lineage
-- Step G4A: Run-linked lineage execution history.
--
-- Dataset lineage stays in lineage_edges as the static dependency graph.
-- This table records which lineage edges participated in a concrete pipeline run.

CREATE TABLE IF NOT EXISTS lineage_run_events (
    lineage_run_event_id INTEGER PRIMARY KEY AUTOINCREMENT,

    lineage_edge_id INTEGER NOT NULL,
    run_id TEXT NOT NULL,

    execution_status TEXT NOT NULL
        CHECK (
            execution_status IN (
                'SUCCESS',
                'FAILED',
                'SKIPPED'
            )
        ),

    step_name TEXT,

    attempt_number INTEGER
        CHECK (
            attempt_number IS NULL
            OR attempt_number > 0
        ),

    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (lineage_edge_id)
        REFERENCES lineage_edges(lineage_edge_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_lineage_run_events_identity
    ON lineage_run_events (
        lineage_edge_id,
        run_id,
        IFNULL(step_name, ''),
        IFNULL(attempt_number, 0)
    );

CREATE INDEX IF NOT EXISTS idx_lineage_run_events_run_id
    ON lineage_run_events (run_id);

CREATE INDEX IF NOT EXISTS idx_lineage_run_events_edge
    ON lineage_run_events (lineage_edge_id);

CREATE INDEX IF NOT EXISTS idx_lineage_run_events_status
    ON lineage_run_events (execution_status);

CREATE INDEX IF NOT EXISTS idx_lineage_run_events_step
    ON lineage_run_events (step_name);

PRAGMA foreign_keys = ON;

-- ============================================================
-- Governance / Lineage
-- Step G5: Query-friendly Governance Views
-- ============================================================

DROP VIEW IF EXISTS vw_asset_downstream_dependencies;
DROP VIEW IF EXISTS vw_asset_upstream_dependencies;
DROP VIEW IF EXISTS vw_lineage_run_history;
DROP VIEW IF EXISTS vw_data_lineage;


-- ------------------------------------------------------------
-- 1) Static dataset lineage
--    One row per active lineage edge.
-- ------------------------------------------------------------
CREATE VIEW vw_data_lineage AS
SELECT
    e.lineage_edge_id,

    u.asset_id AS upstream_asset_id,
    u.asset_key AS upstream_asset_key,
    u.asset_name AS upstream_asset_name,
    u.asset_type AS upstream_asset_type,
    u.data_layer AS upstream_data_layer,
    u.data_domain AS upstream_data_domain,
    u.classification AS upstream_classification,
    u.contains_pii AS upstream_contains_pii,

    d.asset_id AS downstream_asset_id,
    d.asset_key AS downstream_asset_key,
    d.asset_name AS downstream_asset_name,
    d.asset_type AS downstream_asset_type,
    d.data_layer AS downstream_data_layer,
    d.data_domain AS downstream_data_domain,
    d.classification AS downstream_classification,
    d.contains_pii AS downstream_contains_pii,

    e.transformation_name,
    e.transformation_type,
    e.process_reference,
    e.lineage_level,
    e.is_active,
    e.created_at,
    e.updated_at

FROM lineage_edges AS e
INNER JOIN data_assets AS u
    ON u.asset_id = e.upstream_asset_id
INNER JOIN data_assets AS d
    ON d.asset_id = e.downstream_asset_id
WHERE e.is_active = 1;


-- ------------------------------------------------------------
-- 2) Runtime lineage history
--    Which lineage edge actually participated in each run.
-- ------------------------------------------------------------
CREATE VIEW vw_lineage_run_history AS
SELECT
    r.lineage_run_event_id,
    r.run_id,
    r.step_name,
    r.attempt_number,
    r.execution_status,
    r.recorded_at,

    e.lineage_edge_id,
    e.transformation_name,
    e.transformation_type,
    e.process_reference,
    e.lineage_level,

    u.asset_id AS upstream_asset_id,
    u.asset_key AS upstream_asset_key,
    u.asset_name AS upstream_asset_name,
    u.data_layer AS upstream_data_layer,
    u.classification AS upstream_classification,
    u.contains_pii AS upstream_contains_pii,

    d.asset_id AS downstream_asset_id,
    d.asset_key AS downstream_asset_key,
    d.asset_name AS downstream_asset_name,
    d.data_layer AS downstream_data_layer,
    d.classification AS downstream_classification,
    d.contains_pii AS downstream_contains_pii

FROM lineage_run_events AS r
INNER JOIN lineage_edges AS e
    ON e.lineage_edge_id = r.lineage_edge_id
INNER JOIN data_assets AS u
    ON u.asset_id = e.upstream_asset_id
INNER JOIN data_assets AS d
    ON d.asset_id = e.downstream_asset_id;


-- ------------------------------------------------------------
-- 3) Recursive upstream dependency view
--
-- Example:
--   root_asset_name = 'orders'
--
-- returns:
--   stg_orders
--   orders.csv
--
-- depth = 1 means direct dependency.
-- depth > 1 means transitive dependency.
-- ------------------------------------------------------------
CREATE VIEW vw_asset_upstream_dependencies AS
WITH RECURSIVE upstream_tree (
    root_asset_id,
    root_asset_key,
    root_asset_name,
    dependency_asset_id,
    dependency_asset_key,
    dependency_asset_name,
    dependency_data_layer,
    dependency_classification,
    dependency_contains_pii,
    depth,
    lineage_path,
    visited_asset_ids
) AS (

    SELECT
        root.asset_id,
        root.asset_key,
        root.asset_name,

        upstream.asset_id,
        upstream.asset_key,
        upstream.asset_name,
        upstream.data_layer,
        upstream.classification,
        upstream.contains_pii,

        1 AS depth,

        root.asset_name || ' <- ' || upstream.asset_name
            AS lineage_path,

        '|' || root.asset_id || '|' || upstream.asset_id || '|'
            AS visited_asset_ids

    FROM data_assets AS root
    INNER JOIN lineage_edges AS e
        ON e.downstream_asset_id = root.asset_id
       AND e.is_active = 1
       AND e.lineage_level = 'DATASET'
    INNER JOIN data_assets AS upstream
        ON upstream.asset_id = e.upstream_asset_id

    UNION ALL

    SELECT
        tree.root_asset_id,
        tree.root_asset_key,
        tree.root_asset_name,

        upstream.asset_id,
        upstream.asset_key,
        upstream.asset_name,
        upstream.data_layer,
        upstream.classification,
        upstream.contains_pii,

        tree.depth + 1,

        tree.lineage_path || ' <- ' || upstream.asset_name,

        tree.visited_asset_ids || upstream.asset_id || '|'

    FROM upstream_tree AS tree
    INNER JOIN lineage_edges AS e
        ON e.downstream_asset_id = tree.dependency_asset_id
       AND e.is_active = 1
       AND e.lineage_level = 'DATASET'
    INNER JOIN data_assets AS upstream
        ON upstream.asset_id = e.upstream_asset_id

    WHERE
        instr(
            tree.visited_asset_ids,
            '|' || upstream.asset_id || '|'
        ) = 0
)
SELECT
    root_asset_id,
    root_asset_key,
    root_asset_name,
    dependency_asset_id,
    dependency_asset_key,
    dependency_asset_name,
    dependency_data_layer,
    dependency_classification,
    dependency_contains_pii,
    depth,
    lineage_path
FROM upstream_tree;


-- ------------------------------------------------------------
-- 4) Recursive downstream dependency view
--
-- Example:
--   root_asset_name = 'orders'
--
-- returns assets that depend directly or indirectly on orders.
-- ------------------------------------------------------------
CREATE VIEW vw_asset_downstream_dependencies AS
WITH RECURSIVE downstream_tree (
    root_asset_id,
    root_asset_key,
    root_asset_name,
    dependency_asset_id,
    dependency_asset_key,
    dependency_asset_name,
    dependency_data_layer,
    dependency_classification,
    dependency_contains_pii,
    depth,
    lineage_path,
    visited_asset_ids
) AS (

    SELECT
        root.asset_id,
        root.asset_key,
        root.asset_name,

        downstream.asset_id,
        downstream.asset_key,
        downstream.asset_name,
        downstream.data_layer,
        downstream.classification,
        downstream.contains_pii,

        1 AS depth,

        root.asset_name || ' -> ' || downstream.asset_name
            AS lineage_path,

        '|' || root.asset_id || '|' || downstream.asset_id || '|'
            AS visited_asset_ids

    FROM data_assets AS root
    INNER JOIN lineage_edges AS e
        ON e.upstream_asset_id = root.asset_id
       AND e.is_active = 1
       AND e.lineage_level = 'DATASET'
    INNER JOIN data_assets AS downstream
        ON downstream.asset_id = e.downstream_asset_id

    UNION ALL

    SELECT
        tree.root_asset_id,
        tree.root_asset_key,
        tree.root_asset_name,

        downstream.asset_id,
        downstream.asset_key,
        downstream.asset_name,
        downstream.data_layer,
        downstream.classification,
        downstream.contains_pii,

        tree.depth + 1,

        tree.lineage_path || ' -> ' || downstream.asset_name,

        tree.visited_asset_ids || downstream.asset_id || '|'

    FROM downstream_tree AS tree
    INNER JOIN lineage_edges AS e
        ON e.upstream_asset_id = tree.dependency_asset_id
       AND e.is_active = 1
       AND e.lineage_level = 'DATASET'
    INNER JOIN data_assets AS downstream
        ON downstream.asset_id = e.downstream_asset_id

    WHERE
        instr(
            tree.visited_asset_ids,
            '|' || downstream.asset_id || '|'
        ) = 0
)
SELECT
    root_asset_id,
    root_asset_key,
    root_asset_name,
    dependency_asset_id,
    dependency_asset_key,
    dependency_asset_name,
    dependency_data_layer,
    dependency_classification,
    dependency_contains_pii,
    depth,
    lineage_path
FROM downstream_tree;

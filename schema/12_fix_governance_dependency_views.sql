PRAGMA foreign_keys = ON;

-- ============================================================
-- Governance / Lineage
-- Step G5B: De-duplicate recursive dependency views.
--
-- Why:
-- The same asset pair can legitimately have more than one lineage edge
-- (for example CLEANING and INCREMENTAL_LOAD from stg_orders -> orders).
-- Dependency traversal is asset-to-asset, so those parallel process edges
-- must collapse to one dependency relationship.
-- ============================================================

DROP VIEW IF EXISTS vw_asset_downstream_dependencies;
DROP VIEW IF EXISTS vw_asset_upstream_dependencies;


CREATE VIEW vw_asset_upstream_dependencies AS
WITH RECURSIVE

active_asset_dependencies AS (
    SELECT DISTINCT
        upstream_asset_id,
        downstream_asset_id
    FROM lineage_edges
    WHERE
        is_active = 1
        AND lineage_level = 'DATASET'
),

upstream_tree (
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

        1,

        root.asset_name || ' <- ' || upstream.asset_name,

        '|' || root.asset_id || '|' || upstream.asset_id || '|'

    FROM data_assets AS root
    INNER JOIN active_asset_dependencies AS dep
        ON dep.downstream_asset_id = root.asset_id
    INNER JOIN data_assets AS upstream
        ON upstream.asset_id = dep.upstream_asset_id

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
    INNER JOIN active_asset_dependencies AS dep
        ON dep.downstream_asset_id = tree.dependency_asset_id
    INNER JOIN data_assets AS upstream
        ON upstream.asset_id = dep.upstream_asset_id

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


CREATE VIEW vw_asset_downstream_dependencies AS
WITH RECURSIVE

active_asset_dependencies AS (
    SELECT DISTINCT
        upstream_asset_id,
        downstream_asset_id
    FROM lineage_edges
    WHERE
        is_active = 1
        AND lineage_level = 'DATASET'
),

downstream_tree (
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

        1,

        root.asset_name || ' -> ' || downstream.asset_name,

        '|' || root.asset_id || '|' || downstream.asset_id || '|'

    FROM data_assets AS root
    INNER JOIN active_asset_dependencies AS dep
        ON dep.upstream_asset_id = root.asset_id
    INNER JOIN data_assets AS downstream
        ON downstream.asset_id = dep.downstream_asset_id

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
    INNER JOIN active_asset_dependencies AS dep
        ON dep.upstream_asset_id = tree.dependency_asset_id
    INNER JOIN data_assets AS downstream
        ON downstream.asset_id = dep.downstream_asset_id

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

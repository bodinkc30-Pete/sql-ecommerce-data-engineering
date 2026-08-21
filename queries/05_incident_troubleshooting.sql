-- ============================================================
-- Incident Troubleshooting / RCA Evidence Pack
-- SQL E-commerce Data Engineering
--
-- Purpose
--   Read-only evidence pack for investigating the latest failed or
--   incomplete pipeline run.
--
-- Design rules
--   - Never guess root cause.
--   - Prefer orchestrator telemetry when it exists.
--   - Fall back to pipeline_audit for standalone sub-pipeline runs.
--   - Never claim an unlinked later run is a recovery.
--   - Treat NULL rejected_source_records.run_id as unlinked evidence.
--   - Treat pipeline_watermark as current state only.
--
-- SQLite compatible and SELECT-only.
-- ============================================================


-- ============================================================
-- 1. Recent run inventory
-- One row per run_id across all pipeline components.
-- ============================================================

WITH run_rollup AS (
    SELECT
        run_id,
        GROUP_CONCAT(DISTINCT pipeline_name) AS pipeline_components,
        MAX(run_type) AS run_type,
        MAX(recovery_of_run_id) AS recovery_of_run_id,
        MIN(started_at) AS pipeline_started_at,
        MAX(completed_at) AS pipeline_completed_at,
        COUNT(*) AS audit_rows,
        SUM(
            CASE WHEN run_status = 'SUCCESS' THEN 1 ELSE 0 END
        ) AS successful_audit_rows,
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) AS failed_audit_rows,
        SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) AS running_audit_rows,
        COALESCE(SUM(rows_processed), 0) AS rows_processed,
        COALESCE(SUM(rows_rejected), 0) AS rows_rejected
    FROM pipeline_audit
    GROUP BY run_id
)
SELECT
    run_id,
    pipeline_components,
    run_type,
    recovery_of_run_id,
    pipeline_started_at,
    pipeline_completed_at,
    audit_rows,
    failed_audit_rows,
    running_audit_rows,
    rows_processed,
    rows_rejected,
    CASE
        WHEN failed_audit_rows > 0 THEN 'FAILED'
        WHEN running_audit_rows > 0 THEN 'RUNNING'
        WHEN successful_audit_rows = audit_rows THEN 'SUCCESS'
        ELSE 'INCOMPLETE'
    END AS derived_pipeline_status
FROM run_rollup
ORDER BY pipeline_started_at DESC
LIMIT 20;


-- ============================================================
-- 2. Latest incident summary
-- ============================================================

WITH run_rollup AS (
    SELECT
        run_id,
        GROUP_CONCAT(DISTINCT pipeline_name) AS pipeline_components,
        MAX(run_type) AS run_type,
        MAX(recovery_of_run_id) AS recovery_of_run_id,
        MIN(started_at) AS pipeline_started_at,
        MAX(completed_at) AS pipeline_completed_at,
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) AS failed_audit_rows,
        SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) AS running_audit_rows,
        COALESCE(SUM(rows_processed), 0) AS rows_processed,
        COALESCE(SUM(rows_rejected), 0) AS rows_rejected
    FROM pipeline_audit
    GROUP BY run_id
),
latest_incident AS (
    SELECT *
    FROM run_rollup
    WHERE
        failed_audit_rows > 0
        OR running_audit_rows > 0
    ORDER BY pipeline_started_at DESC
    LIMIT 1
)
SELECT
    run_id AS incident_run_id,
    pipeline_components,
    run_type,
    recovery_of_run_id,
    pipeline_started_at,
    pipeline_completed_at,
    failed_audit_rows,
    running_audit_rows,
    rows_processed,
    rows_rejected
FROM latest_incident;


-- ============================================================
-- 3. Step evidence with instrumentation fallback
--
-- ORCHESTRATOR_STEP_LOG
--   Attempt-level telemetry exists for the run.
--
-- PIPELINE_AUDIT_FALLBACK
--   The run was executed as a standalone sub-pipeline and no
--   orchestrator step telemetry exists for that run_id.
-- ============================================================

WITH latest_incident AS (
    SELECT run_id
    FROM pipeline_audit
    GROUP BY run_id
    HAVING
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) > 0
        OR SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) > 0
    ORDER BY MIN(started_at) DESC
    LIMIT 1
),
step_log_rows AS (
    SELECT
        psl.step_number AS evidence_order,
        psl.step_name,
        psl.script_name,
        psl.attempt_number,
        psl.status,
        psl.start_time,
        psl.end_time,
        psl.duration_seconds,
        psl.rows_read AS rows_processed_or_read,
        psl.rows_written,
        psl.rows_rejected,
        psl.error_type,
        psl.error_message,
        psl.sla_threshold_seconds,
        psl.sla_status,
        'ORCHESTRATOR_STEP_LOG' AS evidence_source
    FROM pipeline_step_log AS psl
    WHERE psl.run_id = (
        SELECT run_id FROM latest_incident
    )
),
audit_fallback_rows AS (
    SELECT
        pa.audit_id AS evidence_order,
        pa.step_name,
        NULL AS script_name,
        NULL AS attempt_number,
        pa.run_status AS status,
        pa.started_at AS start_time,
        pa.completed_at AS end_time,
        ROUND(
            (
                JULIANDAY(pa.completed_at)
                - JULIANDAY(pa.started_at)
            ) * 86400,
            3
        ) AS duration_seconds,
        pa.rows_processed AS rows_processed_or_read,
        COALESCE(pa.rows_inserted, 0)
            + COALESCE(pa.rows_updated, 0) AS rows_written,
        pa.rows_rejected,
        NULL AS error_type,
        pa.error_message,
        NULL AS sla_threshold_seconds,
        'NO_ORCHESTRATOR_STEP_SLA' AS sla_status,
        'PIPELINE_AUDIT_FALLBACK' AS evidence_source
    FROM pipeline_audit AS pa
    WHERE
        pa.run_id = (
            SELECT run_id FROM latest_incident
        )
        AND NOT EXISTS (
            SELECT 1
            FROM step_log_rows
        )
)
SELECT *
FROM step_log_rows

UNION ALL

SELECT *
FROM audit_fallback_rows

ORDER BY
    evidence_order,
    attempt_number;


-- ============================================================
-- 4. Execution SLA evidence with coverage status
-- ============================================================

WITH latest_incident AS (
    SELECT run_id
    FROM pipeline_audit
    GROUP BY run_id
    HAVING
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) > 0
        OR SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) > 0
    ORDER BY MIN(started_at) DESC
    LIMIT 1
),
sla_rows AS (
    SELECT
        psm.step_name,
        psm.attempt_number,
        psm.step_run_status,
        psm.duration_seconds,
        psm.sla_threshold_seconds,
        psm.sla_status,
        psm.measured_at,
        'ORCHESTRATOR_SLA_METRIC' AS evidence_source
    FROM pipeline_sla_metrics AS psm
    WHERE psm.run_id = (
        SELECT run_id FROM latest_incident
    )
),
fallback_row AS (
    SELECT
        NULL AS step_name,
        NULL AS attempt_number,
        NULL AS step_run_status,
        NULL AS duration_seconds,
        NULL AS sla_threshold_seconds,
        'NO_ORCHESTRATOR_SLA_TELEMETRY' AS sla_status,
        NULL AS measured_at,
        'PIPELINE_AUDIT_ONLY_RUN' AS evidence_source
    WHERE NOT EXISTS (
        SELECT 1 FROM sla_rows
    )
)
SELECT *
FROM sla_rows

UNION ALL

SELECT *
FROM fallback_row

ORDER BY
    measured_at,
    step_name,
    attempt_number;


-- ============================================================
-- 5. Rejected-source evidence
--
-- DIRECT_RUN_ID means durable linkage exists.
-- TIME_WINDOW_UNLINKED means temporal proximity only.
-- ============================================================

WITH incident_window AS (
    SELECT
        run_id,
        MIN(started_at) AS incident_started_at,
        COALESCE(
            MAX(completed_at),
            CURRENT_TIMESTAMP
        ) AS incident_completed_at
    FROM pipeline_audit
    GROUP BY run_id
    HAVING
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) > 0
        OR SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) > 0
    ORDER BY incident_started_at DESC
    LIMIT 1
)
SELECT
    rejection_id,
    run_id,
    dataset_name,
    source_file,
    source_row_number,
    rejected_column,
    rejected_value,
    rejection_type,
    rejection_reason,
    rejected_at,
    CASE
        WHEN run_id = (
            SELECT run_id FROM incident_window
        )
            THEN 'DIRECT_RUN_ID'
        WHEN run_id IS NULL
            THEN 'TIME_WINDOW_UNLINKED'
        ELSE 'OTHER'
    END AS evidence_linkage
FROM rejected_source_records
WHERE
    run_id = (
        SELECT run_id FROM incident_window
    )
    OR (
        run_id IS NULL
        AND datetime(rejected_at) BETWEEN
            datetime(
                (
                    SELECT incident_started_at
                    FROM incident_window
                ),
                '-5 minutes'
            )
            AND
            datetime(
                (
                    SELECT incident_completed_at
                    FROM incident_window
                ),
                '+5 minutes'
            )
    )
ORDER BY
    rejected_at,
    rejection_id;


-- ============================================================
-- 6. Runtime lineage evidence with coverage status
-- ============================================================

WITH latest_incident AS (
    SELECT run_id
    FROM pipeline_audit
    GROUP BY run_id
    HAVING
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) > 0
        OR SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) > 0
    ORDER BY MIN(started_at) DESC
    LIMIT 1
),
runtime_lineage AS (
    SELECT
        lre.lineage_run_event_id,
        lre.lineage_edge_id,
        le.upstream_asset_id,
        upstream.asset_name AS upstream_asset_name,
        le.downstream_asset_id,
        downstream.asset_name AS downstream_asset_name,
        le.transformation_type,
        lre.step_name,
        lre.attempt_number,
        lre.execution_status,
        lre.recorded_at,
        'RUNTIME_LINEAGE_EVENT' AS evidence_source
    FROM lineage_run_events AS lre
    INNER JOIN lineage_edges AS le
        ON le.lineage_edge_id = lre.lineage_edge_id
    LEFT JOIN data_assets AS upstream
        ON upstream.asset_id = le.upstream_asset_id
    LEFT JOIN data_assets AS downstream
        ON downstream.asset_id = le.downstream_asset_id
    WHERE lre.run_id = (
        SELECT run_id FROM latest_incident
    )
),
coverage_fallback AS (
    SELECT
        NULL AS lineage_run_event_id,
        NULL AS lineage_edge_id,
        NULL AS upstream_asset_id,
        NULL AS upstream_asset_name,
        NULL AS downstream_asset_id,
        NULL AS downstream_asset_name,
        NULL AS transformation_type,
        NULL AS step_name,
        NULL AS attempt_number,
        'NO_RUNTIME_LINEAGE_FOR_RUN' AS execution_status,
        NULL AS recorded_at,
        'PIPELINE_AUDIT_ONLY_RUN' AS evidence_source
    WHERE NOT EXISTS (
        SELECT 1 FROM runtime_lineage
    )
)
SELECT *
FROM runtime_lineage

UNION ALL

SELECT *
FROM coverage_fallback

ORDER BY
    recorded_at,
    lineage_run_event_id;


-- ============================================================
-- 7. Failure to recovery evidence
--
-- DECLARED_RECOVERY
--   recovery_of_run_id explicitly points to the incident.
--
-- POSSIBLE_RECOVERY_NOT_LINKED
--   A later run within 24 hours shows every failed incident step
--   as SUCCESS, but recovery_of_run_id does not link it.
--   This is a candidate only and must not be treated as proof.
-- ============================================================

WITH latest_incident AS (
    SELECT
        run_id,
        MIN(started_at) AS incident_started_at
    FROM pipeline_audit
    GROUP BY run_id
    HAVING
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) > 0
        OR SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) > 0
    ORDER BY incident_started_at DESC
    LIMIT 1
),
failed_steps AS (
    SELECT DISTINCT
        pa.pipeline_name,
        pa.step_name
    FROM pipeline_audit AS pa
    WHERE
        pa.run_id = (
            SELECT run_id FROM latest_incident
        )
        AND pa.run_status = 'FAILED'
),
run_rollup AS (
    SELECT
        run_id,
        MAX(run_type) AS run_type,
        MAX(recovery_of_run_id) AS recovery_of_run_id,
        MIN(started_at) AS started_at,
        MAX(completed_at) AS completed_at,
        COUNT(*) AS audit_rows,
        SUM(
            CASE WHEN run_status = 'SUCCESS' THEN 1 ELSE 0 END
        ) AS success_rows,
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) AS failed_rows,
        SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) AS running_rows
    FROM pipeline_audit
    GROUP BY run_id
),
declared_recovery AS (
    SELECT
        rr.run_id AS recovery_run_id,
        rr.run_type AS recovery_run_type,
        rr.started_at AS recovery_started_at,
        rr.completed_at AS recovery_completed_at,
        CASE
            WHEN rr.failed_rows > 0 THEN 'FAILED'
            WHEN rr.running_rows > 0 THEN 'RUNNING'
            WHEN rr.success_rows = rr.audit_rows THEN 'SUCCESS'
            ELSE 'INCOMPLETE'
        END AS recovery_status,
        'DECLARED_RECOVERY' AS linkage_type
    FROM run_rollup AS rr
    WHERE rr.recovery_of_run_id = (
        SELECT run_id FROM latest_incident
    )
),
possible_recovery AS (
    SELECT
        rr.run_id AS recovery_run_id,
        rr.run_type AS recovery_run_type,
        rr.started_at AS recovery_started_at,
        rr.completed_at AS recovery_completed_at,
        CASE
            WHEN rr.failed_rows > 0 THEN 'FAILED'
            WHEN rr.running_rows > 0 THEN 'RUNNING'
            WHEN rr.success_rows = rr.audit_rows THEN 'SUCCESS'
            ELSE 'INCOMPLETE'
        END AS recovery_status,
        'POSSIBLE_RECOVERY_NOT_LINKED' AS linkage_type
    FROM run_rollup AS rr
    WHERE
        rr.run_id <> (
            SELECT run_id FROM latest_incident
        )
        AND rr.recovery_of_run_id IS NULL
        AND datetime(rr.started_at) > datetime(
            (
                SELECT incident_started_at
                FROM latest_incident
            )
        )
        AND datetime(rr.started_at) <= datetime(
            (
                SELECT incident_started_at
                FROM latest_incident
            ),
            '+24 hours'
        )
        AND (
            SELECT COUNT(*)
            FROM failed_steps
        ) > 0
        AND (
            SELECT COUNT(*)
            FROM failed_steps AS fs
            WHERE EXISTS (
                SELECT 1
                FROM pipeline_audit AS candidate
                WHERE
                    candidate.run_id = rr.run_id
                    AND candidate.pipeline_name = fs.pipeline_name
                    AND candidate.step_name = fs.step_name
                    AND candidate.run_status = 'SUCCESS'
            )
        ) = (
            SELECT COUNT(*)
            FROM failed_steps
        )
        AND NOT EXISTS (
            SELECT 1
            FROM declared_recovery
            WHERE recovery_run_id = rr.run_id
        )
)
SELECT
    (
        SELECT run_id
        FROM latest_incident
    ) AS incident_run_id,
    recovery_run_id,
    recovery_run_type,
    recovery_started_at,
    recovery_completed_at,
    recovery_status,
    linkage_type
FROM declared_recovery

UNION ALL

SELECT
    (
        SELECT run_id
        FROM latest_incident
    ) AS incident_run_id,
    recovery_run_id,
    recovery_run_type,
    recovery_started_at,
    recovery_completed_at,
    recovery_status,
    linkage_type
FROM possible_recovery

ORDER BY
    recovery_started_at;


-- ============================================================
-- 8. Quality and reconciliation evidence for the incident and
-- candidate recovery runs.
--
-- Candidate runs remain explicitly unlinked. This section only
-- compares observable quality evidence.
-- ============================================================

WITH latest_incident AS (
    SELECT
        run_id,
        MIN(started_at) AS incident_started_at
    FROM pipeline_audit
    GROUP BY run_id
    HAVING
        SUM(
            CASE WHEN run_status = 'FAILED' THEN 1 ELSE 0 END
        ) > 0
        OR SUM(
            CASE WHEN run_status = 'RUNNING' THEN 1 ELSE 0 END
        ) > 0
    ORDER BY incident_started_at DESC
    LIMIT 1
),
failed_steps AS (
    SELECT DISTINCT
        pipeline_name,
        step_name
    FROM pipeline_audit
    WHERE
        run_id = (
            SELECT run_id FROM latest_incident
        )
        AND run_status = 'FAILED'
),
candidate_runs AS (
    SELECT DISTINCT
        pa.run_id
    FROM pipeline_audit AS pa
    WHERE
        pa.run_id <> (
            SELECT run_id FROM latest_incident
        )
        AND datetime(pa.started_at) > datetime(
            (
                SELECT incident_started_at
                FROM latest_incident
            )
        )
        AND datetime(pa.started_at) <= datetime(
            (
                SELECT incident_started_at
                FROM latest_incident
            ),
            '+24 hours'
        )
        AND (
            SELECT COUNT(*)
            FROM failed_steps
        ) > 0
        AND (
            SELECT COUNT(*)
            FROM failed_steps AS fs
            WHERE EXISTS (
                SELECT 1
                FROM pipeline_audit AS candidate
                WHERE
                    candidate.run_id = pa.run_id
                    AND candidate.pipeline_name = fs.pipeline_name
                    AND candidate.step_name = fs.step_name
                    AND candidate.run_status = 'SUCCESS'
            )
        ) = (
            SELECT COUNT(*)
            FROM failed_steps
        )
),
related_runs AS (
    SELECT
        run_id,
        'INCIDENT' AS relation
    FROM latest_incident

    UNION ALL

    SELECT
        run_id,
        'POSSIBLE_RECOVERY_NOT_LINKED' AS relation
    FROM candidate_runs
)
SELECT
    rr.relation,
    pa.run_id,
    pa.pipeline_name,
    pa.step_name,
    pa.run_status,
    pa.rows_processed,
    pa.rows_rejected,
    pa.error_message,
    pa.started_at,
    pa.completed_at
FROM pipeline_audit AS pa
INNER JOIN related_runs AS rr
    ON rr.run_id = pa.run_id
WHERE
    pa.pipeline_name = 'ecommerce_quality_check_pipeline'
    OR UPPER(pa.step_name) LIKE '%RECONCILIATION%'
    OR UPPER(pa.step_name) LIKE '%FRESHNESS%'
    OR UPPER(pa.step_name) LIKE '%PIPELINE_TOTAL%'
ORDER BY
    pa.started_at,
    pa.audit_id;


-- ============================================================
-- 9. Current freshness and watermark state
--
-- This is current state only, not a historical incident snapshot.
-- ============================================================

SELECT
    table_name,
    last_loaded_at,
    updated_at,
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(last_loaded_at)
        ) * 24,
        2
    ) AS hours_since_last_load
FROM pipeline_watermark
ORDER BY table_name;

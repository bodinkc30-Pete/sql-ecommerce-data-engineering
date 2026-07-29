SELECT
    run_id,
    pipeline_name,
    MIN(started_at) AS pipeline_started_at,
    MAX(completed_at) AS pipeline_completed_at,
    ROUND(
        (
            JULIANDAY(MAX(completed_at))
            - JULIANDAY(MIN(started_at))
        ) * 86400,
        2
    ) AS duration_seconds,
    COUNT(*) AS total_steps,
    SUM(
        CASE
            WHEN run_status = 'SUCCESS' THEN 1
            ELSE 0
        END
    ) AS successful_steps,
    SUM(
        CASE
            WHEN run_status = 'FAILED' THEN 1
            ELSE 0
        END
    ) AS failed_steps,
    SUM(
        CASE
            WHEN run_status = 'RUNNING' THEN 1
            ELSE 0
        END
    ) AS running_steps,
    COALESCE(SUM(rows_processed), 0) AS total_rows_processed,
    COALESCE(SUM(rows_inserted), 0) AS total_rows_inserted,
    COALESCE(SUM(rows_updated), 0) AS total_rows_updated,
    COALESCE(SUM(rows_rejected), 0) AS total_rows_rejected,
    CASE
        WHEN SUM(
            CASE
                WHEN run_status = 'FAILED' THEN 1
                ELSE 0
            END
        ) > 0
            THEN 'FAILED'
        WHEN SUM(
            CASE
                WHEN run_status = 'RUNNING' THEN 1
                ELSE 0
            END
        ) > 0
            THEN 'RUNNING'
        WHEN COUNT(*) = SUM(
            CASE
                WHEN run_status = 'SUCCESS' THEN 1
                ELSE 0
            END
        )
            THEN 'SUCCESS'
        ELSE 'INCOMPLETE'
    END AS pipeline_status
FROM pipeline_audit
GROUP BY
    run_id,
    pipeline_name
ORDER BY
    pipeline_started_at DESC;


SELECT
    audit_id,
    run_id,
    pipeline_name,
    step_name,
    run_status,
    rows_processed,
    rows_inserted,
    rows_updated,
    rows_rejected,
    error_message,
    started_at,
    completed_at,
    ROUND(
        (
            JULIANDAY(completed_at)
            - JULIANDAY(started_at)
        ) * 86400,
        2
    ) AS step_duration_seconds
FROM pipeline_audit
ORDER BY
    started_at DESC,
    audit_id DESC;


SELECT
    run_id,
    pipeline_name,
    step_name,
    run_status,
    error_message,
    started_at,
    completed_at
FROM pipeline_audit
WHERE run_status = 'FAILED'
ORDER BY
    started_at DESC;


SELECT
    run_id,
    pipeline_name,
    step_name,
    started_at,
    ROUND(
        (
            JULIANDAY('now')
            - JULIANDAY(started_at)
        ) * 1440,
        2
    ) AS running_minutes
FROM pipeline_audit
WHERE
    run_status = 'RUNNING'
    AND completed_at IS NULL
ORDER BY
    started_at;


SELECT
    run_id,
    pipeline_name,
    SUM(rows_processed) AS rows_processed,
    SUM(rows_rejected) AS rows_rejected,
    ROUND(
        100.0 * SUM(rows_rejected)
        / NULLIF(SUM(rows_processed), 0),
        2
    ) AS rejection_rate_percent
FROM pipeline_audit
GROUP BY
    run_id,
    pipeline_name
HAVING SUM(rows_rejected) > 0
ORDER BY
    rejection_rate_percent DESC,
    run_id DESC;
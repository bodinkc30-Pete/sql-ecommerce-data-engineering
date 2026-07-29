SELECT
    pipeline_name,
    COUNT(DISTINCT run_id) AS total_runs,
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
    COALESCE(SUM(rows_processed), 0) AS total_rows_processed,
    COALESCE(SUM(rows_inserted), 0) AS total_rows_inserted,
    COALESCE(SUM(rows_updated), 0) AS total_rows_updated,
    COALESCE(SUM(rows_rejected), 0) AS total_rows_rejected
FROM pipeline_audit
GROUP BY
    pipeline_name
ORDER BY
    total_runs DESC;


SELECT
    run_id,
    pipeline_name,
    SUM(rows_processed) AS rows_processed,
    SUM(rows_inserted) AS rows_inserted,
    SUM(rows_updated) AS rows_updated,
    SUM(rows_rejected) AS rows_rejected,
    ROUND(
        100.0 * SUM(rows_inserted)
        / NULLIF(SUM(rows_processed), 0),
        2
    ) AS insert_rate_percent,
    ROUND(
        100.0 * SUM(rows_updated)
        / NULLIF(SUM(rows_processed), 0),
        2
    ) AS update_rate_percent,
    ROUND(
        100.0 * SUM(rows_rejected)
        / NULLIF(SUM(rows_processed), 0),
        2
    ) AS rejection_rate_percent
FROM pipeline_audit
GROUP BY
    run_id,
    pipeline_name
ORDER BY
    run_id DESC;


SELECT
    step_name,
    COUNT(*) AS total_executions,
    SUM(
        CASE
            WHEN run_status = 'SUCCESS' THEN 1
            ELSE 0
        END
    ) AS successful_executions,
    SUM(
        CASE
            WHEN run_status = 'FAILED' THEN 1
            ELSE 0
        END
    ) AS failed_executions,
    ROUND(
        100.0 * SUM(
            CASE
                WHEN run_status = 'SUCCESS' THEN 1
                ELSE 0
            END
        ) / NULLIF(COUNT(*), 0),
        2
    ) AS success_rate_percent,
    ROUND(
        AVG(
            (
                JULIANDAY(completed_at)
                - JULIANDAY(started_at)
            ) * 86400
        ),
        2
    ) AS average_duration_seconds
FROM pipeline_audit
WHERE completed_at IS NOT NULL
GROUP BY
    step_name
ORDER BY
    success_rate_percent ASC,
    average_duration_seconds DESC;


SELECT
    run_id,
    pipeline_name,
    step_name,
    rows_processed,
    rows_inserted,
    rows_updated,
    rows_rejected,
    ROUND(
        (
            JULIANDAY(completed_at)
            - JULIANDAY(started_at)
        ) * 86400,
        2
    ) AS duration_seconds,
    ROUND(
        rows_processed
        / NULLIF(
            (
                JULIANDAY(completed_at)
                - JULIANDAY(started_at)
            ) * 86400,
            0
        ),
        2
    ) AS rows_per_second
FROM pipeline_audit
WHERE
    completed_at IS NOT NULL
    AND rows_processed > 0
ORDER BY
    rows_per_second DESC;


SELECT
    run_id,
    pipeline_name,
    step_name,
    rows_processed,
    rows_rejected,
    ROUND(
        100.0 * rows_rejected
        / NULLIF(rows_processed, 0),
        2
    ) AS rejection_rate_percent,
    error_message,
    started_at
FROM pipeline_audit
WHERE
    rows_rejected > 0
    OR run_status = 'FAILED'
ORDER BY
    started_at DESC;


SELECT
    DATE(started_at) AS run_date,
    COUNT(DISTINCT run_id) AS total_runs,
    COALESCE(SUM(rows_processed), 0) AS rows_processed,
    COALESCE(SUM(rows_inserted), 0) AS rows_inserted,
    COALESCE(SUM(rows_updated), 0) AS rows_updated,
    COALESCE(SUM(rows_rejected), 0) AS rows_rejected
FROM pipeline_audit
GROUP BY
    DATE(started_at)
ORDER BY
    run_date DESC;
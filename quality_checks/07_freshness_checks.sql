WITH expected_tables(table_name) AS (
    VALUES
        ('stg_customers'),
        ('stg_products'),
        ('stg_orders'),
        ('stg_order_items'),
        ('stg_payments')
),

freshness_check AS (
    SELECT
        expected.table_name,

        watermark.last_loaded_at,

        watermark.updated_at,

        CASE
            WHEN watermark.last_loaded_at IS NULL
                THEN NULL

            ELSE ROUND(
                (
                    JULIANDAY('now')
                    - JULIANDAY(watermark.last_loaded_at)
                ) * 24,
                2
            )
        END AS hours_since_last_load,

        __FRESHNESS_THRESHOLD_HOURS__
            AS freshness_threshold_hours,

        CASE
            WHEN watermark.last_loaded_at IS NULL
                THEN 'NOT_LOADED'

            WHEN watermark.last_loaded_at
                 = '1900-01-01 00:00:00'
                THEN 'NOT_LOADED'

            WHEN (
                JULIANDAY('now')
                - JULIANDAY(watermark.last_loaded_at)
            ) * 24
                > __FRESHNESS_THRESHOLD_HOURS__
                THEN 'STALE_DATA'

            ELSE 'FRESH'
        END AS freshness_status

    FROM expected_tables AS expected

    LEFT JOIN pipeline_watermark AS watermark
        ON expected.table_name = watermark.table_name
)

SELECT
    table_name,
    last_loaded_at,
    updated_at,
    hours_since_last_load,
    freshness_threshold_hours,
    freshness_status

FROM freshness_check

WHERE freshness_status IN (
    'STALE_DATA',
    'NOT_LOADED'
)

ORDER BY
    CASE freshness_status
        WHEN 'NOT_LOADED' THEN 1
        WHEN 'STALE_DATA' THEN 2
        ELSE 3
    END,
    table_name;
PRAGMA foreign_keys = ON;

BEGIN TRANSACTION;

DELETE FROM rejected_influencer_records
WHERE EXISTS (
    SELECT 1
    FROM stg_influencer_payments AS stg
    WHERE
        stg.source_file =
            rejected_influencer_records.source_file
        AND stg.source_sheet =
            rejected_influencer_records.source_sheet
        AND stg.source_row_number =
            rejected_influencer_records.source_row_number
);


WITH normalized_records AS (
    SELECT
        campaign_name,
        source_section,
        sequence_number,
        TRIM(influencer_handle) AS influencer_handle,
        fee_amount AS fee_amount_text,
        REPLACE(
            TRIM(COALESCE(fee_amount, '')),
            ',',
            ''
        ) AS normalized_fee_text,
        post_date_text,
        bank_account_hash,
        payment_round_text,
        CASE
            WHEN LOWER(
                TRIM(
                    COALESCE(
                        payment_status,
                        ''
                    )
                )
            ) IN (
                'ทำจ่ายแล้ว',
                'จ่ายแล้ว',
                'paid'
            )
                THEN 'PAID'

            WHEN LOWER(
                TRIM(
                    COALESCE(
                        payment_status,
                        ''
                    )
                )
            ) IN (
                'ยังไม่ทำจ่าย',
                'ยังไม่จ่าย',
                'unpaid',
                'pending'
            )
                THEN 'UNPAID'

            WHEN LOWER(
                TRIM(
                    COALESCE(
                        payment_status,
                        ''
                    )
                )
            ) IN (
                'ยกเลิก',
                'cancel',
                'cancelled',
                'canceled'
            )
                THEN 'CANCELLED'

            ELSE 'INVALID'
        END AS normalized_payment_status,
        contact_phone_hash,
        account_name_masked,
        notes_sanitized,
        source_file,
        source_sheet,
        source_row_number,
        loaded_at
    FROM stg_influencer_payments
),
validated_records AS (
    SELECT
        *,
        CASE
            WHEN influencer_handle IS NULL
                 OR influencer_handle = ''
                THEN 'MISSING_INFLUENCER_HANDLE'

            WHEN campaign_name IS NULL
                 OR TRIM(campaign_name) = ''
                THEN 'MISSING_CAMPAIGN_NAME'

            WHEN source_section IS NULL
                 OR TRIM(source_section) = ''
                THEN 'MISSING_SOURCE_SECTION'

            WHEN normalized_payment_status = 'INVALID'
                THEN 'INVALID_PAYMENT_STATUS'

            WHEN normalized_payment_status <> 'CANCELLED'
                 AND (
                     normalized_fee_text = ''
                     OR normalized_fee_text
                        GLOB '*[^0-9.]*'
                     OR (
                         LENGTH(
                             normalized_fee_text
                         )
                         - LENGTH(
                             REPLACE(
                                 normalized_fee_text,
                                 '.',
                                 ''
                             )
                         )
                     ) > 1
                 )
                THEN 'INVALID_FEE_AMOUNT'

            WHEN normalized_payment_status <> 'CANCELLED'
                 AND CAST(
                     normalized_fee_text
                     AS REAL
                 ) < 0
                THEN 'NEGATIVE_FEE_AMOUNT'

            ELSE NULL
        END AS rejection_reason
    FROM normalized_records
)
INSERT INTO rejected_influencer_records (
    campaign_name,
    source_section,
    sequence_number,
    influencer_handle,
    fee_amount_text,
    post_date_text,
    payment_round_text,
    payment_status_text,
    rejection_reason,
    source_file,
    source_sheet,
    source_row_number
)
SELECT
    campaign_name,
    source_section,
    sequence_number,
    influencer_handle,
    fee_amount_text,
    post_date_text,
    payment_round_text,
    normalized_payment_status,
    rejection_reason,
    source_file,
    source_sheet,
    source_row_number
FROM validated_records
WHERE rejection_reason IS NOT NULL;


WITH normalized_campaigns AS (
    SELECT DISTINCT
        TRIM(
            campaign_name
        ) AS campaign_name,
        TRIM(
            source_section
        ) AS source_section
    FROM stg_influencer_payments
    WHERE
        campaign_name IS NOT NULL
        AND TRIM(campaign_name) <> ''
        AND source_section IS NOT NULL
        AND TRIM(source_section) <> ''
        AND influencer_handle IS NOT NULL
        AND TRIM(influencer_handle) <> ''
)
INSERT INTO campaigns (
    campaign_name,
    source_section,
    created_at,
    updated_at
)
SELECT
    campaign_name,
    source_section,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM normalized_campaigns
WHERE 1 = 1
ON CONFLICT(
    campaign_name,
    source_section
) DO UPDATE SET
    updated_at = CURRENT_TIMESTAMP;


WITH valid_influencers AS (
    SELECT
        TRIM(
            influencer_handle
        ) AS influencer_handle,
        MAX(
            bank_account_hash
        ) AS bank_account_hash,
        MAX(
            contact_phone_hash
        ) AS contact_phone_hash,
        MAX(
            account_name_masked
        ) AS account_name_masked
    FROM stg_influencer_payments
    WHERE
        influencer_handle IS NOT NULL
        AND TRIM(influencer_handle) <> ''
        AND TRIM(influencer_handle) NOT IN (
            'รายชื่อ',
            'ทั้งหมด',
            'ทำจ่ายแล้ว',
            'ยังไม่ทำจ่าย',
            'สรุป'
        )
    GROUP BY
        TRIM(influencer_handle)
)
INSERT INTO influencers (
    influencer_handle,
    bank_account_hash,
    contact_phone_hash,
    account_name_masked,
    created_at,
    updated_at
)
SELECT
    influencer_handle,
    bank_account_hash,
    contact_phone_hash,
    account_name_masked,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM valid_influencers
WHERE 1 = 1
ON CONFLICT(
    influencer_handle
) DO UPDATE SET
    bank_account_hash = COALESCE(
        excluded.bank_account_hash,
        influencers.bank_account_hash
    ),
    contact_phone_hash = COALESCE(
        excluded.contact_phone_hash,
        influencers.contact_phone_hash
    ),
    account_name_masked = COALESCE(
        excluded.account_name_masked,
        influencers.account_name_masked
    ),
    updated_at = CURRENT_TIMESTAMP;


WITH normalized_records AS (
    SELECT
        TRIM(
            campaign_name
        ) AS campaign_name,
        TRIM(
            source_section
        ) AS source_section,
        sequence_number,
        TRIM(
            influencer_handle
        ) AS influencer_handle,
        REPLACE(
            TRIM(
                COALESCE(
                    fee_amount,
                    ''
                )
            ),
            ',',
            ''
        ) AS normalized_fee_text,
        post_date_text,
        payment_round_text,
        CASE
            WHEN LOWER(
                TRIM(
                    COALESCE(
                        payment_status,
                        ''
                    )
                )
            ) IN (
                'ทำจ่ายแล้ว',
                'จ่ายแล้ว',
                'paid'
            )
                THEN 'PAID'

            WHEN LOWER(
                TRIM(
                    COALESCE(
                        payment_status,
                        ''
                    )
                )
            ) IN (
                'ยังไม่ทำจ่าย',
                'ยังไม่จ่าย',
                'unpaid',
                'pending'
            )
                THEN 'UNPAID'

            WHEN LOWER(
                TRIM(
                    COALESCE(
                        payment_status,
                        ''
                    )
                )
            ) IN (
                'ยกเลิก',
                'cancel',
                'cancelled',
                'canceled'
            )
                THEN 'CANCELLED'

            ELSE 'INVALID'
        END AS normalized_payment_status,
        notes_sanitized,
        source_file,
        source_sheet,
        source_row_number
    FROM stg_influencer_payments
),
valid_records AS (
    SELECT
        *,
        CASE
            WHEN normalized_payment_status =
                 'CANCELLED'
                THEN 0.0

            ELSE CAST(
                normalized_fee_text
                AS REAL
            )
        END AS normalized_fee_amount
    FROM normalized_records
    WHERE
        influencer_handle IS NOT NULL
        AND influencer_handle <> ''
        AND campaign_name IS NOT NULL
        AND campaign_name <> ''
        AND source_section IS NOT NULL
        AND source_section <> ''
        AND normalized_payment_status IN (
            'PAID',
            'UNPAID',
            'CANCELLED'
        )
        AND (
            normalized_payment_status =
                'CANCELLED'
            OR (
                normalized_fee_text <> ''
                AND normalized_fee_text
                    NOT GLOB '*[^0-9.]*'
                AND (
                    LENGTH(
                        normalized_fee_text
                    )
                    - LENGTH(
                        REPLACE(
                            normalized_fee_text,
                            '.',
                            ''
                        )
                    )
                ) <= 1
                AND CAST(
                    normalized_fee_text
                    AS REAL
                ) >= 0
            )
        )
)
INSERT INTO influencer_payments (
    campaign_id,
    influencer_id,
    source_sequence,
    fee_amount,
    post_date,
    payment_round_date,
    payment_status,
    notes_sanitized,
    source_file,
    source_sheet,
    source_row_number,
    record_hash,
    created_at,
    updated_at
)
SELECT
    c.campaign_id,
    i.influencer_id,
    vr.sequence_number,
    vr.normalized_fee_amount,
    NULL,
    NULL,
    vr.normalized_payment_status,
    vr.notes_sanitized,
    vr.source_file,
    vr.source_sheet,
    vr.source_row_number,
    LOWER(
        HEX(
            vr.source_file
            || '|'
            || vr.source_sheet
            || '|'
            || CAST(
                vr.source_row_number
                AS TEXT
            )
            || '|'
            || vr.influencer_handle
        )
    ),
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
FROM valid_records AS vr
INNER JOIN campaigns AS c
    ON vr.campaign_name =
        c.campaign_name
    AND vr.source_section =
        c.source_section
INNER JOIN influencers AS i
    ON vr.influencer_handle =
        i.influencer_handle
WHERE 1 = 1
ON CONFLICT(
    record_hash
) DO UPDATE SET
    campaign_id =
        excluded.campaign_id,
    influencer_id =
        excluded.influencer_id,
    source_sequence =
        excluded.source_sequence,
    fee_amount =
        excluded.fee_amount,
    payment_status =
        excluded.payment_status,
    notes_sanitized =
        excluded.notes_sanitized,
    source_file =
        excluded.source_file,
    source_sheet =
        excluded.source_sheet,
    source_row_number =
        excluded.source_row_number,
    updated_at =
        CURRENT_TIMESTAMP;


COMMIT;
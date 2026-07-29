WITH influencer_quality_results AS (

    SELECT
        'INVALID_PAYMENT_STATUS' AS check_name,
        'influencer_payments' AS table_name,
        CAST(influencer_payment_id AS TEXT) AS record_identifier,
        payment_status AS invalid_value,
        'สถานะการจ่ายต้องเป็น PAID, UNPAID หรือ CANCELLED'
            AS issue_description
    FROM influencer_payments
    WHERE payment_status NOT IN (
        'PAID',
        'UNPAID',
        'CANCELLED'
    )

    UNION ALL

    SELECT
        'NEGATIVE_FEE_AMOUNT',
        'influencer_payments',
        CAST(influencer_payment_id AS TEXT),
        CAST(fee_amount AS TEXT),
        'ค่าจ้างต้องไม่ติดลบ'
    FROM influencer_payments
    WHERE fee_amount < 0

    UNION ALL

    SELECT
        'CANCELLED_WITH_NONZERO_AMOUNT',
        'influencer_payments',
        CAST(influencer_payment_id AS TEXT),
        CAST(fee_amount AS TEXT),
        'รายการที่ยกเลิกควรมีค่าจ้างเท่ากับ 0'
    FROM influencer_payments
    WHERE
        payment_status = 'CANCELLED'
        AND fee_amount <> 0

    UNION ALL

    SELECT
        'MISSING_CAMPAIGN_REFERENCE',
        'influencer_payments',
        CAST(ip.influencer_payment_id AS TEXT),
        CAST(ip.campaign_id AS TEXT),
        'ไม่พบแคมเปญที่รายการจ่ายอ้างอิง'
    FROM influencer_payments AS ip
    LEFT JOIN campaigns AS c
        ON ip.campaign_id = c.campaign_id
    WHERE c.campaign_id IS NULL

    UNION ALL

    SELECT
        'MISSING_INFLUENCER_REFERENCE',
        'influencer_payments',
        CAST(ip.influencer_payment_id AS TEXT),
        CAST(ip.influencer_id AS TEXT),
        'ไม่พบ Influencer ที่รายการจ่ายอ้างอิง'
    FROM influencer_payments AS ip
    LEFT JOIN influencers AS i
        ON ip.influencer_id = i.influencer_id
    WHERE i.influencer_id IS NULL

    UNION ALL

    SELECT
        'DUPLICATE_SOURCE_LOCATION',
        'influencer_payments',
        source_file
            || ' | '
            || source_sheet
            || ' | row '
            || CAST(source_row_number AS TEXT),
        CAST(COUNT(*) AS TEXT),
        'แถวต้นทางเดียวกันถูกโหลดมากกว่าหนึ่งครั้ง'
    FROM influencer_payments
    GROUP BY
        source_file,
        source_sheet,
        source_row_number
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'DUPLICATE_RECORD_HASH',
        'influencer_payments',
        record_hash,
        CAST(COUNT(*) AS TEXT),
        'พบ record_hash ซ้ำ'
    FROM influencer_payments
    GROUP BY record_hash
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'UNMASKED_ACCOUNT_NAME',
        'influencers',
        CAST(influencer_id AS TEXT),
        account_name_masked,
        'ชื่อบัญชีควรถูกปิดบังและมีเครื่องหมาย *'
    FROM influencers
    WHERE
        account_name_masked IS NOT NULL
        AND account_name_masked <> ''
        AND account_name_masked NOT LIKE '%*%'

    UNION ALL

    SELECT
        'INVALID_BANK_ACCOUNT_HASH',
        'influencers',
        CAST(influencer_id AS TEXT),
        bank_account_hash,
        'Bank account hash ต้องเป็น SHA-256 ความยาว 64 ตัวอักษร'
    FROM influencers
    WHERE
        bank_account_hash IS NOT NULL
        AND LENGTH(bank_account_hash) <> 64

    UNION ALL

    SELECT
        'INVALID_PHONE_HASH',
        'influencers',
        CAST(influencer_id AS TEXT),
        contact_phone_hash,
        'Phone hash ต้องเป็น SHA-256 ความยาว 64 ตัวอักษร'
    FROM influencers
    WHERE
        contact_phone_hash IS NOT NULL
        AND LENGTH(contact_phone_hash) <> 64

    UNION ALL

    SELECT
        'RAW_PHONE_FOUND_IN_NOTES',
        'influencer_payments',
        CAST(influencer_payment_id AS TEXT),
        notes_sanitized,
        'หมายเหตุอาจยังมีเบอร์โทรศัพท์ที่ไม่ได้ปิดบัง'
    FROM influencer_payments
    WHERE
        notes_sanitized GLOB '*0[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]*'

    UNION ALL

    SELECT
        'UNKNOWN_CAMPAIGN_NAME',
        'campaigns',
        CAST(campaign_id AS TEXT),
        campaign_name,
        'ชื่อแคมเปญต้องไม่เป็น Unknown Campaign'
    FROM campaigns
    WHERE
        LOWER(TRIM(campaign_name)) = 'unknown campaign'

    UNION ALL

    SELECT
        'UNKNOWN_SOURCE_SECTION',
        'campaigns',
        CAST(campaign_id AS TEXT),
        source_section,
        'ระบบตรวจหาชื่อส่วนข้อมูลต้นทางไม่สำเร็จ'
    FROM campaigns
    WHERE
        source_section LIKE 'UNKNOWN_SECTION_ROW_%'

    UNION ALL

    SELECT
        'REJECT_WITHOUT_REASON',
        'rejected_influencer_records',
        CAST(rejection_id AS TEXT),
        rejection_reason,
        'ข้อมูลที่ถูก Reject ต้องมีเหตุผล'
    FROM rejected_influencer_records
    WHERE
        rejection_reason IS NULL
        OR TRIM(rejection_reason) = ''
)

SELECT
    check_name,
    table_name,
    record_identifier,
    invalid_value,
    issue_description
FROM influencer_quality_results
ORDER BY
    check_name,
    table_name,
    record_identifier;
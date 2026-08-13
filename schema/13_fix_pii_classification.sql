PRAGMA foreign_keys = ON;

-- Governance / Lineage
-- Step G6A Fix: PII classification consistency.
--
-- Customer source/staging assets contain direct PII such as customer_name
-- and email, so INTERNAL is too weak for the governance policy used by the
-- acceptance tests. Promote them to CONFIDENTIAL.

UPDATE data_assets
SET
    classification = 'CONFIDENTIAL',
    updated_at = CURRENT_TIMESTAMP
WHERE asset_key IN (
    'file://synthetic/customers.csv',
    'sqlite://staging/stg_customers'
);

-- Safety check: no PII asset should remain PUBLIC/INTERNAL.
SELECT
    asset_key,
    classification
FROM data_assets
WHERE
    contains_pii = 1
    AND classification NOT IN (
        'CONFIDENTIAL',
        'RESTRICTED'
    );

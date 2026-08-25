# Project 01 — SQLite Database ER Diagram

This document reflects the current Project 01 SQLite schema after the reliability, monitoring, alerting, recovery, governance, and lineage milestones.

The repository currently defines **25 persistent SQLite tables**:

- **6 staging tables**
- **10 business / quarantine tables**
- **6 pipeline operations / observability tables**
- **3 governance / lineage tables**

To keep the diagrams readable, the schema is split into focused ER views. Only relationships enforced by SQLite foreign keys are drawn as ER relationships. Run IDs and other operational correlation fields are intentionally not shown as foreign-key relationships when the database does not enforce them as such.

---

## 1. E-commerce core model

```mermaid
erDiagram
    CUSTOMERS {
        INTEGER customer_id PK
        TEXT customer_name
        TEXT email UK
        TEXT city
        DATE signup_date
        TEXT created_at
        TEXT updated_at
    }

    PRODUCTS {
        INTEGER product_id PK
        TEXT product_name
        TEXT category
        REAL unit_price
        INTEGER stock_quantity
        TEXT created_at
        TEXT updated_at
    }

    ORDERS {
        INTEGER order_id PK
        INTEGER customer_id FK
        DATE order_date
        TEXT order_status
        REAL order_total
        TEXT created_at
        TEXT updated_at
    }

    ORDER_ITEMS {
        INTEGER order_item_id PK
        INTEGER order_id FK
        INTEGER product_id FK
        INTEGER quantity
        REAL unit_price
        REAL line_total
        TEXT created_at
        TEXT updated_at
    }

    PAYMENTS {
        INTEGER payment_id PK
        INTEGER order_id FK
        DATE payment_date
        TEXT payment_method
        REAL payment_amount
        TEXT payment_status
        TEXT created_at
        TEXT updated_at
    }

    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--o{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : referenced_by
    ORDERS ||--o{ PAYMENTS : has
```

### Core relationship rules

- `orders.customer_id` → `customers.customer_id`
- `order_items.order_id` → `orders.order_id`
- `order_items.product_id` → `products.product_id`
- `payments.order_id` → `orders.order_id`

---

## 2. Influencer-payment model

```mermaid
erDiagram
    CAMPAIGNS {
        INTEGER campaign_id PK
        TEXT campaign_name
        TEXT source_section
        TEXT created_at
        TEXT updated_at
    }

    INFLUENCERS {
        INTEGER influencer_id PK
        TEXT influencer_handle UK
        TEXT bank_account_hash
        TEXT contact_phone_hash
        TEXT account_name_masked
        TEXT created_at
        TEXT updated_at
    }

    INFLUENCER_PAYMENTS {
        INTEGER influencer_payment_id PK
        INTEGER campaign_id FK
        INTEGER influencer_id FK
        TEXT source_sequence
        REAL fee_amount
        TEXT post_date
        TEXT payment_round_date
        TEXT payment_status
        TEXT notes_sanitized
        TEXT source_file
        TEXT source_sheet
        INTEGER source_row_number
        TEXT record_hash UK
        TEXT created_at
        TEXT updated_at
    }

    REJECTED_INFLUENCER_RECORDS {
        INTEGER rejection_id PK
        TEXT campaign_name
        TEXT source_section
        TEXT sequence_number
        TEXT influencer_handle
        TEXT fee_amount_text
        TEXT post_date_text
        TEXT payment_round_text
        TEXT payment_status_text
        TEXT rejection_reason
        TEXT source_file
        TEXT source_sheet
        INTEGER source_row_number
        TEXT rejected_at
    }

    CAMPAIGNS ||--o{ INFLUENCER_PAYMENTS : contains
    INFLUENCERS ||--o{ INFLUENCER_PAYMENTS : receives
```

`rejected_influencer_records` is intentionally independent from the accepted business tables. Invalid records are preserved as evidence rather than forced into the trusted model.

---

## 3. Generic source quarantine

```mermaid
erDiagram
    REJECTED_SOURCE_RECORDS {
        INTEGER rejection_id PK
        TEXT run_id
        TEXT dataset_name
        TEXT source_file
        INTEGER source_row_number
        TEXT raw_record_json
        TEXT rejected_column
        TEXT rejected_value
        TEXT rejection_reason
        TEXT rejection_type
        TEXT rejected_at
    }
```

`rejected_source_records.run_id` is nullable. A value links rejection evidence to a known run, while a null value represents evidence that could not be durably linked to one pipeline run.

---

## 4. Pipeline operations and observability

```mermaid
erDiagram
    PIPELINE_WATERMARK {
        TEXT table_name PK
        TEXT last_loaded_at
        TEXT updated_at
    }

    PIPELINE_AUDIT {
        INTEGER audit_id PK
        TEXT pipeline_name
        TEXT run_id
        TEXT run_type
        TEXT recovery_of_run_id
        TEXT backfill_start_date
        TEXT backfill_end_date
        TEXT step_name
        TEXT run_status
        INTEGER rows_processed
        INTEGER rows_inserted
        INTEGER rows_updated
        INTEGER rows_rejected
        TEXT error_message
        TEXT started_at
        TEXT completed_at
        TEXT created_at
    }

    PIPELINE_STEP_LOG {
        INTEGER step_log_id PK
        TEXT pipeline_name
        TEXT run_id
        INTEGER step_number
        TEXT step_name
        TEXT script_name
        INTEGER attempt_number
        TEXT status
        TEXT start_time
        TEXT end_time
        REAL duration_seconds
        INTEGER rows_read
        INTEGER rows_written
        INTEGER rows_rejected
        TEXT error_type
        TEXT error_message
        REAL sla_threshold_seconds
        TEXT sla_status
        TEXT created_at
        TEXT updated_at
    }

    PIPELINE_SLA_METRICS {
        INTEGER sla_metric_id PK
        TEXT pipeline_name
        TEXT run_id
        TEXT step_name
        INTEGER attempt_number
        TEXT step_run_status
        REAL duration_seconds
        REAL sla_threshold_seconds
        TEXT sla_status
        TEXT measured_at
        TEXT created_at
    }

    PIPELINE_ALERTS {
        INTEGER alert_id PK
        TEXT alert_key UK
        TEXT alert_fingerprint UK
        TEXT source_type
        TEXT alert_type
        TEXT severity
        TEXT status
        TEXT pipeline_name
        TEXT run_id
        TEXT step_name
        INTEGER attempt_number
        TEXT title
        TEXT message
        TEXT first_detected_at
        TEXT last_detected_at
        INTEGER occurrence_count
        TEXT acknowledged_at
        TEXT resolved_at
        TEXT created_at
        TEXT updated_at
    }

    PIPELINE_ALERT_OCCURRENCES {
        INTEGER occurrence_id PK
        INTEGER alert_id FK
        TEXT run_id
        INTEGER attempt_number
        TEXT detected_at
        TEXT error_type
        TEXT raw_error_message
        TEXT normalized_error_signature
        TEXT created_at
    }

    PIPELINE_ALERTS ||--o{ PIPELINE_ALERT_OCCURRENCES : records
```

### Important operational semantics

The pipeline uses `run_id` across audit, step, SLA, rejection, alert, and runtime-lineage evidence to correlate one execution. Most of these links are application-level correlations rather than SQLite foreign keys.

`pipeline_audit.recovery_of_run_id` records the failed top-level run that a declared recovery is intended to recover. It is deliberately shown as a field rather than a physical self-referencing foreign key because the schema does not enforce that relationship.

Alert lifecycle state is constrained to:

```text
OPEN → ACKNOWLEDGED → RESOLVED
```

`pipeline_alert_occurrences.alert_id` is an enforced foreign key to `pipeline_alerts.alert_id` with cascading deletion.

---

## 5. Governance and lineage

```mermaid
erDiagram
    DATA_ASSETS {
        INTEGER asset_id PK
        TEXT asset_key UK
        TEXT asset_name
        TEXT asset_type
        TEXT data_layer
        TEXT data_domain
        TEXT source_system
        TEXT asset_location
        TEXT data_format
        TEXT classification
        INTEGER contains_pii
        TEXT owner_name
        TEXT description
        INTEGER is_active
        TEXT created_at
        TEXT updated_at
    }

    LINEAGE_EDGES {
        INTEGER lineage_edge_id PK
        INTEGER upstream_asset_id FK
        INTEGER downstream_asset_id FK
        TEXT transformation_name
        TEXT transformation_type
        TEXT process_reference
        TEXT lineage_level
        TEXT run_id
        INTEGER is_active
        TEXT created_at
        TEXT updated_at
    }

    LINEAGE_RUN_EVENTS {
        INTEGER lineage_run_event_id PK
        INTEGER lineage_edge_id FK
        TEXT run_id
        TEXT execution_status
        TEXT step_name
        INTEGER attempt_number
        TEXT recorded_at
    }

    DATA_ASSETS ||--o{ LINEAGE_EDGES : upstream_asset
    DATA_ASSETS ||--o{ LINEAGE_EDGES : downstream_asset
    LINEAGE_EDGES ||--o{ LINEAGE_RUN_EVENTS : executed_as
```

### Governance model

`data_assets` is the registry of files, tables, views, outputs, and other governed assets.

`lineage_edges` stores the static dependency graph between registered upstream and downstream assets.

`lineage_run_events` records which lineage edge participated in a concrete pipeline execution.

---

## 6. Staging layer

The six staging tables intentionally keep source-like values as text where appropriate so validation and transformation happen after ingestion.

```mermaid
erDiagram
    STG_CUSTOMERS {
        TEXT customer_id
        TEXT customer_name
        TEXT email
        TEXT city
        TEXT signup_date
        TEXT source_file
        TEXT loaded_at
    }

    STG_PRODUCTS {
        TEXT product_id
        TEXT product_name
        TEXT category
        TEXT unit_price
        TEXT stock_quantity
        TEXT source_file
        TEXT loaded_at
    }

    STG_ORDERS {
        TEXT order_id
        TEXT customer_id
        TEXT order_date
        TEXT order_status
        TEXT source_file
        TEXT loaded_at
    }

    STG_ORDER_ITEMS {
        TEXT order_item_id
        TEXT order_id
        TEXT product_id
        TEXT quantity
        TEXT unit_price
        TEXT source_file
        TEXT loaded_at
    }

    STG_PAYMENTS {
        TEXT payment_id
        TEXT order_id
        TEXT payment_date
        TEXT payment_method
        TEXT payment_amount
        TEXT payment_status
        TEXT source_file
        TEXT loaded_at
    }

    STG_INFLUENCER_PAYMENTS {
        INTEGER staging_row_id PK
        TEXT campaign_name
        TEXT source_section
        TEXT sequence_number
        TEXT influencer_handle
        TEXT fee_amount
        TEXT post_date_text
        TEXT bank_account_hash
        TEXT payment_round_text
        TEXT payment_status
        TEXT contact_phone_hash
        TEXT account_name_masked
        TEXT notes_sanitized
        TEXT source_file
        TEXT source_sheet
        INTEGER source_row_number
        TEXT loaded_at
    }
```

The staging tables do not enforce business foreign keys. That is intentional: malformed, late, or referentially invalid source records must be ingestible so the pipeline can validate, quarantine, and explain them instead of failing before evidence is captured.

---

## Physical table inventory

| Layer | Tables |
|---|---|
| Staging | `stg_customers`, `stg_products`, `stg_orders`, `stg_order_items`, `stg_payments`, `stg_influencer_payments` |
| E-commerce core | `customers`, `products`, `orders`, `order_items`, `payments` |
| Influencer-payment core | `campaigns`, `influencers`, `influencer_payments` |
| Quarantine | `rejected_influencer_records`, `rejected_source_records` |
| Pipeline operations | `pipeline_watermark`, `pipeline_audit`, `pipeline_step_log`, `pipeline_sla_metrics` |
| Alerting | `pipeline_alerts`, `pipeline_alert_occurrences` |
| Governance / lineage | `data_assets`, `lineage_edges`, `lineage_run_events` |

Views are documented separately from physical tables and therefore are not represented as ER entities here.

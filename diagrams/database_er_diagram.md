# Database ER Diagram

```mermaid
erDiagram

    CUSTOMERS {
        TEXT customer_id PK
        TEXT customer_name
        TEXT email
        TEXT city
        TEXT signup_date
        TEXT created_at
        TEXT updated_at
    }

    PRODUCTS {
        TEXT product_id PK
        TEXT product_name
        TEXT category
        REAL unit_price
        INTEGER stock_quantity
        TEXT created_at
        TEXT updated_at
    }

    ORDERS {
        TEXT order_id PK
        TEXT customer_id FK
        TEXT order_date
        TEXT order_status
        REAL order_total
        TEXT created_at
        TEXT updated_at
    }

    ORDER_ITEMS {
        TEXT order_item_id PK
        TEXT order_id FK
        TEXT product_id FK
        INTEGER quantity
        REAL unit_price
        REAL line_total
        TEXT created_at
        TEXT updated_at
    }

    PAYMENTS {
        TEXT payment_id PK
        TEXT order_id FK
        TEXT payment_date
        TEXT payment_method
        REAL payment_amount
        TEXT payment_status
        TEXT created_at
        TEXT updated_at
    }

    CAMPAIGNS {
        INTEGER campaign_id PK
        TEXT campaign_name
        TEXT source_section
        TEXT created_at
        TEXT updated_at
    }

    INFLUENCERS {
        INTEGER influencer_id PK
        TEXT influencer_handle
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
        TEXT record_hash
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

    PIPELINE_AUDIT {
        INTEGER audit_id PK
        TEXT pipeline_name
        TEXT run_id
        TEXT step_name
        TEXT run_status
        INTEGER rows_processed
        INTEGER rows_inserted
        INTEGER rows_updated
        INTEGER rows_rejected
        TEXT error_message
        TEXT started_at
        TEXT completed_at
    }

    CUSTOMERS ||--o{ ORDERS : places
    ORDERS ||--|{ ORDER_ITEMS : contains
    PRODUCTS ||--o{ ORDER_ITEMS : included_in
    ORDERS ||--o{ PAYMENTS : has

    CAMPAIGNS ||--o{ INFLUENCER_PAYMENTS : contains
    INFLUENCERS ||--o{ INFLUENCER_PAYMENTS : receives
# Hybrid E-commerce Data Pipeline Architecture

```mermaid
flowchart LR

    A1[Synthetic CSV Files] --> B[Raw Data Loader]
    A2[Pawchoice Excel] --> B

    B --> C1[stg_customers]
    B --> C2[stg_products]
    B --> C3[stg_orders]
    B --> C4[stg_order_items]
    B --> C5[stg_payments]
    B --> C6[stg_influencer_payments]

    C1 --> D[SQL Transformations]
    C2 --> D
    C3 --> D
    C4 --> D
    C5 --> D
    C6 --> D

    D --> E1[customers]
    D --> E2[products]
    D --> E3[orders]
    D --> E4[order_items]
    D --> E5[payments]
    D --> E6[campaigns]
    D --> E7[influencers]
    D --> E8[influencer_payments]
    D --> E9[rejected_influencer_records]

    E1 --> F[Data Quality Checks]
    E2 --> F
    E3 --> F
    E4 --> F
    E5 --> F
    E6 --> F
    E7 --> F
    E8 --> F
    E9 --> F

    F --> G1[Null Checks]
    F --> G2[Duplicate Checks]
    F --> G3[Referential Integrity]
    F --> G4[Reconciliation]
    F --> G5[Business Rules]
    F --> G6[Privacy Checks]

    G1 --> H[SQLite Views]
    G2 --> H
    G3 --> H
    G4 --> H
    G5 --> H
    G6 --> H

    H --> I1[Campaign Payment Summary]
    H --> I2[Payment Status Summary]
    H --> I3[Rejected Record Summary]
    H --> I4[Pipeline Run Summary]
    H --> I5[Data Quality Summary]
    H --> I6[Daily Sales Summary]

    I1 --> J[Portfolio CSV Outputs]
    I2 --> J
    I3 --> J
    I4 --> J
    I5 --> J
    I6 --> J

    B --> K[Pipeline Audit]
    D --> K
    F --> K
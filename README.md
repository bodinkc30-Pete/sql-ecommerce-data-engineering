# SQL E-commerce Data Engineering

A production-style hybrid data engineering project that combines synthetic e-commerce transaction data with a real-world Pawchoice influencer payment workbook.

The pipeline ingests CSV and Excel sources, loads raw records into staging tables, applies SQL transformations, protects personally identifiable information, routes invalid records to rejected tables, validates data quality, and exports portfolio-safe analytical outputs.

---

## Project Overview

This project demonstrates an end-to-end data pipeline using:

- Python
- SQL
- SQLite
- openpyxl
- CSV and Excel ingestion
- Staging and core table architecture
- Data quality validation
- Rejected-record handling
- Data lineage
- PII hashing and masking
- Incremental and idempotent processing
- Automated tests
- Pipeline monitoring
- Portfolio-safe data exports

The project contains two data domains:

1. Synthetic e-commerce transactions
2. Pawchoice influencer payment records

---

## Architecture

```mermaid
flowchart LR

    A1[Synthetic CSV Files] --> B[Raw Data Loader]
    A2[Pawchoice Excel] --> B

    B --> C1[Staging Tables]
    C1 --> D[SQL Transformations]

    D --> E1[E-commerce Core Tables]
    D --> E2[Influencer Payment Core Tables]
    D --> E3[Rejected Records]

    E1 --> F[Data Quality Checks]
    E2 --> F
    E3 --> F

    F --> G[SQLite Analytical Views]
    G --> H[Portfolio-safe CSV Outputs]

    B --> I[Pipeline Audit]
    D --> I
    F --> I
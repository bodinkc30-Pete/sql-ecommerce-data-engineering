# SQL E-commerce Data Engineering — Pipeline Architecture

This diagram represents the current Project 01 architecture after the reliability, observability, Airflow, REST API, performance, CI/CD, and incident-response milestones.

```mermaid
flowchart TB

    %% ----------------------------
    %% Sources
    %% ----------------------------
    subgraph SRC["Data Sources"]
        CSV["Synthetic E-commerce CSVs<br/>Demo + Hybrid"]
        XLSX["Private Pawchoice Excel<br/>Hybrid only"]
    end

    %% ----------------------------
    %% Execution / Orchestration
    %% ----------------------------
    subgraph EXEC["Execution & Orchestration"]
        CLI["Local / Docker CLI"]
        AF["Apache Airflow<br/>LocalExecutor"]
        DAG["project01_ecommerce_pipeline DAG<br/>daily • catchup=false • retries=2"]
        ORCH["scripts/05_run_pipeline.py<br/>Existing Pipeline Orchestrator"]
    end

    CLI --> ORCH
    AF --> DAG
    DAG --> ORCH

    %% ----------------------------
    %% Pipeline stages
    %% ----------------------------
    subgraph PIPE["Pipeline Stages"]
        SETUP["1. SETUP_DATABASE<br/>scripts/01_setup_database.py"]
        LOAD["2. LOAD_RAW_DATA<br/>scripts/02_load_raw_data.py"]
        TRANS["3. RUN_TRANSFORMATIONS<br/>scripts/03_run_transformations.py"]
        DQ["4. RUN_QUALITY_CHECKS<br/>scripts/04_run_quality_checks.py"]
    end

    ORCH --> SETUP --> LOAD --> TRANS --> DQ

    CSV --> LOAD
    XLSX --> LOAD

    %% ----------------------------
    %% SQLite data platform
    %% ----------------------------
    subgraph SQLITE["SQLite Data Platform"]
        STG["Staging Layer<br/>stg_*"]
        CORE["Core Relational Layer<br/>customers • products • orders<br/>order_items • payments<br/>campaigns • influencers • influencer_payments"]
        REJ["Rejected / Quarantine Layer<br/>rejected_source_records<br/>rejected_influencer_records"]
        WM["Incremental State<br/>pipeline_watermark"]
        VIEWS["Serving Views / Data Marts<br/>sales • products • customers<br/>payments • pipeline • quality • alerts"]
    end

    LOAD --> STG
    STG --> TRANS
    TRANS --> CORE
    TRANS --> REJ
    TRANS --> WM
    CORE --> DQ
    REJ --> DQ
    DQ --> VIEWS

    %% ----------------------------
    %% Reliability & observability
    %% ----------------------------
    subgraph OBS["Reliability, Monitoring & Alerting"]
        AUDIT["pipeline_audit"]
        STEP["pipeline_step_log"]
        SLA["pipeline_sla_metrics"]
        ALERT["pipeline_alerts"]
        OCC["pipeline_alert_occurrences"]
        ALERTCLI["scripts/07_manage_alerts.py<br/>OPEN → ACKNOWLEDGED → RESOLVED"]
    end

    ORCH --> AUDIT
    ORCH --> STEP
    STEP --> SLA
    ORCH --> ALERT
    DQ --> ALERT
    ALERT --> OCC
    ALERTCLI --> ALERT

    %% ----------------------------
    %% Governance & lineage
    %% ----------------------------
    subgraph GOV["Governance & Lineage"]
        ASSET["data_assets"]
        EDGE["lineage_edges"]
        RUNLINE["lineage_run_events"]
        GOVVIEW["Governance / Dependency Views"]
    end

    STG --> ASSET
    CORE --> ASSET
    VIEWS --> ASSET
    ASSET --> EDGE
    ORCH --> RUNLINE
    EDGE --> RUNLINE
    EDGE --> GOVVIEW

    %% ----------------------------
    %% Serving
    %% ----------------------------
    subgraph SERVE["Consumption / Serving"]
        EXPORT["scripts/06_export_portfolio_outputs.py<br/>Portfolio-safe CSV outputs"]
        API["FastAPI Read-only REST API<br/>api/app.py"]
        HEALTH["/health"]
        SALES["/api/v1/sales/daily"]
        PROD["/api/v1/products/sales"]
        RUNS["/api/v1/pipelines/runs"]
        QAPI["/api/v1/quality/issues"]
        AAPI["/api/v1/alerts"]
    end

    VIEWS --> EXPORT
    VIEWS --> API
    AUDIT --> API
    ALERT --> API

    API --> HEALTH
    API --> SALES
    API --> PROD
    API --> RUNS
    API --> QAPI
    API --> AAPI

    %% ----------------------------
    %% Troubleshooting & recovery
    %% ----------------------------
    subgraph IR["Incident Response & Recovery"]
        RCA["queries/05_incident_troubleshooting.sql<br/>Read-only RCA Evidence Pack"]
        RUNBOOK["docs/INCIDENT_RUNBOOK.md"]
        RECOVERY["Declared Recovery<br/>--recovery-of FAILED_RUN_ID"]
    end

    AUDIT --> RCA
    STEP --> RCA
    SLA --> RCA
    REJ --> RCA
    RUNLINE --> RCA
    WM --> RCA
    RCA --> RUNBOOK
    RUNBOOK --> RECOVERY
    RECOVERY --> ORCH

    %% ----------------------------
    %% Delivery / validation
    %% ----------------------------
    subgraph DELIVERY["Packaging & Continuous Validation"]
        APPIMG["Root Docker Image<br/>Python 3.12 slim • non-root"]
        AFIMG["Airflow Docker Stack<br/>PostgreSQL metadata • LocalExecutor"]
        CI["GitHub Actions CI"]
        HOSTTEST["Fresh DB + E2E Pipeline<br/>Exports + Full Test Suite"]
        DOCKERTEST["Docker Build + Full Parity Test"]
    end

    ORCH --> APPIMG
    AF --> AFIMG
    CI --> HOSTTEST
    CI --> DOCKERTEST
    APPIMG --> DOCKERTEST
```

## Architecture notes

### Airflow wraps the existing orchestrator

Airflow is an orchestration layer, not a second implementation of the pipeline.

The DAG ultimately executes:

```text
python /opt/project/scripts/05_run_pipeline.py
```

This keeps business execution logic inside the existing orchestrator and avoids duplicating ingestion, transformation, quality, retry, audit, and recovery behavior inside the DAG.

### Demo and Hybrid modes share one pipeline

- **Demo Mode** uses only version-controlled synthetic CSV files and is the default public/CI path.
- **Hybrid Mode** adds the private Pawchoice workbook while keeping sensitive source data outside Git and Docker images.

### SQLite remains the Project 01 business data store

Airflow uses PostgreSQL for Airflow metadata, but Project 01 business data continues to use SQLite.

### Serving is read-only

The FastAPI layer reads the SQLite serving layer and exposes read-only endpoints for health, sales, product sales, pipeline runs, quality issues, and alerts.

It does not expose mutating business-data routes.

### Recovery preserves lineage to the failed run

Declared recovery is executed with:

```powershell
python scripts/05_run_pipeline.py --recovery-of <FAILED_RUN_ID>
```

The recovery run records `recovery_of_run_id`, allowing the incident evidence pack to distinguish a true declared recovery from an unrelated later successful run.

### CI validates both host and Docker execution

GitHub Actions validates:

1. dependency installation,
2. Demo Mode configuration,
3. fresh-database reproducibility,
4. end-to-end pipeline execution,
5. portfolio exports,
6. automated tests,
7. artifact collection,
8. Docker image build,
9. the same validation flow inside Docker.

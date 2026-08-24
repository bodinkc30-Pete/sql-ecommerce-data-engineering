from __future__ import annotations

from datetime import timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG


PIPELINE_ROOT = "/opt/project"
PIPELINE_SCRIPT = f"{PIPELINE_ROOT}/scripts/05_run_pipeline.py"


with DAG(
    dag_id="project01_ecommerce_pipeline",
    description=(
        "Airflow wrapper for the existing Project 01 "
        "e-commerce pipeline orchestrator."
    ),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "project01",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["project01", "ecommerce", "data-engineering"],
) as dag:
    run_existing_pipeline = BashOperator(
        task_id="run_existing_pipeline",
        bash_command=f"python {PIPELINE_SCRIPT}",
        cwd=PIPELINE_ROOT,
    )

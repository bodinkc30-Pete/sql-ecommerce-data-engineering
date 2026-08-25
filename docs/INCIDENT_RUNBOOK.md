# Project 01 Incident Response & Recovery Runbook

## Purpose

This runbook defines the operational procedure for investigating, recovering, and verifying incidents in the SQL E-commerce Data Engineering pipeline.

It is designed to work with telemetry and controls already implemented in this repository:

- `pipeline_audit`
- `pipeline_step_log`
- `pipeline_sla_metrics`
- `pipeline_alerts`
- `pipeline_alert_occurrences`
- `rejected_source_records`
- `lineage_run_events`
- `pipeline_watermark`
- `queries/05_incident_troubleshooting.sql`
- `scripts/05_run_pipeline.py`
- `scripts/07_manage_alerts.py`

The objective is not only to restore service, but to preserve evidence showing what failed, where it failed, why the evidence supports the root cause, what recovery action was taken, and whether the recovery actually succeeded.

---

## Operating principles

### 1. Never guess the root cause

A symptom is not automatically a root cause.

Examples:

- `STALE_DATA` is a symptom until the failed or delayed upstream step is identified.
- `database is locked` is evidence of a lock-related failure, but the incident still needs run and step context.
- rejected rows may be related to an incident, but rows without durable `run_id` linkage must not be presented as proven incident evidence.

Use the evidence pack before writing an RCA.

### 2. Preserve incident identity

Always record the affected `run_id`.

Do not mix evidence from unrelated runs simply because they happened close together.

### 3. Prefer durable linkage over time proximity

Evidence directly linked by `run_id` is stronger than evidence found only within the same time window.

### 4. Do not label a later successful run as a recovery unless it is linked

A later successful run is only a candidate unless:

```text
recovery_of_run_id = <incident_run_id>
```

The troubleshooting SQL intentionally distinguishes:

```text
DECLARED_RECOVERY
POSSIBLE_RECOVERY_NOT_LINKED
```

Only `DECLARED_RECOVERY` is durable proof of recovery linkage.

### 5. Recovery is allowed only for a failed top-level pipeline run

The recovery contract requires the source run to be:

```text
pipeline_name = hybrid_ecommerce_data_pipeline
step_name     = PIPELINE_TOTAL
run_status    = FAILED
```

Do not use the recovery command for a successful run, an unknown run ID, or a standalone quality-check failure.

### 6. Do not resolve an alert before verification

The alert lifecycle is:

```text
OPEN -> ACKNOWLEDGED -> RESOLVED
```

A resolved alert should represent an incident that has been investigated and verified.

---

# Incident workflow

## Step 1 — Confirm the incident

Start from one of these signals:

- failed pipeline execution,
- failed quality gate,
- open pipeline alert,
- SLA breach,
- stale-data detection,
- rejected-source anomaly,
- unexpected pipeline state.

Capture:

```text
Incident run_id:
Detected at:
Pipeline mode:
Observed symptom:
Alert ID (if any):
Operator:
```

If an alert exists, acknowledge it after confirming that investigation has started.

```powershell
python scripts/07_manage_alerts.py acknowledge <ALERT_ID>
```

Do not resolve it yet.

---

## Step 2 — Run the incident evidence pack

Open:

```text
queries/05_incident_troubleshooting.sql
```

against:

```text
database/ecommerce_data_engineering.db
```

The file is SELECT-only and is intended to preserve an evidence-first troubleshooting workflow.

Run the sections in order.

---

## Step 3 — Identify the incident run

### Query 1 — Recent run inventory

Use this to see recent pipeline runs and their derived state.

Focus on:

```text
run_id
pipeline_components
run_type
recovery_of_run_id
pipeline_started_at
pipeline_completed_at
failed_audit_rows
running_audit_rows
rows_processed
rows_rejected
derived_pipeline_status
```

Expected operational states include:

```text
SUCCESS
FAILED
RUNNING
INCOMPLETE
```

Record the target incident `run_id`.

### Query 2 — Latest incident summary

Use this as the initial incident snapshot.

Record:

```text
incident_run_id
pipeline_components
run_type
pipeline_started_at
pipeline_completed_at
failed_audit_rows
running_audit_rows
rows_processed
rows_rejected
```

---

## Step 4 — Find the failing step

### Query 3 — Step evidence

Prefer:

```text
ORCHESTRATOR_STEP_LOG
```

when step-level telemetry exists.

If the run was executed as a standalone sub-pipeline, the evidence pack may return:

```text
PIPELINE_AUDIT_FALLBACK
```

Review:

```text
step_name
script_name
attempt_number
status
start_time
end_time
duration_seconds
rows_processed_or_read
rows_written
rows_rejected
error_type
error_message
sla_threshold_seconds
sla_status
evidence_source
```

Identify the first materially failed step.

Typical pipeline stages are:

```text
SETUP_DATABASE
LOAD_RAW_DATA
RUN_TRANSFORMATIONS
RUN_QUALITY_CHECKS
```

Do not jump directly to the final pipeline error if more specific failed-step evidence exists.

---

## Step 5 — Check SLA evidence

### Query 4 — Execution SLA evidence

Inspect whether the incident also contained a timing breach.

Relevant fields:

```text
step_name
attempt_number
step_run_status
duration_seconds
sla_threshold_seconds
sla_status
measured_at
evidence_source
```

If no orchestrator SLA telemetry exists, the evidence pack explicitly reports:

```text
NO_ORCHESTRATOR_SLA_TELEMETRY
```

Do not invent an SLA conclusion when telemetry is absent.

---

## Step 6 — Check rejected-source evidence

### Query 5 — Rejected-source evidence

Inspect:

```text
dataset_name
source_file
source_row_number
rejected_column
rejected_value
rejection_type
rejection_reason
rejected_at
evidence_linkage
```

Evidence linkage values must be interpreted carefully.

### Strong evidence

```text
DIRECT_RUN_ID
```

The rejected row is directly linked to the incident.

### Weak / contextual evidence

```text
TIME_WINDOW_UNLINKED
```

The record occurred near the incident but has no durable run linkage.

It may support investigation, but it must not be presented as proven causal evidence.

---

## Step 7 — Check runtime lineage

### Query 6 — Runtime lineage evidence

Use runtime lineage to identify which assets were involved in the failed execution.

Review:

```text
upstream_asset_name
downstream_asset_name
transformation_type
step_name
attempt_number
execution_status
recorded_at
evidence_source
```

If the run has no runtime lineage telemetry, the pack reports:

```text
NO_RUNTIME_LINEAGE_FOR_RUN
```

This is a telemetry coverage result, not proof that no data movement occurred.

---

## Step 8 — Build the RCA

At this point, write the RCA from evidence rather than assumptions.

Use this structure:

```text
Incident run_id:
Failed step:
Observed error:
Error type:
Affected dataset / asset:
Impact:
Evidence source:
Root cause:
Contributing factors:
Rejected rows:
SLA impact:
Data-quality impact:
Recovery action:
Recovery run_id:
Verification:
```

### Root-cause categories

Use the narrowest evidence-supported category.

Examples that the project is instrumented to investigate include:

```text
SOURCE_FILE_MISSING
SCHEMA_DRIFT
INVALID_SOURCE_DATA
REFERENTIAL_INTEGRITY_FAILURE
QUALITY_GATE_FAILURE
STALE_DATA
DATABASE_LOCK
SLA_BREACH
PIPELINE_STEP_FAILURE
```

Do not select a category merely because a test for that scenario exists. The incident evidence must support it.

---

# Recovery procedure

## Step 9 — Fix the cause before recovery

A recovery run should not be used to repeatedly retry an unresolved root cause.

Examples:

- restore a required source file,
- correct source schema drift,
- release the database lock,
- fix invalid configuration,
- repair the failing code or SQL,
- correct upstream data when appropriate.

Preserve the original failed run for evidence.

Do not manually rewrite its audit status to `SUCCESS`.

---

## Step 10 — Validate that the run is eligible for recovery

Recovery is only supported for a failed top-level pipeline run.

The source run must have a failed:

```text
PIPELINE_TOTAL
```

record for:

```text
hybrid_ecommerce_data_pipeline
```

The pipeline performs this validation before starting recovery.

---

## Step 11 — Run declared recovery

Use:

```powershell
python scripts/05_run_pipeline.py --recovery-of <FAILED_RUN_ID>
```

Example shape:

```powershell
python scripts/05_run_pipeline.py --recovery-of 11111111-2222-3333-4444-555555555555
```

Do not combine `--recovery-of` with backfill arguments.

The new run should carry:

```text
run_type = RECOVERY
recovery_of_run_id = <FAILED_RUN_ID>
```

This durable linkage distinguishes a declared recovery from an unrelated later success.

---

# Verification procedure

## Step 12 — Re-run the incident evidence pack

After the recovery execution, re-run:

```text
queries/05_incident_troubleshooting.sql
```

### Query 7 — Failure-to-recovery evidence

The desired result is:

```text
linkage_type = DECLARED_RECOVERY
recovery_status = SUCCESS
```

Do not treat:

```text
POSSIBLE_RECOVERY_NOT_LINKED
```

as proof of recovery.

---

## Step 13 — Verify quality and reconciliation

### Query 8 — Quality and reconciliation evidence

Confirm that the recovery did not merely finish technically while leaving data-quality problems unresolved.

Review:

```text
run_status
rows_processed
rows_rejected
error_message
```

for quality, reconciliation, freshness, and pipeline-total evidence associated with the incident and candidate recovery runs.

A successful recovery should have no unresolved critical quality failure.

---

## Step 14 — Check current freshness state

### Query 9 — Current freshness and watermark state

Review:

```text
table_name
last_loaded_at
updated_at
hours_since_last_load
```

Important:

`pipeline_watermark` represents current state.

It is not a historical incident snapshot.

Use it to verify present freshness after recovery, not to reconstruct the exact historical state at failure time.

---

## Step 15 — Verify the pipeline operationally

Confirm all applicable conditions:

```text
[ ] Recovery run completed successfully
[ ] recovery_of_run_id points to the failed run
[ ] Previously failed step is now successful
[ ] Quality gate passes
[ ] Reconciliation is acceptable
[ ] Freshness is acceptable
[ ] No unexpected rejected-row increase
[ ] Runtime lineage is consistent where telemetry exists
[ ] No new critical/open alert was generated
[ ] Pipeline output is usable
```

For code changes, also run the automated regression suite before declaring the incident fully closed.

---

# Alert lifecycle

## Acknowledge

Use when investigation has started:

```powershell
python scripts/07_manage_alerts.py acknowledge <ALERT_ID>
```

Expected transition:

```text
OPEN -> ACKNOWLEDGED
```

Repeated acknowledgement is idempotent.

## Resolve

Resolve only after recovery/fix verification:

```powershell
python scripts/07_manage_alerts.py resolve <ALERT_ID>
```

Expected transition:

```text
ACKNOWLEDGED -> RESOLVED
```

An `OPEN` alert cannot skip acknowledgement and go directly to `RESOLVED`.

If the same incident fingerprint recurs after resolution, monitoring may reopen the alert rather than silently treating the prior resolution as permanent.

---

# Scenario playbooks

## A. Missing source file

### Evidence

Look for a failed `LOAD_RAW_DATA` step and source-file error evidence.

### Action

1. Verify the expected path and configured filename.
2. Restore or correct the required source file.
3. Do not substitute an unrelated file merely to make the run pass.
4. Run declared recovery if the failed run is eligible.
5. Verify ingestion, quality, and freshness.

---

## B. Schema drift

### Evidence

Look for a failed `LOAD_RAW_DATA` step with a structural contract error such as missing or unexpected columns.

### Action

1. Compare source headers to the expected data contract.
2. Determine whether the producer changed legitimately or the file is malformed.
3. Update the contract only when the new schema is intentional.
4. Do not silently ignore unknown columns without a design decision.
5. Recover and verify.

---

## C. Invalid or orphaned source records

### Evidence

Use rejected-source evidence and quality checks.

Look for:

```text
DIRECT_RUN_ID
rejection_reason
rejected_column
source_row_number
```

### Action

1. Determine whether quarantine is expected behavior.
2. Confirm invalid records did not enter core tables.
3. Confirm valid records still loaded.
4. Assess whether rejection count/rate breaches policy.
5. Correct the source or rule only when necessary.
6. Recover and verify if the pipeline failed.

---

## D. Database lock / transient database failure

### Evidence

Look for error text such as:

```text
database is locked
database is busy
temporarily unavailable
timeout
```

The pipeline includes bounded retry behavior for retryable database operations.

### Action

1. Identify the process holding the database.
2. Avoid destructive deletion of SQLite database files.
3. Allow the built-in bounded retry to operate.
4. If retries are exhausted, remove the lock cause.
5. Run declared recovery when eligible.
6. Verify database integrity and pipeline success.

---

## E. Stale data

### Evidence

Use freshness checks plus the current watermark state.

Possible freshness states include:

```text
FRESH
STALE_DATA
NOT_LOADED
```

### Action

1. Identify the dataset with stale or missing load state.
2. Trace its upstream ingestion/transformation step.
3. Determine whether the cause is scheduling, ingestion failure, source delay, or another evidence-supported reason.
4. Restore data flow.
5. Recover if appropriate.
6. Verify current freshness.

Do not call `STALE_DATA` the root cause unless no deeper cause can be established.

---

## F. Quality-gate failure

### Evidence

Inspect:

```text
CRITICAL
ERROR
WARNING
```

and the corresponding check file / audit evidence.

### Action

1. Identify the failed quality rule.
2. Measure issue count and rate.
3. Determine whether the issue is source-related, transformation-related, or a valid business exception.
4. Do not weaken thresholds merely to force a green run.
5. Correct the cause.
6. Recover and re-run quality checks.

---

## G. SLA breach

### Evidence

Inspect:

```text
duration_seconds
sla_threshold_seconds
sla_status
```

### Action

1. Determine which step exceeded its threshold.
2. Separate performance symptoms from functional failures.
3. Check whether the run still completed successfully.
4. Investigate input volume, locking, query plan, or another evidence-supported bottleneck.
5. Optimize and benchmark where appropriate.
6. Verify the step returns within the expected threshold.

---

# Incident closure record

Use this template when closing an incident.

```markdown
## Incident

- Incident run_id:
- Alert ID:
- Detected at:
- Pipeline mode:
- Failed step:
- Error type:
- Error message:

## Impact

- Affected data:
- Rows processed:
- Rows rejected:
- Freshness impact:
- Business/consumer impact:

## Evidence

- Pipeline audit:
- Step log:
- SLA metrics:
- Rejected-source evidence:
- Runtime lineage:
- Quality/reconciliation:
- Watermark/current freshness:

## RCA

- Root cause:
- Contributing factors:
- Why the evidence supports this conclusion:

## Fix

- Change applied:
- Files/config/data affected:

## Recovery

- Recovery command:
- Recovery run_id:
- recovery_of_run_id:
- Recovery status:

## Verification

- Pipeline:
- Quality:
- Reconciliation:
- Freshness:
- Regression tests:
- Alerts:

## Closure

- Alert status:
- Closed at:
- Follow-up/prevention:
```

---

# What not to do

Do not:

- guess a root cause from the final exception alone,
- overwrite the failed run's audit history,
- delete the database as a first response,
- bypass the quality gate to make the pipeline green,
- claim time-correlated evidence is durable run-linked evidence,
- claim a later normal run is a recovery without `recovery_of_run_id`,
- use a standalone quality failure as `--recovery-of`,
- resolve an alert before verification,
- expose private source data in incident screenshots, logs, README content, or Git commits.

---

# Definition of incident resolved

An incident is resolved only when the evidence supports all applicable conditions:

```text
Root cause identified
        +
Corrective action applied
        +
Pipeline/recovery run successful
        +
Data quality verified
        +
Freshness/reconciliation verified
        +
Recovery linkage verified when recovery was used
        +
Alert lifecycle completed
        +
Evidence retained for RCA
```

A green process exit by itself is not sufficient evidence of incident resolution.

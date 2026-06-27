# Loop Engineering

## Purpose

Loop engineering defines how Hidden Jobs Worker should run repeatedly, observe results, and improve source quality without introducing uncontrolled behavior.

## Core Loop

```text
Select enabled source
        |
        v
Create run ID
        |
        v
Discover raw jobs
        |
        v
Normalize jobs
        |
        v
Submit batches
        |
        v
Record outcomes
        |
        v
Review metrics and adjust sources
```

## Run Identity

Every source execution must have a run ID. The run ID should include:

- Timestamp.
- Source key.
- Optional worker instance identifier.

Run IDs must be propagated to ingestion requests and logs.

## Scheduling

The worker should support source-level scheduling intent, but MVP execution may be triggered by a process scheduler, container job, or manual command.

Scheduling should account for:

- Source priority.
- Source update frequency.
- Rate limits.
- Recent failure history.
- Maintenance windows.

## Backoff and Retry

Retries should be bounded and targeted.

Retry candidates:

- Temporary network errors.
- HTTP 429 with backoff.
- HTTP 500, 502, 503, or 504.

Do not retry indefinitely. Do not retry validation errors without a code or data change.

## Failure Handling

Each failure should be classified and attached to the source run.

Minimum categories:

- `source_unavailable`.
- `source_blocked`.
- `source_contract_changed`.
- `parse_error`.
- `normalization_error`.
- `ingestion_auth_error`.
- `ingestion_validation_error`.
- `ingestion_transient_error`.
- `unexpected_error`.

## Metrics

Track at minimum:

- Sources attempted.
- Sources succeeded.
- Sources failed.
- Jobs discovered.
- Jobs normalized.
- Jobs submitted.
- Jobs accepted.
- Jobs rejected.
- Jobs marked duplicate.
- Run duration.
- Request count per source.
- Retry count.

## Quality Review Loop

Source performance should be reviewed using:

- Field completeness.
- Acceptance rate.
- Duplicate rate.
- Rejection reasons.
- Parse stability.
- Source availability.

Poor-performing sources should be disabled or moved to investigation until corrected.

## Guardrails

The worker must have safeguards for:

- Maximum jobs per source run.
- Maximum request count per source run.
- Maximum batch size.
- Request timeout.
- Total run timeout.
- Per-source concurrency limit.
- Global concurrency limit.

## Operational States

Recommended source states:

- `candidate`: identified but not implemented.
- `disabled`: implemented but not active.
- `testing`: allowed in controlled test runs.
- `active`: included in scheduled runs.
- `paused`: temporarily stopped due to quality, security, or availability concerns.
- `retired`: no longer maintained.

## Human Review

Human review is required when:

- A new source is added.
- A source changes access behavior.
- Rejection rate spikes.
- Duplicate rate spikes.
- Source terms or robots guidance changes.
- A source appears to block or throttle the worker.

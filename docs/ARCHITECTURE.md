# Hidden Jobs Worker Architecture

## Overview

Hidden Jobs Worker is a Python background service that discovers job postings, normalizes them, and sends them to a Spring Boot internal ingestion API. The worker does not write directly to the database.

```text
+----------------+      HTTPS + X-Worker-Token      +-------------------------------+      SQL      +-----------------+
| Python Worker  | --------------------------------> | Spring Boot Internal API      | ------------> | Neon PostgreSQL |
+----------------+                                   +-------------------------------+               +-----------------+
```

## Responsibilities

### Python Worker

- Manage source registry and source run lifecycle.
- Fetch or scrape supported job sources.
- Extract raw job data.
- Normalize records into the ingestion contract.
- Submit bounded batches to the ingestion API.
- Emit structured run logs and metrics.

### Spring Boot Internal Ingestion API

- Authenticate worker requests using `X-Worker-Token`.
- Validate ingestion payloads.
- Apply deduplication and persistence rules.
- Store canonical jobs in Neon PostgreSQL.
- Return accepted, rejected, and error results to the worker.

### Neon PostgreSQL

- Persist canonical company, source, job, and ingestion metadata records.
- Enforce database constraints required by the backend.

## Logical Worker Components

```text
Scheduler / Runner
        |
        v
Source Registry
        |
        v
Source Adapter -> Raw Job Records
        |
        v
Normalizer -> Ingestion Payload
        |
        v
Batcher -> Ingestion Client
        |
        v
Run Reporter / Metrics
```

## Component Boundaries

### Source Registry

Tracks configured sources and source metadata:

- Source name.
- Source type.
- Base URL.
- Adapter name.
- Enabled status.
- Schedule intent.
- Compliance notes.

### Source Adapter

Encapsulates source-specific discovery and extraction. Adapters should return raw records plus provenance instead of directly producing API payloads.

### Normalizer

Maps raw source records to the canonical ingestion contract. It should handle field cleanup, location normalization hints, employment type hints, and stable source references.

### Batcher

Groups normalized jobs into bounded API requests. Batch limits should be configurable.

### Ingestion Client

Sends HTTPS requests to the Spring Boot ingestion API with:

- `Content-Type: application/json`.
- `X-Worker-Token: <runtime secret>`.
- Request timeout.
- Bounded retry policy for transient failures.

### Run Reporter

Records structured outcomes for each source run. This data should support debugging, alerting, and quality review.

## Data Flow

1. Runner starts a source run and creates a run ID.
2. Source registry provides enabled source configuration.
3. Source adapter discovers raw job records.
4. Normalizer converts raw records to ingestion payload items.
5. Batcher creates bounded job batches.
6. Ingestion client sends batches to the Spring Boot API.
7. Worker records accepted, rejected, failed, and skipped counts.

## Security Model

The MVP uses a shared worker token:

- Requests must use HTTPS.
- Requests must include `X-Worker-Token`.
- Token value must come from runtime configuration.
- Token must never be logged or committed.

Future options may include mTLS, short-lived service tokens, signed requests, or private networking.

## Deployment Assumptions

- Worker runs as a scheduled process, container, or job runner.
- Worker has outbound HTTPS access to the ingestion API.
- Worker secrets are provided by environment variables or a secret manager.
- Database access is owned by the Spring Boot service, not the worker.

## Failure Isolation

- One source failure should not abort all sources.
- One malformed job should not discard a whole source run when item-level rejection is possible.
- Transient ingestion failures should be retried within strict limits.
- Persistent failures should be surfaced to monitoring and logs.

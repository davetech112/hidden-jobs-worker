# Hidden Jobs Worker Software Requirements Specification

## 1. Purpose

Hidden Jobs Worker is a Python-based background worker that discovers job postings from applicant tracking system boards, company career pages, and remote job sources. It normalizes discovered jobs and sends them to a Spring Boot internal ingestion API for persistence in Neon PostgreSQL.

This document defines the product scope and requirements for the worker. It does not specify implementation details.

## 2. System Context

The MVP architecture is:

```text
Python Worker -> Spring Boot Internal Ingestion API -> Neon PostgreSQL
```

The worker is responsible for discovery, source-specific extraction, normalization, deduplication support, and delivery to the ingestion API. The Spring Boot service owns validation, persistence, API security, and downstream database writes.

## 3. Goals

- Discover hidden or less-visible job postings from supported sources.
- Normalize jobs into a stable ingestion contract.
- Send job batches to the Spring Boot ingestion API over HTTPS.
- Support repeatable source runs with observable outcomes.
- Avoid committing or exposing secrets.
- Keep source adapters isolated so new sources can be added safely.

## 4. Non-Goals

- The worker will not write directly to PostgreSQL.
- The worker will not expose a public API.
- The worker will not implement user-facing job search features.
- The worker will not bypass website access controls, authentication walls, CAPTCHAs, or robots restrictions.
- The worker will not store long-term canonical job data outside the ingestion API and database.
- The worker will not implement code in this documentation phase.

## 5. Users and Stakeholders

- Platform backend team: owns the Spring Boot ingestion API and database.
- Data engineering team: owns source discovery, extraction quality, and normalization.
- Security reviewers: validate token handling, source access behavior, and secret hygiene.
- QA reviewers: validate source coverage, contracts, retries, and failure handling.

## 6. Functional Requirements

### FR-1 Source Registry

The worker must maintain a registry of supported sources, including source type, base URL, extraction strategy, schedule intent, and enabled status.

### FR-2 Source Discovery

The worker must discover jobs from:

- ATS-hosted boards.
- Company career pages.
- Remote job sources.

Each source adapter must produce raw job records with enough provenance to support debugging and deduplication.

### FR-3 Normalization

The worker must normalize raw jobs into the ingestion payload defined in `docs/INGESTION_CONTRACT.md`.

### FR-4 Ingestion Delivery

The worker must submit normalized jobs to the Spring Boot internal ingestion API using HTTPS and the `X-Worker-Token` shared secret header.

### FR-5 Batch Processing

The worker should send jobs in bounded batches to prevent oversized requests and isolate partial failures.

### FR-6 Idempotency Support

The worker must include stable source identifiers where available. When no source identifier exists, it must include enough stable fields for the ingestion API to derive deduplication keys.

### FR-7 Error Handling

The worker must classify failures at minimum as:

- Source unavailable.
- Parse or extraction failure.
- Contract validation failure.
- Ingestion API failure.
- Authentication or authorization failure.

### FR-8 Observability

The worker must record structured run information, including source name, run ID, discovered count, normalized count, submitted count, rejected count, duration, and failure reason.

### FR-9 Configuration

The worker must read environment-specific configuration from environment variables or runtime secret management. Secrets must never be committed.

## 7. Non-Functional Requirements

### Reliability

- Source failures must not stop unrelated sources from running.
- Ingestion retries must use bounded retry policies.
- The worker must avoid infinite loops or unbounded memory growth.

### Security

- The MVP authentication mechanism is `X-Worker-Token` over HTTPS.
- Secrets must be injected at runtime and excluded from source control.
- Logs must not include tokens, credentials, or full sensitive headers.

### Maintainability

- Source-specific extraction logic must be isolated by adapter.
- Shared normalization and delivery behavior must be centralized.
- Contracts must be versioned when breaking changes are introduced.

### Compliance and Website Access

- The worker must respect source access restrictions and avoid abusive request patterns.
- The worker must not evade rate limits, authentication, CAPTCHAs, or other access controls.

## 8. Assumptions

- The Spring Boot ingestion API exists or will be built separately.
- The ingestion API owns final validation and persistence.
- Neon PostgreSQL is reachable only through the Spring Boot backend for this workflow.
- The worker runs in a controlled environment with HTTPS egress to the ingestion API.

## 9. Open Questions

- Which ATS platforms are in MVP scope?
- What source scheduling mechanism will be used for production runs?
- What duplicate resolution policy will the ingestion API apply?
- What maximum batch size and request timeout should be enforced?
- What monitoring platform will receive worker metrics and alerts?

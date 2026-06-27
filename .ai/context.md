# AI Context

## Project

Hidden Jobs Worker is a Python worker that discovers hidden jobs from ATS boards, company career pages, and remote job sources. It sends normalized jobs to a Spring Boot internal ingestion API. The backend persists data in Neon PostgreSQL.

## Architecture

```text
Python Worker -> Spring Boot Internal Ingestion API -> Neon PostgreSQL
```

The worker must not write directly to Neon PostgreSQL. All persistence goes through the Spring Boot ingestion API.

## MVP Security

Use a shared secret sent as `X-Worker-Token` over HTTPS. The token must come from runtime configuration and must never be committed or logged.

## Current Phase

Documentation and agent structure only. Do not implement worker code yet.

## Primary Documents

- `docs/SRS.md`: requirements.
- `docs/ARCHITECTURE.md`: system architecture.
- `docs/SOURCE_STRATEGY.md`: source selection and adapter strategy.
- `docs/INGESTION_CONTRACT.md`: worker-to-backend API contract.
- `docs/LOOP_ENGINEERING.md`: run loop, retries, observability, and guardrails.

## Agent Files

- `agents/PYTHON_ENGINEER.md`.
- `agents/SCRAPER_ENGINEER.md`.
- `agents/QE_REVIEWER.md`.
- `agents/SENIOR_REVIEWER.md`.
- `agents/SECURITY_REVIEWER.md`.

# Hidden Jobs Worker

Hidden Jobs Worker is a Python worker blueprint for discovering hidden jobs from ATS boards, company career pages, and remote job sources. The worker sends normalized jobs to a Spring Boot internal ingestion API, which persists data in Neon PostgreSQL.

```text
Python Worker -> Spring Boot Internal Ingestion API -> Neon PostgreSQL
```

## Current Status

This repository contains the initial Python worker foundation:

- Typed configuration loading from environment variables.
- Structured logging setup with sensitive header redaction helpers.
- Pydantic models for the ingestion contract.
- Spring Boot ingestion client for `POST /api/internal/jobs/ingest`.
- Source adapter interface and a Remotive adapter.
- CLI command for manually running one source.
- Unit tests and GitHub Actions CI for Ruff and Pytest.

Scheduling, deployment, browser automation, and additional source adapters are intentionally out of scope for this foundation.

## Setup

Use Python 3.12 or 3.13.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Use `.env.example` as a reference for required runtime variables, then provide values through your execution environment:

```bash
export SPRING_API_BASE_URL=https://api.example.com
export WORKER_INGEST_TOKEN=replace-with-runtime-secret
```

Do not commit `.env` files or real token values. The worker reads runtime configuration from environment variables.

## Manual Source Run

Fetch and parse Remotive jobs without sending them to the ingestion API:

```bash
hidden-jobs-worker run-source remotive --dry-run
```

Fetch Remotive jobs and submit bounded batches to Spring Boot:

```bash
hidden-jobs-worker run-source remotive
```

The worker sends normalized job batches to:

```text
POST {SPRING_API_BASE_URL}/api/internal/jobs/ingest
```

Authentication uses the `X-Worker-Token` header populated from `WORKER_INGEST_TOKEN`.

## Checks

```bash
ruff check .
pytest
git diff --check
```

## Documentation

- `docs/SRS.md`: product scope and requirements.
- `docs/ARCHITECTURE.md`: system architecture and component boundaries.
- `docs/SOURCE_STRATEGY.md`: source selection, compliance, and adapter strategy.
- `docs/INGESTION_CONTRACT.md`: worker-to-ingestion API contract.
- `docs/LOOP_ENGINEERING.md`: run loop, retries, metrics, and guardrails.

## AI Agent Instructions

- `agents/PYTHON_ENGINEER.md`: Python worker implementation guidance.
- `agents/SCRAPER_ENGINEER.md`: source adapter and scraping guidance.
- `agents/QE_REVIEWER.md`: quality engineering review guidance.
- `agents/SENIOR_REVIEWER.md`: senior engineering review guidance.
- `agents/SECURITY_REVIEWER.md`: security review guidance.
- `.ai/context.md`: shared project context.
- `.ai/worker-rules.md`: project rules for future AI-assisted work.
- `.ai/security-checklist.md`: release and deployment security checklist.

## Security

The MVP authentication model uses a shared secret in the `X-Worker-Token` header over HTTPS.

Never commit secrets. Use runtime configuration or a secret manager for tokens, URLs, and environment-specific credentials.

## Implementation Boundary

The worker must not write directly to Neon PostgreSQL. All job ingestion must flow through the Spring Boot internal ingestion API.

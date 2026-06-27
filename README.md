# Hidden Jobs Worker

Hidden Jobs Worker is a Python worker blueprint for discovering hidden jobs from ATS boards, company career pages, and remote job sources. The worker sends normalized jobs to a Spring Boot internal ingestion API, which persists data in Neon PostgreSQL.

```text
Python Worker -> Spring Boot Internal Ingestion API -> Neon PostgreSQL
```

## Current Status

This repository currently contains project documentation and AI agent instructions only. Worker implementation has not started.

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

# Worker Rules

## Scope Rules

- Build a Python worker only when implementation is explicitly requested.
- Do not implement code during the documentation-only phase.
- Keep the worker separate from the Spring Boot backend.
- Do not write directly to Neon PostgreSQL.
- Send normalized jobs only through the internal ingestion API.

## Contract Rules

- Follow `docs/INGESTION_CONTRACT.md`.
- Include source provenance for every job.
- Include stable source job IDs when available.
- Treat breaking contract changes as versioned changes.
- Keep batch sizes bounded.

## Source Rules

- Keep source adapters isolated.
- Respect source access restrictions.
- Do not bypass login, CAPTCHA, paywalls, or access controls.
- Do not evade rate limits.
- Use conservative request behavior.
- Disable sources that become unstable, blocked, or non-compliant.

## Security Rules

- Use `X-Worker-Token` over HTTPS for MVP.
- Read secrets from runtime configuration only.
- Never commit secrets.
- Never log secrets.
- Redact sensitive headers in logs.
- Keep `.env` files out of source control.

## Engineering Rules

- Prefer simple, testable components.
- Use structured data models for ingestion payloads.
- Keep retries bounded.
- Classify failures explicitly.
- Emit structured logs and useful metrics.
- Add tests with implementation changes.

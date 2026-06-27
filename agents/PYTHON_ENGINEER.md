# Python Engineer Agent

## Mission

Design and implement Python worker internals for Hidden Jobs Worker when implementation begins. Do not implement code during the documentation-only phase.

## Responsibilities

- Define worker package structure.
- Implement source run orchestration.
- Implement configuration loading.
- Implement normalization pipeline.
- Implement ingestion client.
- Implement structured logging and metrics hooks.
- Add focused unit tests for shared worker behavior.

## Operating Rules

- Follow the architecture and contracts in `docs/`.
- Keep source adapters isolated from shared worker core logic.
- Read secrets only from runtime configuration.
- Never hard-code or commit secrets.
- Avoid direct database access.
- Keep retries bounded.
- Prefer typed data models for contracts.
- Treat API contract changes as cross-service changes.

## Required Handoff Checks

- Contract fields match `docs/INGESTION_CONTRACT.md`.
- Token is sent only as `X-Worker-Token` over HTTPS.
- Logs redact sensitive headers and configuration.
- Failure classifications are explicit.
- Tests cover normal and failure paths.

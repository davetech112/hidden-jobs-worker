# Security Checklist

Use this checklist before releasing or deploying Hidden Jobs Worker changes.

## Secrets

- [ ] No secrets are committed.
- [ ] `.env` and local secret files are ignored.
- [ ] Worker token is read from runtime configuration.
- [ ] Worker token is not printed in logs.
- [ ] Sensitive headers are redacted in errors and debug output.

## Transport

- [ ] Ingestion API calls use HTTPS outside local development.
- [ ] Worker sends authentication in `X-Worker-Token`.
- [ ] Token is not sent to third-party job sources.
- [ ] Request timeouts are configured.
- [ ] Retries are bounded.

## Source Access

- [ ] Source access behavior has been reviewed.
- [ ] Worker does not bypass authentication, CAPTCHAs, paywalls, or access controls.
- [ ] Worker does not evade rate limits.
- [ ] Request pacing is conservative.
- [ ] Blocked or throttled sources are paused or disabled.

## Data Handling

- [ ] Raw payload storage avoids secrets and excessive page content.
- [ ] Logs avoid sensitive headers and credentials.
- [ ] Error reports avoid leaking tokens.
- [ ] Test fixtures do not contain real secrets.

## Architecture

- [ ] Worker does not write directly to Neon PostgreSQL.
- [ ] Spring Boot API owns validation and persistence.
- [ ] Contract version is explicit.
- [ ] Cross-service contract changes are reviewed.

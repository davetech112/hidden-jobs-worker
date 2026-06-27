# Source Strategy

## Purpose

This document defines how Hidden Jobs Worker should select, classify, access, and evaluate job sources.

## Source Classes

### ATS Boards

Applicant tracking system boards expose structured or semi-structured job listings for one or more companies.

Expected traits:

- Stable company or board identifiers.
- Listing pages with predictable fields.
- Job detail URLs.
- Possible structured JSON endpoints.

Examples of ATS categories to evaluate:

- Greenhouse-style boards.
- Lever-style boards.
- Ashby-style boards.
- Workable-style boards.
- SmartRecruiters-style boards.

### Company Career Pages

Company-owned career pages may be custom-built or embedded from ATS providers.

Expected traits:

- Less consistent markup.
- Higher need for source-specific adapters.
- Stronger requirement for compliance review.
- Potential canonical URLs suitable for deduplication.

### Remote Job Sources

Remote-focused sources list distributed roles across many companies.

Expected traits:

- Broader coverage.
- Higher duplicate risk.
- Potentially stricter terms of use.
- Need for source attribution.

## Source Selection Criteria

Prioritize sources that have:

- Clear public access.
- Stable structure or API-like responses.
- Useful job details.
- Acceptable terms and access behavior.
- High signal for hidden or early-stage postings.
- Low duplication against existing sources.

Avoid sources that require:

- Login or private access.
- CAPTCHA solving.
- Rate-limit evasion.
- Browser fingerprint bypass.
- Scraping behind explicit prohibitions.

## Source Metadata

Each source should have a documented record containing:

- `source_key`: stable internal identifier.
- `source_name`: human-readable name.
- `source_type`: `ats_board`, `company_career_page`, or `remote_job_source`.
- `base_url`: starting URL.
- `adapter`: extraction strategy.
- `enabled`: runtime flag.
- `priority`: operational priority.
- `schedule`: intended frequency.
- `rate_limit`: request pacing guidance.
- `compliance_notes`: terms, robots, or access constraints.
- `owner`: person or team responsible for review.

## Adapter Strategy

Adapters should be small and source-specific. Common behavior should live in shared utilities only when it is genuinely reusable across multiple sources.

Adapter output should include:

- Raw title.
- Raw company.
- Raw location.
- Raw employment type.
- Raw compensation when available.
- Job detail URL.
- Source job ID when available.
- Posted date when available.
- Description or description URL.
- Extraction timestamp.
- Provenance metadata.

## Quality Scoring

Source quality should be evaluated using:

- Discovery count.
- Valid normalization rate.
- Duplicate rate.
- Rejection rate from ingestion API.
- Field completeness.
- Source stability over time.
- Operational failure rate.

## Request Behavior

The worker should:

- Use conservative request pacing.
- Use clear user-agent identification if approved by the project.
- Respect robots and terms decisions.
- Avoid high-concurrency scraping.
- Stop or back off when sources return blocking, throttling, or error signals.

## Source Lifecycle

1. Candidate source identified.
2. Compliance and access review completed.
3. Adapter design documented.
4. Source added as disabled.
5. Test run executed in controlled environment.
6. Results reviewed for quality and compliance.
7. Source enabled for scheduled runs.
8. Source monitored and periodically revalidated.

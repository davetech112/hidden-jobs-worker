# Ingestion Contract

## Purpose

This document defines the expected contract between Hidden Jobs Worker and the Spring Boot internal ingestion API.

The worker sends normalized job records. The Spring Boot service authenticates, validates, deduplicates, persists, and reports item-level outcomes.

## Transport

- Protocol: HTTPS.
- Format: JSON.
- Authentication: `X-Worker-Token` shared secret header.
- Content type: `application/json`.

## MVP Endpoint

The exact route is owned by the Spring Boot service. Recommended MVP route:

```text
POST /internal/ingestion/jobs
```

## Required Headers

```text
Content-Type: application/json
X-Worker-Token: <runtime secret>
```

The worker must never log the token value.

## Request Envelope

```json
{
  "contractVersion": "1.0",
  "worker": {
    "name": "hidden-jobs-worker",
    "version": "0.0.0",
    "runId": "2026-06-27T21:00:00Z-source-key"
  },
  "source": {
    "key": "example-source",
    "name": "Example Source",
    "type": "ats_board",
    "baseUrl": "https://example.com/jobs"
  },
  "jobs": []
}
```

## Job Item

```json
{
  "sourceJobId": "job-123",
  "sourceUrl": "https://example.com/jobs/job-123",
  "title": "Backend Engineer",
  "companyName": "Example Inc",
  "locationText": "Remote, United States",
  "remoteType": "remote",
  "employmentType": "full_time",
  "descriptionText": "Plain-text job description when available.",
  "descriptionHtml": null,
  "postedAt": "2026-06-27T00:00:00Z",
  "expiresAt": null,
  "compensation": {
    "minAmount": 120000,
    "maxAmount": 160000,
    "currency": "USD",
    "interval": "year"
  },
  "tags": ["python", "backend"],
  "raw": {
    "sourcePayloadRef": "optional-debug-reference"
  }
}
```

## Field Requirements

### Envelope

| Field | Required | Notes |
| --- | --- | --- |
| `contractVersion` | Yes | Starts at `1.0`. |
| `worker.name` | Yes | Stable worker name. |
| `worker.version` | Yes | Worker release version or build identifier. |
| `worker.runId` | Yes | Unique source run identifier. |
| `source.key` | Yes | Stable source identifier. |
| `source.name` | Yes | Human-readable source name. |
| `source.type` | Yes | `ats_board`, `company_career_page`, or `remote_job_source`. |
| `source.baseUrl` | Yes | Source starting URL. |
| `jobs` | Yes | Non-empty array for submission requests. |

### Job

| Field | Required | Notes |
| --- | --- | --- |
| `sourceJobId` | Preferred | Required when source provides stable IDs. |
| `sourceUrl` | Yes | Canonical job detail URL when available. |
| `title` | Yes | Normalized title text. |
| `companyName` | Yes | Company name as presented or mapped. |
| `locationText` | Preferred | Raw or normalized location display text. |
| `remoteType` | Optional | `remote`, `hybrid`, `onsite`, or `unknown`. |
| `employmentType` | Optional | `full_time`, `part_time`, `contract`, `internship`, `temporary`, or `unknown`. |
| `descriptionText` | Preferred | Plain text description. |
| `descriptionHtml` | Optional | Sanitization is owned by the backend if stored. |
| `postedAt` | Optional | ISO-8601 timestamp when available. |
| `expiresAt` | Optional | ISO-8601 timestamp when available. |
| `compensation` | Optional | Include only when source provides credible compensation. |
| `tags` | Optional | Lowercase normalized hints. |
| `raw` | Optional | Must not contain secrets or excessive full-page content. |

## Response Envelope

Recommended response:

```json
{
  "runId": "2026-06-27T21:00:00Z-source-key",
  "accepted": 24,
  "rejected": 1,
  "duplicates": 3,
  "items": [
    {
      "sourceUrl": "https://example.com/jobs/job-123",
      "status": "accepted",
      "jobId": "internal-job-id",
      "reason": null
    }
  ]
}
```

## Status Codes

| Status | Meaning |
| --- | --- |
| `200 OK` | Batch processed with item-level outcomes. |
| `202 Accepted` | Batch accepted for asynchronous processing. |
| `400 Bad Request` | Request envelope or schema is invalid. |
| `401 Unauthorized` | Missing or invalid worker token. |
| `413 Payload Too Large` | Batch size is too large. |
| `429 Too Many Requests` | Worker should back off. |
| `500+` | Backend or infrastructure error. |

## Deduplication Inputs

The worker should provide as many stable identifiers as possible:

- Source key.
- Source job ID.
- Source URL.
- Company name.
- Title.
- Location text.
- Posted date.

The backend owns final deduplication policy.

## Contract Evolution

Breaking changes require a new `contractVersion`. The worker and backend must support an explicit compatibility window during migrations.

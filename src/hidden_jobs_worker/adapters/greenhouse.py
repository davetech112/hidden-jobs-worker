from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import httpx

from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.models import AtsType, CompanyRecord, JobRecord, RemoteType


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)

    def text(self) -> str:
        return " ".join(self.parts)


class GreenhouseAdapter(AtsAdapter):
    ats_type = AtsType.GREENHOUSE
    source_name = "GREENHOUSE"
    base_url = "https://boards-api.greenhouse.io"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, company: CompanyRecord) -> list[JobRecord]:
        if not company.ats_slug:
            raise ValueError(f"company {company.id} is missing atsSlug")
        response = self._client.get(
            f"{self.base_url}/v1/boards/{company.ats_slug}/jobs",
            params={"content": "true"},
        )
        response.raise_for_status()
        return self.parse_jobs(company, response.json())

    def parse_jobs(self, company: CompanyRecord, payload: Any) -> list[JobRecord]:
        if not isinstance(payload, dict) or not isinstance(payload.get("jobs"), list):
            raise ValueError("Greenhouse payload missing jobs array")
        return [self._parse_job(company, job) for job in payload["jobs"] if isinstance(job, dict)]

    def _parse_job(self, company: CompanyRecord, raw_job: dict[str, Any]) -> JobRecord:
        content = _optional_str(raw_job.get("content"))
        return JobRecord(
            sourceName=self.source_name,
            sourceJobId=str(raw_job["id"]) if raw_job.get("id") is not None else None,
            sourceUrl=_greenhouse_job_url(company, raw_job),
            title=raw_job.get("title") or "",
            companyName=company.name,
            locationText=_greenhouse_location(raw_job.get("location")),
            remoteType=_remote_type_from_location(_greenhouse_location(raw_job.get("location"))),
            descriptionText=_html_to_text(content) if content else None,
            descriptionHtml=content,
            postedAt=_parse_datetime(raw_job.get("updated_at")),
            raw={"source": self.source_name, "companyId": company.id},
        )


def _greenhouse_job_url(company: CompanyRecord, raw_job: dict[str, Any]) -> str:
    url = raw_job.get("absolute_url")
    if isinstance(url, str) and url.strip():
        return url
    if company.ats_slug and raw_job.get("id") is not None:
        return f"https://boards.greenhouse.io/{company.ats_slug}/jobs/{raw_job['id']}"
    raise ValueError("Greenhouse job missing canonical URL")


def _greenhouse_location(value: Any) -> str | None:
    if isinstance(value, dict):
        name = value.get("name")
        return name if isinstance(name, str) and name.strip() else None
    return value if isinstance(value, str) and value.strip() else None


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _remote_type_from_location(value: str | None) -> RemoteType:
    if value and "remote" in value.lower():
        return RemoteType.REMOTE
    return RemoteType.UNKNOWN

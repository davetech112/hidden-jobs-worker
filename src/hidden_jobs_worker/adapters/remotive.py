from datetime import datetime
from html.parser import HTMLParser
from typing import Any

import httpx

from hidden_jobs_worker.adapters.base import SourceAdapter, SourceMetadata
from hidden_jobs_worker.models import EmploymentType, JobRecord, RemoteType, SourceType


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


class RemotiveAdapter(SourceAdapter):
    metadata = SourceMetadata(
        key="remotive",
        name="Remotive",
        type=SourceType.REMOTE_JOB_SOURCE,
        base_url="https://remotive.com/api/remote-jobs",
    )

    def __init__(
        self,
        api_url: str = "https://remotive.com/api/remote-jobs",
        client: httpx.Client | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        self.api_url = api_url
        self.metadata = SourceMetadata(
            key=self.metadata.key,
            name=self.metadata.name,
            type=self.metadata.type,
            base_url=api_url,
        )
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self) -> list[JobRecord]:
        response = self._client.get(self.api_url)
        response.raise_for_status()
        return self.parse_jobs(response.json())

    def parse_jobs(self, payload: dict[str, Any]) -> list[JobRecord]:
        jobs = payload.get("jobs")
        if not isinstance(jobs, list):
            raise ValueError("Remotive payload missing jobs array")
        return [self._parse_job(job) for job in jobs if isinstance(job, dict)]

    def _parse_job(self, raw_job: dict[str, Any]) -> JobRecord:
        description_html = _optional_str(raw_job.get("description"))
        return JobRecord(
            sourceJobId=str(raw_job["id"]) if raw_job.get("id") is not None else None,
            sourceUrl=raw_job.get("url") or raw_job.get("job_url"),
            title=raw_job.get("title") or "",
            companyName=raw_job.get("company_name") or "",
            locationText=raw_job.get("candidate_required_location"),
            remoteType=RemoteType.REMOTE,
            employmentType=_map_employment_type(raw_job.get("job_type")),
            descriptionText=_html_to_text(description_html) if description_html else None,
            descriptionHtml=description_html,
            postedAt=_parse_datetime(raw_job.get("publication_date")),
            tags=_parse_tags(raw_job.get("tags")),
            raw={
                "source": "remotive",
                "category": raw_job.get("category"),
                "salary": raw_job.get("salary"),
            },
        )


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


def _parse_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(tag) for tag in value]
    return []


def _map_employment_type(value: Any) -> EmploymentType:
    normalized = str(value or "").lower().replace("-", " ").replace("_", " ")
    if "full" in normalized:
        return EmploymentType.FULL_TIME
    if "part" in normalized:
        return EmploymentType.PART_TIME
    if "contract" in normalized or "freelance" in normalized:
        return EmploymentType.CONTRACT
    if "intern" in normalized:
        return EmploymentType.INTERNSHIP
    if "temporary" in normalized or "temp" in normalized:
        return EmploymentType.TEMPORARY
    return EmploymentType.UNKNOWN

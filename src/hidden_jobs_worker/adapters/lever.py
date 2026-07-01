from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

import httpx

from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.models import AtsType, CareerBoard, EmploymentType, JobRecord, RemoteType


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


class LeverAdapter(AtsAdapter):
    ats_type = AtsType.LEVER
    source_name = "LEVER"
    base_url = "https://api.lever.co"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if not career_board.ats_slug:
            raise ValueError(f"career board {career_board.board_id} is missing atsSlug")
        response = self._client.get(
            f"{self.base_url}/v0/postings/{career_board.ats_slug}",
            params={"mode": "json"},
        )
        response.raise_for_status()
        return self.parse_jobs(career_board, response.json())

    def parse_jobs(self, career_board: CareerBoard, payload: Any) -> list[JobRecord]:
        if not isinstance(payload, list):
            raise ValueError("Lever payload must be an array")
        return [self._parse_job(career_board, job) for job in payload if isinstance(job, dict)]

    def _parse_job(self, career_board: CareerBoard, raw_job: dict[str, Any]) -> JobRecord:
        raw_categories = raw_job.get("categories")
        categories = raw_categories if isinstance(raw_categories, dict) else {}
        description_html = _optional_str(raw_job.get("description"))
        description_text = _optional_str(raw_job.get("descriptionPlain"))
        parsed_description = description_text or (
            _html_to_text(description_html) if description_html else None
        )
        return JobRecord(
            sourceName=self.source_name,
            sourceType="ATS",
            sourceJobId=_optional_str(raw_job.get("id")),
            sourceUrl=_lever_job_url(career_board, raw_job),
            title=raw_job.get("text") or "",
            companyName=career_board.company_name,
            locationText=_optional_str(categories.get("location")),
            remoteType=_remote_type_from_location(categories.get("location")),
            employmentType=_map_employment_type(categories.get("commitment")),
            descriptionText=parsed_description,
            descriptionHtml=description_html,
            postedAt=_parse_created_at(raw_job.get("createdAt")),
            tags=_lever_tags(categories),
            raw={
                "source": self.source_name,
                "companyId": career_board.company_id,
                "boardId": career_board.board_id,
            },
        )


def _lever_job_url(career_board: CareerBoard, raw_job: dict[str, Any]) -> str:
    url = raw_job.get("hostedUrl") or raw_job.get("applyUrl")
    if isinstance(url, str) and url.strip():
        return url
    if career_board.ats_slug and raw_job.get("id"):
        return f"https://jobs.lever.co/{career_board.ats_slug}/{raw_job['id']}"
    raise ValueError("Lever job missing canonical URL")


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _parse_created_at(value: Any) -> datetime | None:
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000, tz=UTC)
    return None


def _remote_type_from_location(value: Any) -> RemoteType:
    if isinstance(value, str) and "remote" in value.lower():
        return RemoteType.REMOTE
    return RemoteType.UNKNOWN


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


def _lever_tags(categories: dict[str, Any]) -> list[str]:
    tags = []
    for key in ("team", "department", "commitment"):
        value = categories.get(key)
        if isinstance(value, str) and value.strip():
            tags.append(value)
    return tags

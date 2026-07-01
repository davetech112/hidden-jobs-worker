from datetime import datetime
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


class AshbyAdapter(AtsAdapter):
    ats_type = AtsType.ASHBY
    source_name = "ASHBY"
    base_url = "https://api.ashbyhq.com"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if not career_board.ats_slug:
            raise ValueError(f"career board {career_board.board_id} is missing atsSlug")
        response = self._client.get(
            f"{self.base_url}/posting-api/job-board/{career_board.ats_slug}"
        )
        response.raise_for_status()
        return self.parse_jobs(career_board, response.json())

    def parse_jobs(self, career_board: CareerBoard, payload: Any) -> list[JobRecord]:
        jobs = payload.get("jobs") if isinstance(payload, dict) else None
        if not isinstance(jobs, list):
            raise ValueError("Ashby payload missing jobs array")
        return [self._parse_job(career_board, job) for job in jobs if isinstance(job, dict)]

    def _parse_job(self, career_board: CareerBoard, raw_job: dict[str, Any]) -> JobRecord:
        description_html = _first_present_str(
            raw_job,
            ("descriptionHtml", "description_html", "description"),
        )
        description_text = _first_present_str(
            raw_job,
            ("descriptionPlain", "descriptionText", "description_plain"),
        )
        return JobRecord(
            sourceName=self.source_name,
            sourceType="ATS",
            sourceJobId=_optional_str(raw_job.get("id")),
            sourceUrl=_ashby_job_url(career_board, raw_job),
            title=_optional_str(raw_job.get("title")) or "",
            companyName=career_board.company_name,
            locationText=_location_text(raw_job),
            remoteType=_remote_type(_location_text(raw_job)),
            employmentType=_employment_type(_first_present(raw_job, ("employmentType", "type"))),
            descriptionText=description_text
            or (_html_to_text(description_html) if description_html else None),
            descriptionHtml=description_html,
            postedAt=_parse_datetime(_first_present(raw_job, ("publishedAt", "postedAt"))),
            tags=_tags(raw_job),
            raw={
                "source": self.source_name,
                "sourceType": "ATS",
                "companyId": career_board.company_id,
                "boardId": career_board.board_id,
            },
        )


def _ashby_job_url(career_board: CareerBoard, raw_job: dict[str, Any]) -> str:
    url = _first_present_str(raw_job, ("jobUrl", "job_url", "url"))
    if url:
        return url
    if career_board.ats_slug and raw_job.get("id"):
        return f"https://jobs.ashbyhq.com/{career_board.ats_slug}/{raw_job['id']}"
    raise ValueError("Ashby job missing canonical URL")


def _location_text(raw_job: dict[str, Any]) -> str | None:
    location = raw_job.get("location")
    if isinstance(location, str) and location.strip():
        return location
    if isinstance(location, dict):
        for key in ("name", "displayName", "location"):
            value = location.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return _first_present_str(raw_job, ("locationName", "locationText"))


def _first_present(raw_job: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = raw_job.get(key)
        if value is not None:
            return value
    return None


def _first_present_str(raw_job: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = _optional_str(raw_job.get(key))
        if value:
            return value
    return None


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


def _remote_type(value: str | None) -> RemoteType:
    if value and "remote" in value.lower():
        return RemoteType.REMOTE
    return RemoteType.UNKNOWN


def _employment_type(value: Any) -> EmploymentType:
    normalized = str(value or "").lower().replace("-", " ").replace("_", " ")
    if "full" in normalized:
        return EmploymentType.FULL_TIME
    if "part" in normalized:
        return EmploymentType.PART_TIME
    if "contract" in normalized:
        return EmploymentType.CONTRACT
    if "intern" in normalized:
        return EmploymentType.INTERNSHIP
    if "temporary" in normalized or "temp" in normalized:
        return EmploymentType.TEMPORARY
    return EmploymentType.UNKNOWN


def _tags(raw_job: dict[str, Any]) -> list[str]:
    tags = []
    department = raw_job.get("department")
    if isinstance(department, str) and department.strip():
        tags.append(department)
    elif isinstance(department, dict):
        name = department.get("name")
        if isinstance(name, str) and name.strip():
            tags.append(name)
    return tags

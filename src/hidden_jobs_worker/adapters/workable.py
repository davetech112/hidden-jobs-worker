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


class WorkableAdapter(AtsAdapter):
    ats_type = AtsType.WORKABLE
    source_name = "WORKABLE"
    base_url = "https://apply.workable.com"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if not career_board.ats_slug:
            raise ValueError(f"career board {career_board.board_id} is missing atsSlug")
        response = self._client.get(f"{self.base_url}/api/v3/accounts/{career_board.ats_slug}/jobs")
        response.raise_for_status()
        return self.parse_jobs(career_board, response.json())

    def parse_jobs(self, career_board: CareerBoard, payload: Any) -> list[JobRecord]:
        jobs = _jobs_array(payload)
        if jobs is None:
            raise ValueError("Workable payload missing jobs array")
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
            sourceJobId=_first_present_str(raw_job, ("id", "shortcode", "shortCode")),
            sourceUrl=_workable_job_url(career_board, raw_job),
            title=_first_present_str(raw_job, ("title", "text")) or "",
            companyName=career_board.company_name,
            locationText=_location_text(raw_job),
            remoteType=_remote_type(raw_job),
            employmentType=_employment_type(_first_present(raw_job, ("type", "employmentType"))),
            descriptionText=description_text
            or (_html_to_text(description_html) if description_html else None),
            descriptionHtml=description_html,
            tags=_tags(raw_job),
            raw={
                "source": self.source_name,
                "sourceType": "ATS",
                "companyId": career_board.company_id,
                "boardId": career_board.board_id,
            },
        )


def _jobs_array(payload: Any) -> list[Any] | None:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("jobs", "results", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    return None


def _workable_job_url(career_board: CareerBoard, raw_job: dict[str, Any]) -> str:
    url = _first_present_str(raw_job, ("url", "shortlink", "application_url", "applyUrl"))
    if url:
        return url
    identifier = _first_present_str(raw_job, ("shortcode", "shortCode", "id"))
    if career_board.ats_slug and identifier:
        return f"https://apply.workable.com/{career_board.ats_slug}/j/{identifier}/"
    raise ValueError("Workable job missing canonical URL")


def _location_text(raw_job: dict[str, Any]) -> str | None:
    value = raw_job.get("location")
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, dict):
        parts = []
        for key in ("city", "region", "country", "name"):
            part = value.get(key)
            if isinstance(part, str) and part.strip():
                parts.append(part)
        if parts:
            return ", ".join(parts)
    return _first_present_str(raw_job, ("locationText", "full_location"))


def _first_present(raw_job: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = raw_job.get(key)
        if value is not None:
            return value
    return None


def _first_present_str(raw_job: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = raw_job.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, int):
            return str(value)
    return None


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _remote_type(raw_job: dict[str, Any]) -> RemoteType:
    remote_flag = raw_job.get("remote")
    if remote_flag is True:
        return RemoteType.REMOTE
    location = _location_text(raw_job)
    if location and "remote" in location.lower():
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
    for key in ("department", "function", "industry"):
        value = raw_job.get(key)
        if isinstance(value, str) and value.strip():
            tags.append(value)
    return tags

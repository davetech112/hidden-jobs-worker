from typing import Any
from xml.etree import ElementTree

import httpx

from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.adapters.common import (
    employment_type,
    first_present,
    first_present_str,
    html_to_text,
    jobs_array,
    location_text,
    remote_type,
    tags_from,
)
from hidden_jobs_worker.models import AtsType, CareerBoard, JobRecord


class PersonioAdapterError(RuntimeError):
    """Raised when a Personio board variant cannot be crawled."""


class PersonioAdapter(AtsAdapter):
    ats_type = AtsType.PERSONIO
    source_name = "PERSONIO"
    base_url = "https://jobs.personio.com"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if not career_board.ats_slug:
            raise PersonioAdapterError(
                f"career board {career_board.board_id} is missing Personio atsSlug"
            )
        response = self._client.get(f"https://{career_board.ats_slug}.jobs.personio.com/xml")
        response.raise_for_status()
        return self.parse_jobs(career_board, response.text)

    def parse_jobs(self, career_board: CareerBoard, payload: Any) -> list[JobRecord]:
        if isinstance(payload, str):
            jobs = _jobs_from_xml(payload)
        else:
            jobs = jobs_array(payload, ("positions", "jobs", "results", "data"))
        return [self._parse_job(career_board, job) for job in jobs if isinstance(job, dict)]

    def _parse_job(self, career_board: CareerBoard, raw_job: dict[str, Any]) -> JobRecord:
        description_html = first_present_str(
            raw_job,
            ("jobDescriptions", "description", "descriptionHtml"),
        )
        return JobRecord(
            sourceName=self.source_name,
            sourceType="ATS",
            sourceJobId=first_present_str(raw_job, ("id", "recruitingCategory")),
            sourceUrl=_job_url(career_board, raw_job),
            title=first_present_str(raw_job, ("name", "title")) or "",
            companyName=career_board.company_name,
            locationText=location_text(raw_job),
            remoteType=remote_type(raw_job),
            employmentType=employment_type(first_present(raw_job, ("employmentType", "schedule"))),
            descriptionText=html_to_text(description_html) if description_html else None,
            descriptionHtml=description_html,
            tags=tags_from(raw_job, ("department", "office")),
            raw=_raw(self.source_name, career_board),
        )


def _jobs_from_xml(payload: str) -> list[dict[str, str]]:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise PersonioAdapterError("Personio XML payload could not be parsed") from exc

    jobs: list[dict[str, str]] = []
    for position in root.findall(".//position"):
        job: dict[str, str] = {}
        for child in position:
            text = "".join(child.itertext()).strip()
            if text:
                job[child.tag] = text
        if job:
            jobs.append(job)
    return jobs


def _job_url(career_board: CareerBoard, raw_job: dict[str, Any]) -> str:
    url = first_present_str(raw_job, ("jobUrl", "url", "applicationUrl"))
    if url:
        return url
    job_id = first_present_str(raw_job, ("id", "recruitingCategory"))
    if career_board.ats_slug and job_id:
        return f"https://{career_board.ats_slug}.jobs.personio.com/job/{job_id}"
    raise PersonioAdapterError("Personio job missing canonical URL")


def _raw(source_name: str, career_board: CareerBoard) -> dict[str, str]:
    return {
        "source": source_name,
        "sourceType": "ATS",
        "companyId": career_board.company_id,
        "boardId": career_board.board_id,
    }

from typing import Any

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


class ComeetAdapterError(RuntimeError):
    """Raised when a Comeet board variant cannot be crawled."""


class ComeetAdapter(AtsAdapter):
    ats_type = AtsType.COMEET
    source_name = "COMEET"
    base_url = "https://www.comeet.com"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if not career_board.ats_slug:
            raise ComeetAdapterError(
                f"career board {career_board.board_id} is missing Comeet atsSlug"
            )
        response = self._client.get(
            f"{self.base_url}/careers-api/2.0/company/{career_board.ats_slug}/positions"
        )
        response.raise_for_status()
        return self.parse_jobs(career_board, response.json())

    def parse_jobs(self, career_board: CareerBoard, payload: Any) -> list[JobRecord]:
        jobs = jobs_array(payload, ("positions", "jobs", "results", "data"))
        return [self._parse_job(career_board, job) for job in jobs if isinstance(job, dict)]

    def _parse_job(self, career_board: CareerBoard, raw_job: dict[str, Any]) -> JobRecord:
        description_html = first_present_str(raw_job, ("description", "descriptionHtml", "details"))
        return JobRecord(
            sourceName=self.source_name,
            sourceType="ATS",
            sourceJobId=first_present_str(raw_job, ("uid", "id")),
            sourceUrl=_job_url(career_board, raw_job),
            title=first_present_str(raw_job, ("name", "title")) or "",
            companyName=career_board.company_name,
            locationText=location_text(raw_job),
            remoteType=remote_type(raw_job),
            employmentType=employment_type(first_present(raw_job, ("employment_type", "type"))),
            descriptionText=html_to_text(description_html) if description_html else None,
            descriptionHtml=description_html,
            tags=tags_from(raw_job, ("department", "tags")),
            raw=_raw(self.source_name, career_board),
        )


def _job_url(career_board: CareerBoard, raw_job: dict[str, Any]) -> str:
    url = first_present_str(raw_job, ("url_active_page", "url", "apply_url"))
    if url:
        return url
    job_id = first_present_str(raw_job, ("uid", "id"))
    if career_board.ats_slug and job_id:
        return f"https://www.comeet.com/jobs/{career_board.ats_slug}/{job_id}"
    raise ComeetAdapterError("Comeet job missing canonical URL")


def _raw(source_name: str, career_board: CareerBoard) -> dict[str, str]:
    return {
        "source": source_name,
        "sourceType": "ATS",
        "companyId": career_board.company_id,
        "boardId": career_board.board_id,
    }

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


class SmartRecruitersAdapterError(RuntimeError):
    """Raised when a SmartRecruiters board variant cannot be crawled."""


class SmartRecruitersAdapter(AtsAdapter):
    ats_type = AtsType.SMARTRECRUITERS
    source_name = "SMARTRECRUITERS"
    base_url = "https://api.smartrecruiters.com"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if not career_board.ats_slug:
            raise SmartRecruitersAdapterError(
                f"career board {career_board.board_id} is missing SmartRecruiters atsSlug"
            )
        response = self._client.get(
            f"{self.base_url}/v1/companies/{career_board.ats_slug}/postings"
        )
        response.raise_for_status()
        return self.parse_jobs(career_board, response.json())

    def parse_jobs(self, career_board: CareerBoard, payload: Any) -> list[JobRecord]:
        jobs = jobs_array(payload, ("content", "jobs", "results", "data"))
        return [self._parse_job(career_board, job) for job in jobs if isinstance(job, dict)]

    def _parse_job(self, career_board: CareerBoard, raw_job: dict[str, Any]) -> JobRecord:
        job_ad = raw_job.get("jobAd") if isinstance(raw_job.get("jobAd"), dict) else {}
        sections = job_ad.get("sections") if isinstance(job_ad, dict) else {}
        section_description = None
        if isinstance(sections, dict):
            job_description = sections.get("jobDescription", {})
            if isinstance(job_description, dict):
                section_description = job_description.get("text")
        description_html = first_present_str(
            raw_job,
            ("descriptionHtml", "description", "content"),
        ) or section_description
        description_text = html_to_text(description_html) if description_html else None
        job_id = first_present_str(raw_job, ("id", "uuid", "refNumber"))
        return JobRecord(
            sourceName=self.source_name,
            sourceType="ATS",
            sourceJobId=job_id,
            sourceUrl=_job_url(career_board, raw_job, job_id),
            title=first_present_str(raw_job, ("name", "title")) or "",
            companyName=career_board.company_name,
            locationText=location_text(raw_job),
            remoteType=remote_type(raw_job),
            employmentType=employment_type(first_present(raw_job, ("typeOfEmployment", "type"))),
            descriptionText=description_text,
            descriptionHtml=description_html,
            tags=tags_from(raw_job, ("department", "industry", "function")),
            raw=_raw(self.source_name, career_board),
        )


def _job_url(career_board: CareerBoard, raw_job: dict[str, Any], job_id: str | None) -> str:
    url = first_present_str(raw_job, ("releasedUrl", "ref", "url", "applyUrl"))
    if url:
        return url
    if career_board.ats_slug and job_id:
        return f"https://jobs.smartrecruiters.com/{career_board.ats_slug}/{job_id}"
    raise SmartRecruitersAdapterError("SmartRecruiters job missing canonical URL")


def _raw(source_name: str, career_board: CareerBoard) -> dict[str, str]:
    return {
        "source": source_name,
        "sourceType": "ATS",
        "companyId": career_board.company_id,
        "boardId": career_board.board_id,
    }

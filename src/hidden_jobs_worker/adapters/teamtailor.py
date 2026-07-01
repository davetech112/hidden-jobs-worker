import json
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

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


class TeamtailorAdapterError(RuntimeError):
    """Raised when a Teamtailor board variant cannot be crawled."""


class _HtmlParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__()
        self.page_url = page_url
        self.scripts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._script: list[str] | None = None
        self._link: dict[str, str] | None = None
        self._link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value for key, value in attrs if value is not None}
        if tag == "script":
            self._script = []
        if tag == "a" and attributes.get("href"):
            self._link = {"url": urljoin(self.page_url, attributes["href"])}
            self._link_text = []

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script.append(data)
        if self._link is not None and data.strip():
            self._link_text.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._script is not None:
            script = "".join(self._script).strip()
            if script:
                self.scripts.append(script)
            self._script = None
        if tag == "a" and self._link is not None:
            title = " ".join(self._link_text).strip()
            if title:
                self._link["title"] = title
                self.links.append(self._link)
            self._link = None
            self._link_text = []


class TeamtailorAdapter(AtsAdapter):
    ats_type = AtsType.TEAMTAILOR
    source_name = "TEAMTAILOR"
    base_url = "https://teamtailor.com"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if not career_board.ats_slug:
            raise TeamtailorAdapterError(
                f"career board {career_board.board_id} is missing Teamtailor atsSlug"
            )
        url = str(career_board.board_url) if career_board.board_url else ""
        if "teamtailor" not in url:
            url = f"https://{career_board.ats_slug}.teamtailor.com/jobs"
        response = self._client.get(url)
        response.raise_for_status()
        return self.parse_jobs(career_board, response.text)

    def parse_jobs(self, career_board: CareerBoard, payload: Any) -> list[JobRecord]:
        if isinstance(payload, dict | list):
            jobs = jobs_array(payload, ("data", "jobs", "results"))
            return [self._parse_job(career_board, job) for job in jobs if isinstance(job, dict)]
        if not isinstance(payload, str):
            return []
        parser = _HtmlParser(str(career_board.board_url))
        parser.feed(payload)
        for script in parser.scripts:
            try:
                jobs = jobs_array(json.loads(script), ("data", "jobs", "results"))
            except json.JSONDecodeError:
                continue
            if jobs:
                return [self._parse_job(career_board, job) for job in jobs if isinstance(job, dict)]
        return [
            self._parse_job(career_board, link)
            for link in parser.links
            if "/jobs/" in link.get("url", "")
        ]

    def _parse_job(self, career_board: CareerBoard, raw_job: dict[str, Any]) -> JobRecord:
        raw_attributes = raw_job.get("attributes")
        attributes = raw_attributes if isinstance(raw_attributes, dict) else {}
        merged = {**attributes, **raw_job}
        description_html = first_present_str(merged, ("body", "description", "descriptionHtml"))
        return JobRecord(
            sourceName=self.source_name,
            sourceType="ATS",
            sourceJobId=first_present_str(merged, ("id", "uuid")),
            sourceUrl=_job_url(career_board, merged),
            title=first_present_str(merged, ("title", "name")) or "",
            companyName=career_board.company_name,
            locationText=location_text(merged),
            remoteType=remote_type(merged),
            employmentType=employment_type(first_present(merged, ("employmentType", "type"))),
            descriptionText=html_to_text(description_html) if description_html else None,
            descriptionHtml=description_html,
            tags=tags_from(merged, ("department", "tags")),
            raw=_raw(self.source_name, career_board),
        )


def _job_url(career_board: CareerBoard, raw_job: dict[str, Any]) -> str:
    links = raw_job.get("links") if isinstance(raw_job.get("links"), dict) else {}
    url = first_present_str(raw_job, ("url", "careersiteJobUrl")) or first_present_str(
        links, ("careersite-job-url", "self")
    )
    if url:
        return url
    job_id = first_present_str(raw_job, ("id", "uuid"))
    if career_board.ats_slug and job_id:
        return f"https://{career_board.ats_slug}.teamtailor.com/jobs/{job_id}"
    raise TeamtailorAdapterError("Teamtailor job missing canonical URL")


def _raw(source_name: str, career_board: CareerBoard) -> dict[str, str]:
    return {
        "source": source_name,
        "sourceType": "ATS",
        "companyId": career_board.company_id,
        "boardId": career_board.board_id,
    }

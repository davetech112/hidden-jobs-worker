import json
import logging
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import httpx

from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.models import AtsType, CareerBoard, EmploymentType, JobRecord, RemoteType

LOGGER = logging.getLogger(__name__)


class WorkableAdapterError(RuntimeError):
    def __init__(self, message: str, attempted_urls: list[str]) -> None:
        super().__init__(f"{message}; attempted URLs: {', '.join(attempted_urls)}")
        self.attempted_urls = attempted_urls


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


class _WorkableHtmlParser(HTMLParser):
    def __init__(self, page_url: str) -> None:
        super().__init__()
        self.page_url = page_url
        self.scripts: list[str] = []
        self.links: list[dict[str, str]] = []
        self._current_script: list[str] | None = None
        self._current_link: dict[str, str] | None = None
        self._current_link_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key: value for key, value in attrs if value is not None}
        if tag == "script":
            self._current_script = []
        if tag == "a" and attributes.get("href"):
            self._current_link = {"href": urljoin(self.page_url, attributes["href"])}
            self._current_link_text = []

    def handle_data(self, data: str) -> None:
        if self._current_script is not None:
            self._current_script.append(data)
        if self._current_link is not None:
            stripped = data.strip()
            if stripped:
                self._current_link_text.append(stripped)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._current_script is not None:
            script = "".join(self._current_script).strip()
            if script:
                self.scripts.append(script)
            self._current_script = None
        if tag == "a" and self._current_link is not None:
            text = " ".join(self._current_link_text).strip()
            if text:
                self._current_link["title"] = text
            self.links.append(self._current_link)
            self._current_link = None
            self._current_link_text = []


class WorkableAdapter(AtsAdapter):
    ats_type = AtsType.WORKABLE
    source_name = "WORKABLE"
    base_url = "https://apply.workable.com"

    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 15.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if not career_board.ats_slug:
            raise ValueError(f"career board {career_board.board_id} is missing atsSlug")
        attempted_urls: list[str] = []
        slug = career_board.ats_slug
        strategies = (
            ("api", f"{self.base_url}/api/v3/accounts/{slug}/jobs", "json"),
            ("public-page", f"{self.base_url}/{slug}/", "html"),
            ("jobs-page", f"{self.base_url}/{slug}/jobs", "html"),
        )

        for strategy_name, url, payload_type in strategies:
            attempted_urls.append(url)
            response = self._client.get(url)
            if response.status_code == 404:
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                continue

            try:
                payload = response.json() if payload_type == "json" else response.text
                jobs = self.parse_jobs(career_board, payload, page_url=url)
            except (ValueError, json.JSONDecodeError):
                continue
            if jobs:
                LOGGER.info(
                    "Workable fetch strategy succeeded",
                    extra={
                        "strategy": strategy_name,
                        "url": url,
                        "board_id": career_board.board_id,
                        "job_count": len(jobs),
                    },
                )
                return jobs

        raise WorkableAdapterError(
            f"Workable fetch failed for board {career_board.board_id}",
            attempted_urls,
        )

    def parse_jobs(
        self,
        career_board: CareerBoard,
        payload: Any,
        page_url: str | None = None,
    ) -> list[JobRecord]:
        if isinstance(payload, str):
            return self._parse_html_jobs(career_board, payload, page_url)
        jobs = _jobs_array(payload)
        if jobs is None:
            raise ValueError("Workable payload missing jobs array")
        return [self._parse_job(career_board, job) for job in jobs if isinstance(job, dict)]

    def _parse_html_jobs(
        self,
        career_board: CareerBoard,
        html: str,
        page_url: str | None,
    ) -> list[JobRecord]:
        parser = _WorkableHtmlParser(page_url or f"{self.base_url}/{career_board.ats_slug}/")
        parser.feed(html)

        for script in parser.scripts:
            embedded_payload = _json_from_script(script)
            if embedded_payload is None:
                continue
            jobs = _jobs_array(embedded_payload)
            if jobs:
                return [self._parse_job(career_board, job) for job in jobs if isinstance(job, dict)]

        return [
            self._parse_job(career_board, link)
            for link in _job_links(parser.links, career_board.ats_slug)
        ]

    def _parse_job(self, career_board: CareerBoard, raw_job: dict[str, Any]) -> JobRecord:
        description_html = _first_present_str(
            raw_job,
            ("descriptionHtml", "description_html", "description", "content", "contentHtml"),
        )
        description_text = _first_present_str(
            raw_job,
            ("descriptionPlain", "descriptionText", "description_plain", "contentText"),
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
        for key in ("jobs", "results", "data", "postings"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for value in payload.values():
            jobs = _jobs_array(value)
            if jobs is not None:
                return jobs
    return None


def _workable_job_url(career_board: CareerBoard, raw_job: dict[str, Any]) -> str:
    url = _first_present_str(
        raw_job,
        ("url", "shortlink", "application_url", "applyUrl", "absolute_url"),
    )
    if url:
        return urljoin(f"https://apply.workable.com/{career_board.ats_slug or ''}/", url)
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
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            if isinstance(item, dict):
                name = _first_present_str(item, ("city", "region", "country", "name"))
                if name:
                    parts.append(name)
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
        if isinstance(value, dict):
            name = _first_present_str(value, ("name", "title"))
            if name:
                tags.append(name)
    return tags


def _json_from_script(script: str) -> Any | None:
    stripped = script.strip()
    candidates = [stripped]
    for marker in ("window.__INITIAL_STATE__ =", "window.__INITIAL_STATE__="):
        if marker in stripped:
            candidates.append(stripped.split(marker, 1)[1].strip().removesuffix(";"))
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _job_links(links: list[dict[str, str]], ats_slug: str | None) -> list[dict[str, str]]:
    jobs: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    slug_fragment = f"/{ats_slug}/" if ats_slug else "/"
    for link in links:
        url = link.get("href", "")
        title = link.get("title", "")
        lower_url = url.lower()
        lower_title = title.lower()
        is_job_url = "/j/" in lower_url
        is_board_job_url = bool(ats_slug and slug_fragment in lower_url and "/j/" in lower_url)
        is_job_text = any(word in lower_title for word in ("engineer", "manager", "designer"))
        if not title or url in seen_urls or not (is_job_url or is_board_job_url or is_job_text):
            continue
        seen_urls.add(url)
        jobs.append(
            {
                "title": title,
                "url": url,
                "shortcode": _shortcode_from_url(url),
            }
        )
    return jobs


def _shortcode_from_url(url: str) -> str | None:
    parts = [part for part in url.rstrip("/").split("/") if part]
    if "j" in parts:
        index = parts.index("j")
        if len(parts) > index + 1:
            return parts[index + 1]
    return None

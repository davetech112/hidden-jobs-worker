import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from hidden_jobs_worker.models import AtsType


@dataclass(frozen=True)
class AtsDetection:
    ats_type: AtsType
    ats_slug: str | None = None
    matched_url: str | None = None
    suspicious_reason: str | None = None


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key.lower() in {"href", "src"} and value:
                self.urls.append(value)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)


def detect_ats(url: str | None = None, html: str | None = None) -> AtsDetection:
    urls = []
    if url:
        urls.append(url)
    if html:
        extractor = _LinkExtractor()
        extractor.feed(html)
        urls.extend(extractor.urls)
        urls.extend(_extract_urls_from_text(html))

    fallback_detection: AtsDetection | None = None
    for candidate_url in urls:
        detection = _detect_ats_from_url(candidate_url)
        if detection.ats_type == AtsType.UNKNOWN:
            if detection.suspicious_reason:
                fallback_detection = fallback_detection or detection
            continue
        if detection.ats_slug:
            return detection
        fallback_detection = fallback_detection or detection
    return fallback_detection or AtsDetection(AtsType.UNKNOWN)


def _detect_ats_from_url(url: str) -> AtsDetection:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if host in {"boards.greenhouse.io", "job-boards.greenhouse.io"}:
        return _detection(AtsType.GREENHOUSE, _first_path_part(path_parts), url)

    if "greenhouse.io" in host:
        slug = _first_path_part(path_parts)
        if host.startswith("boards-api.") and len(path_parts) >= 3:
            slug = path_parts[2]
        return _detection(AtsType.GREENHOUSE, slug, url)

    if host == "jobs.lever.co" or host.endswith(".lever.co"):
        return _detection(AtsType.LEVER, _first_path_part(path_parts), url)

    if host == "jobs.ashbyhq.com" or host.endswith(".ashbyhq.com"):
        return _detection(AtsType.ASHBY, _first_path_part(path_parts), url)

    if host == "apply.workable.com" or host.endswith(".workable.com"):
        return _detection(AtsType.WORKABLE, _first_path_part(path_parts), url)

    if host in {"jobs.smartrecruiters.com", "smartrecruiters.com"} or host.endswith(
        ".smartrecruiters.com"
    ):
        slug = _first_path_part(path_parts)
        if host == "api.smartrecruiters.com" and len(path_parts) >= 3:
            slug = path_parts[2]
        return _detection(AtsType.SMARTRECRUITERS, slug, url)

    if host == "teamtailor.com" or host.endswith(".teamtailor.com"):
        slug = host.split(".")[0] if host != "teamtailor.com" else _first_path_part(path_parts)
        return _detection(AtsType.TEAMTAILOR, slug, url)

    if host == "recruitee.com" or host.endswith(".recruitee.com"):
        slug = host.split(".")[0] if host != "recruitee.com" else _first_path_part(path_parts)
        return _detection(AtsType.RECRUITEE, slug, url)

    if host == "comeet.com" or host.endswith(".comeet.com"):
        slug = None
        if "company" in path_parts:
            index = path_parts.index("company")
            if len(path_parts) > index + 1:
                slug = path_parts[index + 1]
        elif "jobs" in path_parts:
            index = path_parts.index("jobs")
            if len(path_parts) > index + 1:
                slug = path_parts[index + 1]
        else:
            slug = _first_path_part(path_parts)
        return _detection(AtsType.COMEET, slug, url)

    if host == "jobs.personio.com" or host.endswith(".jobs.personio.com"):
        slug = host.removesuffix(".jobs.personio.com")
        if slug == host:
            slug = _first_path_part(path_parts)
        return _detection(AtsType.PERSONIO, slug, url)

    return AtsDetection(AtsType.UNKNOWN)


def _first_path_part(path_parts: list[str]) -> str | None:
    return path_parts[0] if path_parts else None


def _extract_urls_from_text(text: str) -> list[str]:
    return re.findall(r"https?://[^\s\"'<>]+", text)


def _detection(ats_type: AtsType, slug: str | None, matched_url: str) -> AtsDetection:
    sanitized_slug = sanitize_ats_slug(slug)
    if sanitized_slug and is_suspicious_ats_slug(sanitized_slug):
        return AtsDetection(
            AtsType.UNKNOWN,
            None,
            matched_url,
            f"suspicious {ats_type.value} atsSlug rejected: {sanitized_slug}",
        )
    return AtsDetection(ats_type, sanitized_slug, matched_url)


def sanitize_ats_slug(value: str | None) -> str | None:
    if value is None:
        return None
    slug = value.strip().strip("/")
    if not slug:
        return None
    if "://" in slug or "\\" in slug:
        return None
    if any(character in slug for character in ("'", '"', "/", ":", ",", "{", "}", "<", ">")):
        return None
    if "&" in slug or ";" in slug:
        return None
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", slug):
        return None
    if ".." in slug or slug.endswith("."):
        return None
    return slug


SUSPICIOUS_ATS_SLUGS = {
    "www",
    "api",
    "app",
    "jobs",
    "careers",
    "career",
    "hiring",
    "apply",
    "recruitment",
    "ai-statement",
    "privacy",
    "legal",
    "terms",
    "cookie",
    "static",
    "assets",
}


def is_suspicious_ats_slug(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in SUSPICIOUS_ATS_SLUGS

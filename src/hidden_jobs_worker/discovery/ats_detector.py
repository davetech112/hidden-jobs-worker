from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

from hidden_jobs_worker.models import AtsType


@dataclass(frozen=True)
class AtsDetection:
    ats_type: AtsType
    ats_slug: str | None = None
    matched_url: str | None = None


class _LinkExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.links.append(value)


def detect_ats(url: str | None = None, html: str | None = None) -> AtsDetection:
    urls = []
    if url:
        urls.append(url)
    if html:
        extractor = _LinkExtractor()
        extractor.feed(html)
        urls.extend(extractor.links)

    for candidate_url in urls:
        detection = _detect_ats_from_url(candidate_url)
        if detection.ats_type != AtsType.UNKNOWN:
            return detection
    return AtsDetection(AtsType.UNKNOWN)


def _detect_ats_from_url(url: str) -> AtsDetection:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if "greenhouse.io" in host:
        slug = _first_path_part(path_parts)
        if host.startswith("boards-api.") and len(path_parts) >= 3:
            slug = path_parts[2]
        return AtsDetection(AtsType.GREENHOUSE, slug, url)

    if host == "jobs.lever.co" or host.endswith(".lever.co"):
        return AtsDetection(AtsType.LEVER, _first_path_part(path_parts), url)

    if host == "jobs.ashbyhq.com" or host.endswith(".ashbyhq.com"):
        return AtsDetection(AtsType.ASHBY, _first_path_part(path_parts), url)

    if host == "apply.workable.com" or host.endswith(".workable.com"):
        return AtsDetection(AtsType.WORKABLE, _first_path_part(path_parts), url)

    if "smartrecruiters.com" in host:
        return AtsDetection(AtsType.SMARTRECRUITERS, _first_path_part(path_parts), url)

    if host.endswith(".teamtailor.com"):
        return AtsDetection(AtsType.TEAMTAILOR, host.split(".")[0], url)

    if host.endswith(".recruitee.com"):
        return AtsDetection(AtsType.RECRUITEE, host.split(".")[0], url)

    return AtsDetection(AtsType.UNKNOWN)


def _first_path_part(path_parts: list[str]) -> str | None:
    return path_parts[0] if path_parts else None

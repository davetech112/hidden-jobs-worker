from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

CAREERS_PATHS = ("/careers", "/jobs", "/join-us", "/company/careers", "/about/careers")
CAREERS_TERMS = ("careers", "jobs", "join us", "open roles", "work with us")


@dataclass(frozen=True)
class CareersPage:
    url: str
    html: str


class _Anchor:
    def __init__(self, href: str, text: str) -> None:
        self.href = href
        self.text = text


class _CareersLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._current_href: str | None = None
        self._text_parts: list[str] = []
        self.anchors: list[_Anchor] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self._current_href = value
                self._text_parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href is not None:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._current_href is not None:
            self.anchors.append(_Anchor(self._current_href, " ".join(self._text_parts)))
            self._current_href = None
            self._text_parts = []


class CareersPageFinder:
    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 30.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)

    def find(self, website_url: str) -> str | None:
        page = self.find_page(website_url)
        return page.url if page else None

    def find_page(self, website_url: str) -> CareersPage | None:
        for path in CAREERS_PATHS:
            candidate_url = urljoin(_normalized_base_url(website_url), path)
            page = self._fetch_reachable(candidate_url)
            if page:
                return page

        try:
            response = self._client.get(website_url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        careers_url = find_careers_link(str(response.url), response.text)
        if not careers_url:
            return None
        return self._fetch_reachable(careers_url) or CareersPage(careers_url, "")

    def _is_reachable(self, url: str) -> bool:
        return self._fetch_reachable(url) is not None

    def _fetch_reachable(self, url: str) -> CareersPage | None:
        try:
            response = self._client.get(url)
        except httpx.HTTPError:
            return None
        if 200 <= response.status_code < 400:
            return CareersPage(str(response.url), response.text)
        return None


def find_careers_link(base_url: str, html: str) -> str | None:
    parser = _CareersLinkParser()
    parser.feed(html)
    for anchor in parser.anchors:
        haystack = f"{anchor.text} {anchor.href}".lower().replace("-", " ")
        if any(term in haystack for term in CAREERS_TERMS):
            return urljoin(base_url, anchor.href)
    return None


def _normalized_base_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        return f"https://{url.strip('/')}"
    return f"{parsed.scheme}://{parsed.netloc}"

from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

CAREERS_PATHS = ("/careers", "/jobs", "/join-us", "/company/careers", "/about/careers")
CAREERS_TERMS = ("careers", "jobs", "join us", "open roles", "work with us")


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
        for path in CAREERS_PATHS:
            candidate_url = urljoin(_normalized_base_url(website_url), path)
            if self._is_reachable(candidate_url):
                return candidate_url

        try:
            response = self._client.get(website_url)
            response.raise_for_status()
        except httpx.HTTPError:
            return None

        return find_careers_link(website_url, response.text)

    def _is_reachable(self, url: str) -> bool:
        try:
            response = self._client.get(url)
        except httpx.HTTPError:
            return False
        return 200 <= response.status_code < 400


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

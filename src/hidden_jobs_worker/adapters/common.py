from html.parser import HTMLParser
from typing import Any

from hidden_jobs_worker.models import EmploymentType, RemoteType


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        stripped = data.strip()
        if stripped:
            self.parts.append(stripped)

    def text(self) -> str:
        return " ".join(self.parts)


def first_present(raw: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = raw.get(key)
        if value is not None:
            return value
    return None


def first_present_str(raw: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


def html_to_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return parser.text()


def jobs_array(payload: Any, keys: tuple[str, ...] = ("jobs", "results", "data")) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            value = payload.get(key)
            if isinstance(value, list):
                return value
        for value in payload.values():
            nested = jobs_array(value, keys)
            if nested:
                return nested
    return []


def location_text(raw: dict[str, Any]) -> str | None:
    location = first_present(raw, ("location", "locationText", "full_location", "city"))
    if isinstance(location, str) and location.strip():
        return location.strip()
    if isinstance(location, dict):
        parts = []
        for key in ("city", "region", "country", "name", "displayName"):
            value = location.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        if parts:
            return ", ".join(parts)
    if isinstance(location, list):
        parts = []
        for item in location:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                value = first_present_str(item, ("city", "region", "country", "name"))
                if value:
                    parts.append(value)
        if parts:
            return ", ".join(parts)
    return None


def remote_type(raw: dict[str, Any]) -> RemoteType:
    remote = raw.get("remote")
    if remote is True:
        return RemoteType.REMOTE
    text = " ".join(
        str(value)
        for value in (
            location_text(raw),
            first_present(raw, ("workplaceType", "remoteType", "workplace")),
        )
        if value is not None
    ).lower()
    if "remote" in text:
        return RemoteType.REMOTE
    if "hybrid" in text:
        return RemoteType.HYBRID
    if "onsite" in text or "office" in text:
        return RemoteType.ONSITE
    return RemoteType.UNKNOWN


def employment_type(value: Any) -> EmploymentType:
    normalized = str(value or "").lower().replace("-", " ").replace("_", " ")
    if "full" in normalized:
        return EmploymentType.FULL_TIME
    if "part" in normalized:
        return EmploymentType.PART_TIME
    if "contract" in normalized or "freelance" in normalized:
        return EmploymentType.CONTRACT
    if "intern" in normalized or "trainee" in normalized:
        return EmploymentType.INTERNSHIP
    if "temporary" in normalized or "temp" in normalized:
        return EmploymentType.TEMPORARY
    return EmploymentType.UNKNOWN


def tags_from(raw: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
    tags: list[str] = []
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            tags.append(value)
        elif isinstance(value, dict):
            name = first_present_str(value, ("name", "title", "label"))
            if name:
                tags.append(name)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    tags.append(item)
                elif isinstance(item, dict):
                    name = first_present_str(item, ("name", "title", "label"))
                    if name:
                        tags.append(name)
    return tags

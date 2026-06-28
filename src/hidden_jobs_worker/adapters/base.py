from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from hidden_jobs_worker.models import JobRecord, SourceInfo, SourceType


@dataclass(frozen=True)
class SourceMetadata:
    key: str
    name: str
    type: SourceType
    base_url: str

    def to_source_info(self) -> SourceInfo:
        return SourceInfo(key=self.key, name=self.name, type=self.type, baseUrl=self.base_url)


class SourceAdapter(ABC):
    metadata: SourceMetadata

    @abstractmethod
    def fetch_jobs(self) -> list[JobRecord]:
        """Fetch and normalize jobs from a source."""

    @abstractmethod
    def parse_jobs(self, payload: dict[str, Any]) -> list[JobRecord]:
        """Parse a source response payload into normalized job records."""

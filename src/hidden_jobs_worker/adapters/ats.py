from abc import ABC, abstractmethod
from typing import Any

from hidden_jobs_worker.adapters.base import SourceMetadata
from hidden_jobs_worker.models import AtsType, CompanyRecord, JobRecord, SourceInfo, SourceType


class AtsAdapter(ABC):
    ats_type: AtsType
    source_name: str
    base_url: str

    def source_info(self, company: CompanyRecord) -> SourceInfo:
        return SourceInfo(
            key=f"{self.source_name.lower()}:{company.id}",
            name=self.source_name,
            type=SourceType.ATS_BOARD,
            baseUrl=str(company.careers_url or company.website_url or self.base_url),
        )

    @property
    def metadata(self) -> SourceMetadata:
        return SourceMetadata(
            key=self.source_name.lower(),
            name=self.source_name,
            type=SourceType.ATS_BOARD,
            base_url=self.base_url,
        )

    @abstractmethod
    def fetch_jobs(self, company: CompanyRecord) -> list[JobRecord]:
        """Fetch and normalize jobs for one company."""

    @abstractmethod
    def parse_jobs(self, company: CompanyRecord, payload: Any) -> list[JobRecord]:
        """Parse a provider response payload into normalized jobs."""

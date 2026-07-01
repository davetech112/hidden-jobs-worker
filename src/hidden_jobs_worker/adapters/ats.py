from abc import ABC, abstractmethod
from typing import Any

from hidden_jobs_worker.adapters.base import SourceMetadata
from hidden_jobs_worker.models import AtsType, CareerBoard, JobRecord, SourceInfo, SourceType


class AtsAdapter(ABC):
    ats_type: AtsType
    source_name: str
    base_url: str

    def source_info(self, career_board: CareerBoard) -> SourceInfo:
        return SourceInfo(
            key=f"{self.source_name.lower()}:{career_board.board_id}",
            name=self.source_name,
            type=SourceType.ATS_BOARD,
            baseUrl=str(career_board.board_url),
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
    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        """Fetch and normalize jobs for one career board."""

    @abstractmethod
    def parse_jobs(self, career_board: CareerBoard, payload: Any) -> list[JobRecord]:
        """Parse a provider response payload into normalized jobs."""

import logging

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.logging import redact_headers
from hidden_jobs_worker.models import CompanyCandidate

LOGGER = logging.getLogger(__name__)
CAREER_BOARD_DISCOVERIES_PATH = "/api/internal/discoveries/career-boards"
SUCCESS_STATUS_CODES = {200, 201, 202}
EXPECTED_RESULT_STATUSES = {"created", "updated", "ignored"}


class DiscoveryRegistrationClientError(RuntimeError):
    """Raised when the discovery registration API cannot process a request."""


class DiscoveryRegistrationAuthError(DiscoveryRegistrationClientError):
    """Raised when the discovery registration API rejects worker authentication."""


class DiscoveryRegistrationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str
    message: str | None = None
    company_id: str | None = Field(default=None, alias="companyId")

    @field_validator("status")
    @classmethod
    def normalize_status(cls, value: str) -> str:
        stripped = value.strip().lower()
        if stripped not in EXPECTED_RESULT_STATUSES:
            raise ValueError("status must be created, updated, or ignored")
        return stripped

    @property
    def submitted(self) -> bool:
        return self.status in {"created", "updated"}

    @property
    def ignored(self) -> bool:
        return self.status == "ignored"


class DiscoveryRegistrationClient:
    """Submits verified discovery candidates to the backend."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.worker_request_timeout_seconds)

    def submit_career_board(self, candidate: CompanyCandidate) -> DiscoveryRegistrationResult:
        request_body = candidate.model_dump(mode="json", by_alias=True)
        url = f"{self._settings.spring_api_base_url}{CAREER_BOARD_DISCOVERIES_PATH}"
        headers = {
            "Content-Type": "application/json",
            "X-Worker-Token": self._settings.worker_ingest_token,
        }

        response = self._client.post(url, headers=headers, json=request_body)
        if response.status_code in {401, 403}:
            raise DiscoveryRegistrationAuthError(
                "discovery registration API rejected worker authentication"
            )
        if response.status_code not in SUCCESS_STATUS_CODES:
            LOGGER.warning(
                "discovery registration API failure",
                extra={
                    "status_code": response.status_code,
                    "headers": redact_headers(headers),
                },
            )
            raise DiscoveryRegistrationClientError(
                f"discovery registration API returned status {response.status_code}: "
                f"{response.text}"
            )
        return DiscoveryRegistrationResult.model_validate(_unwrap_response_data(response.json()))


def _unwrap_response_data(response_body: object) -> object:
    if isinstance(response_body, dict) and isinstance(response_body.get("data"), dict):
        return response_body["data"]
    return response_body

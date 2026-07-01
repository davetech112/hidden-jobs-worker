import logging

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, HttpUrl, field_validator

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.logging import redact_headers
from hidden_jobs_worker.models import AtsType, CompanyCandidate

LOGGER = logging.getLogger(__name__)
CAREER_BOARD_DISCOVERIES_PATH = "/api/internal/discoveries/career-boards"
SUCCESS_STATUS_CODES = {200, 201, 202}
EXPECTED_RESULT_STATUSES = {"created", "updated", "ignored"}
BACKEND_ATS_TYPES = {AtsType.GREENHOUSE, AtsType.LEVER, AtsType.ASHBY, AtsType.WORKABLE}


class DiscoveryRegistrationClientError(RuntimeError):
    """Raised when the discovery registration API cannot process a request."""


class DiscoveryRegistrationAuthError(DiscoveryRegistrationClientError):
    """Raised when the discovery registration API rejects worker authentication."""


class DiscoveryRegistrationResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(validation_alias=AliasChoices("status", "action"))
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
    def created(self) -> bool:
        return self.status == "created"

    @property
    def updated(self) -> bool:
        return self.status == "updated"

    @property
    def submitted(self) -> bool:
        return self.created or self.updated

    @property
    def ignored(self) -> bool:
        return self.status == "ignored"


class DiscoveryRegistrationClient:
    """Submits verified discovery candidates to the backend."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.worker_request_timeout_seconds)

    def submit_career_board(self, candidate: CompanyCandidate) -> DiscoveryRegistrationResult:
        request_body = build_career_board_discovery_payload(candidate)
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


def build_career_board_discovery_payload(candidate: CompanyCandidate) -> dict[str, object]:
    payload = CareerBoardDiscoveryPayload.from_candidate(candidate)
    return payload.model_dump(mode="json", by_alias=True)


class CareerBoardDiscoveryPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    company_name: str = Field(alias="companyName")
    website_url: HttpUrl | None = Field(default=None, alias="websiteUrl")
    careers_url: HttpUrl | None = Field(default=None, alias="careersUrl")
    board_url: HttpUrl = Field(alias="boardUrl")
    ats_type: AtsType = Field(alias="atsType")
    ats_slug: str | None = Field(default=None, alias="atsSlug")
    confidence_score: float = Field(
        alias="confidenceScore",
        ge=0.0,
        le=1.0,
    )
    verification_method: str | None = Field(default=None, alias="verificationMethod")
    verification_url: HttpUrl | None = Field(default=None, alias="verificationUrl")
    detected_from: str | None = Field(default=None, alias="detectedFrom")
    discovery_notes: str | None = Field(default=None, alias="discoveryNotes")

    @classmethod
    def from_candidate(cls, candidate: CompanyCandidate) -> "CareerBoardDiscoveryPayload":
        board_url = _board_url_for(candidate)
        return cls(
            companyName=candidate.name,
            websiteUrl=candidate.website_url,
            careersUrl=candidate.careers_url,
            boardUrl=board_url,
            atsType=_backend_ats_type(candidate.ats_type),
            atsSlug=candidate.ats_slug,
            confidenceScore=round(candidate.confidence_score, 4),
            verificationMethod=_verification_method(candidate.ats_type),
            verificationUrl=board_url,
            detectedFrom=candidate.source,
            discoveryNotes="\n".join(candidate.discovery_notes) or None,
        )

    @field_validator("company_name")
    @classmethod
    def require_company_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("companyName must not be blank")
        return stripped


def _board_url_for(candidate: CompanyCandidate) -> str:
    if candidate.board_url:
        return str(candidate.board_url)
    if candidate.careers_url:
        return str(candidate.careers_url)
    if not candidate.ats_slug:
        raise ValueError("atsSlug or careersUrl is required to build boardUrl")
    if candidate.ats_type == AtsType.GREENHOUSE:
        return f"https://boards.greenhouse.io/{candidate.ats_slug}"
    if candidate.ats_type == AtsType.LEVER:
        return f"https://jobs.lever.co/{candidate.ats_slug}"
    if candidate.ats_type == AtsType.ASHBY:
        return f"https://jobs.ashbyhq.com/{candidate.ats_slug}"
    if candidate.ats_type == AtsType.WORKABLE:
        return f"https://apply.workable.com/{candidate.ats_slug}"
    if candidate.careers_url:
        return str(candidate.careers_url)
    raise ValueError("careersUrl is required to build custom boardUrl")


def _backend_ats_type(ats_type: AtsType) -> AtsType:
    if ats_type in BACKEND_ATS_TYPES:
        return ats_type
    return AtsType.CUSTOM


def _verification_method(ats_type: AtsType) -> str:
    return f"{_backend_ats_type(ats_type).value.lower()}-board"

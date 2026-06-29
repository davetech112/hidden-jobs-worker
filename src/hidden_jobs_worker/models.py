from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class SourceType(StrEnum):
    ATS_BOARD = "ats_board"
    COMPANY_CAREER_PAGE = "company_career_page"
    REMOTE_JOB_SOURCE = "remote_job_source"


class RemoteType(StrEnum):
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"
    UNKNOWN = "UNKNOWN"


class EmploymentType(StrEnum):
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERNSHIP = "INTERNSHIP"
    TEMPORARY = "TEMPORARY"
    UNKNOWN = "UNKNOWN"


class ExperienceLevel(StrEnum):
    ENTRY_LEVEL = "ENTRY_LEVEL"
    MID_LEVEL = "MID_LEVEL"
    SENIOR_LEVEL = "SENIOR_LEVEL"
    LEAD = "LEAD"
    STAFF = "STAFF"
    PRINCIPAL = "PRINCIPAL"
    EXECUTIVE = "EXECUTIVE"
    UNKNOWN = "UNKNOWN"


class Compensation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    min_amount: float | None = Field(default=None, alias="minAmount")
    max_amount: float | None = Field(default=None, alias="maxAmount")
    currency: str | None = None
    interval: str | None = None


class JobRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_job_id: str | None = Field(default=None, alias="sourceJobId")
    source_url: HttpUrl = Field(alias="sourceUrl")
    title: str
    company_name: str = Field(alias="companyName")
    location_text: str | None = Field(default=None, alias="locationText")
    remote_type: RemoteType | None = Field(default=RemoteType.UNKNOWN, alias="remoteType")
    employment_type: EmploymentType | None = Field(
        default=EmploymentType.UNKNOWN, alias="employmentType"
    )
    experience_level: ExperienceLevel | None = Field(default=None, alias="experienceLevel")
    description_text: str | None = Field(default=None, alias="descriptionText")
    description_html: str | None = Field(default=None, alias="descriptionHtml")
    posted_at: datetime | None = Field(default=None, alias="postedAt")
    expires_at: datetime | None = Field(default=None, alias="expiresAt")
    compensation: Compensation | None = None
    tags: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("title", "company_name")
    @classmethod
    def require_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("must not be empty")
        return stripped

    @field_validator("tags")
    @classmethod
    def normalize_tags(cls, value: list[str]) -> list[str]:
        return sorted({tag.strip().lower() for tag in value if tag.strip()})

    @field_validator("remote_type", mode="before")
    @classmethod
    def normalize_remote_type(cls, value: object) -> object:
        return _normalize_enum_value(value)

    @field_validator("employment_type", mode="before")
    @classmethod
    def normalize_employment_type(cls, value: object) -> object:
        return _normalize_enum_value(value)

    @field_validator("experience_level", mode="before")
    @classmethod
    def normalize_experience_level(cls, value: object) -> object:
        return _normalize_enum_value(value)


class WorkerInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    version: str
    run_id: str = Field(alias="runId")


class SourceInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    key: str
    name: str
    type: SourceType
    base_url: HttpUrl = Field(alias="baseUrl")


class IngestionPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    contract_version: str = Field(default="1.0", alias="contractVersion")
    worker: WorkerInfo
    source: SourceInfo
    jobs: list[JobRecord]

    @field_validator("jobs")
    @classmethod
    def require_jobs(cls, value: list[JobRecord]) -> list[JobRecord]:
        if not value:
            raise ValueError("jobs must not be empty")
        return value


class IngestionItemResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source_url: str | None = Field(default=None, alias="sourceUrl")
    status: str
    job_id: str | None = Field(default=None, alias="jobId")
    reason: str | None = None


class IngestionResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    run_id: str = Field(alias="runId")
    accepted: int = 0
    rejected: int = 0
    duplicates: int = 0
    items: list[IngestionItemResult] = Field(default_factory=list)


def build_run_id(source_key: str, now: datetime | None = None) -> str:
    timestamp = (now or datetime.now(UTC)).replace(microsecond=0).isoformat()
    return f"{timestamp}-{source_key}"


def _normalize_enum_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    return normalized or value

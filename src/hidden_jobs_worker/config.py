from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _validate_http_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("HTTP is only allowed for local development hosts")
    return value.rstrip("/")


class SourceRunSettings(BaseSettings):
    """Runtime configuration for source-only operations."""

    model_config = SettingsConfigDict(extra="ignore")

    worker_name: str = Field(default="hidden-jobs-worker", alias="WORKER_NAME")
    worker_version: str = Field(default="0.1.0", alias="WORKER_VERSION")
    worker_log_level: str = Field(default="INFO", alias="WORKER_LOG_LEVEL")
    worker_request_timeout_seconds: float = Field(
        default=15.0, alias="WORKER_REQUEST_TIMEOUT_SECONDS", gt=0
    )
    worker_max_retries: int = Field(default=2, alias="WORKER_MAX_RETRIES", ge=0, le=5)
    worker_batch_size: int = Field(default=100, alias="WORKER_BATCH_SIZE", ge=1, le=500)
    worker_company_request_delay_seconds: float = Field(
        default=1.0, alias="WORKER_COMPANY_REQUEST_DELAY_SECONDS", ge=0
    )
    remotive_api_url: str = Field(
        default="https://remotive.com/api/remote-jobs", alias="REMOTIVE_API_URL"
    )

    @field_validator("remotive_api_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return _validate_http_url(value)


class Settings(SourceRunSettings):
    """Runtime configuration for ingestion operations."""

    spring_api_base_url: str = Field(alias="SPRING_API_BASE_URL")
    worker_ingest_token: str = Field(alias="WORKER_INGEST_TOKEN", repr=False)

    @field_validator("spring_api_base_url")
    @classmethod
    def validate_ingestion_url(cls, value: str) -> str:
        return _validate_http_url(value)

    @field_validator("worker_ingest_token")
    @classmethod
    def validate_token(cls, value: str) -> str:
        if not value.strip() or value == "replace-with-runtime-secret":
            raise ValueError("WORKER_INGEST_TOKEN must be provided at runtime")
        return value

    def redacted(self) -> dict[str, Any]:
        data = self.model_dump(by_alias=True)
        data["WORKER_INGEST_TOKEN"] = "***REDACTED***"
        return data


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache
def get_source_run_settings() -> SourceRunSettings:
    return SourceRunSettings()

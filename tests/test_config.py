import pytest
from pydantic import ValidationError

from hidden_jobs_worker.config import Settings


def test_settings_load_required_values() -> None:
    settings = Settings(
        SPRING_API_BASE_URL="https://api.example.com/",
        WORKER_INGEST_TOKEN="test-token",
    )

    assert settings.spring_api_base_url == "https://api.example.com"
    assert settings.worker_ingest_token == "test-token"
    assert settings.redacted()["WORKER_INGEST_TOKEN"] == "***REDACTED***"


def test_settings_reject_non_local_http_ingestion_url() -> None:
    with pytest.raises(ValidationError):
        Settings(
            SPRING_API_BASE_URL="http://api.example.com",
            WORKER_INGEST_TOKEN="test-token",
        )


def test_settings_allows_local_http_for_development() -> None:
    settings = Settings(
        SPRING_API_BASE_URL="http://localhost:8080",
        WORKER_INGEST_TOKEN="test-token",
    )

    assert settings.spring_api_base_url == "http://localhost:8080"

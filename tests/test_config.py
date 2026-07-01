import pytest
from pydantic import ValidationError

from hidden_jobs_worker.config import Settings, SourceRunSettings


def test_settings_load_required_values() -> None:
    settings = Settings(
        SPRING_API_BASE_URL="https://api.example.com/",
        WORKER_INGEST_TOKEN="test-token",
    )

    assert settings.spring_api_base_url == "https://api.example.com"
    assert settings.worker_ingest_token == "test-token"
    assert settings.worker_request_timeout_seconds == 60
    assert settings.worker_ingest_batch_size == 10
    assert settings.redacted()["WORKER_INGEST_TOKEN"] == "***REDACTED***"


def test_settings_read_http_timeout_env_var() -> None:
    settings = Settings(
        SPRING_API_BASE_URL="https://api.example.com/",
        WORKER_INGEST_TOKEN="test-token",
        WORKER_HTTP_TIMEOUT_SECONDS=45,
    )

    assert settings.worker_request_timeout_seconds == 45


def test_settings_read_ingest_batch_size_env_var() -> None:
    settings = Settings(
        SPRING_API_BASE_URL="https://api.example.com/",
        WORKER_INGEST_TOKEN="test-token",
        WORKER_INGEST_BATCH_SIZE=25,
    )

    assert settings.worker_ingest_batch_size == 25


def test_settings_support_legacy_request_timeout_env_var() -> None:
    settings = Settings(
        SPRING_API_BASE_URL="https://api.example.com/",
        WORKER_INGEST_TOKEN="test-token",
        WORKER_REQUEST_TIMEOUT_SECONDS=20,
    )

    assert settings.worker_request_timeout_seconds == 20


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


def test_source_run_settings_do_not_require_ingestion_token() -> None:
    settings = SourceRunSettings()

    assert settings.remotive_api_url == "https://remotive.com/api/remote-jobs"


def test_settings_ignore_dotenv_files(tmp_path, monkeypatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "SPRING_API_BASE_URL=https://api.example.com\n"
        "WORKER_INGEST_TOKEN=dotenv-token\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SPRING_API_BASE_URL", raising=False)
    monkeypatch.delenv("WORKER_INGEST_TOKEN", raising=False)

    with pytest.raises(ValidationError):
        Settings()

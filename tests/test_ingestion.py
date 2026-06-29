import json

import httpx
import pytest

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.ingestion import IngestionAuthError, IngestionClient
from hidden_jobs_worker.models import (
    IngestionPayload,
    JobRecord,
    SourceInfo,
    SourceType,
    WorkerInfo,
)


def _settings() -> Settings:
    return Settings(
        SPRING_API_BASE_URL="https://api.example.com",
        WORKER_INGEST_TOKEN="test-token",
        WORKER_MAX_RETRIES=1,
    )


def _payload() -> IngestionPayload:
    return IngestionPayload(
        worker=WorkerInfo(name="hidden-jobs-worker", version="0.1.0", runId="run-1"),
        source=SourceInfo(
            key="remotive",
            name="Remotive",
            type=SourceType.REMOTE_JOB_SOURCE,
            baseUrl="https://remotive.com/api/remote-jobs",
        ),
        jobs=[
            JobRecord(
                sourceJobId="1",
                sourceUrl="https://example.com/jobs/1",
                title="Engineer",
                companyName="Example Inc",
            )
        ],
    )


def test_ingestion_client_posts_contract_payload_and_token_header() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json={"runId": "run-1", "accepted": 1, "rejected": 0, "duplicates": 0, "items": []},
        )

    client = IngestionClient(_settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.submit(_payload())

    assert result.accepted == 1
    assert str(seen_requests[0].url) == "https://api.example.com/api/internal/jobs/ingest"
    assert seen_requests[0].headers["X-Worker-Token"] == "test-token"
    assert seen_requests[0].headers["Content-Type"] == "application/json"
    request_json = json.loads(seen_requests[0].content)
    assert request_json["jobs"][0]["remoteType"] == "UNKNOWN"
    assert request_json["jobs"][0]["employmentType"] == "UNKNOWN"


def test_ingestion_client_retries_transient_status() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, text="unavailable")
        return httpx.Response(
            200,
            json={"runId": "run-1", "accepted": 1, "rejected": 0, "duplicates": 0, "items": []},
        )

    client = IngestionClient(_settings(), httpx.Client(transport=httpx.MockTransport(handler)))

    assert client.submit(_payload()).accepted == 1
    assert attempts == 2


def test_ingestion_client_classifies_auth_failure() -> None:
    client = IngestionClient(
        _settings(),
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )

    with pytest.raises(IngestionAuthError):
        client.submit(_payload())

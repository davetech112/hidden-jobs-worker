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
                sourceName="REMOTIVE",
                sourceJobId="1",
                sourceUrl="https://example.com/jobs/1",
                title="Engineer",
                companyName="Example Inc",
            )
        ],
    )


def _payload_with_jobs(count: int) -> IngestionPayload:
    payload = _payload()
    jobs = [
        JobRecord(
            sourceName="REMOTIVE",
            sourceJobId=str(index),
            sourceUrl=f"https://example.com/jobs/{index}",
            title=f"Engineer {index}",
            companyName="Example Inc",
        )
        for index in range(count)
    ]
    return payload.model_copy(update={"jobs": jobs})


def test_ingestion_client_parses_raw_response_and_posts_token_header() -> None:
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
    assert request_json["jobs"][0]["sourceName"] == "REMOTIVE"
    assert request_json["jobs"][0]["remoteType"] == "UNKNOWN"
    assert request_json["jobs"][0]["employmentType"] == "UNKNOWN"


def test_ingestion_client_parses_wrapped_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "runId": "run-1",
                    "received": 1,
                    "saved": 1,
                    "duplicatesSkipped": 0,
                    "failed": 0,
                    "errors": [],
                },
                "message": "Jobs ingested successfully",
                "timestamp": "2026-06-30T00:00:00Z",
            },
        )

    client = IngestionClient(_settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.submit(_payload())

    assert result.run_id == "run-1"
    assert result.received == 1
    assert result.saved_count == 1


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


def test_submit_batches_sends_sixty_jobs_as_three_batches() -> None:
    batch_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batch_sizes.append(len(body["jobs"]))
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "runId": body["worker"]["runId"],
                    "received": len(body["jobs"]),
                    "saved": len(body["jobs"]),
                    "duplicatesSkipped": 0,
                    "failed": 0,
                    "errors": [],
                },
                "message": "Jobs ingested successfully",
                "timestamp": "2026-06-30T00:00:00Z",
            },
        )

    client = IngestionClient(_settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.submit_batches(_payload_with_jobs(60), batch_size=25)

    assert batch_sizes == [25, 25, 10]
    assert result.received == 60
    assert result.saved == 60
    assert result.failed == 0


def test_submit_batches_records_failed_batch_and_continues() -> None:
    batch_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        batch_sizes.append(len(body["jobs"]))
        if body["jobs"][0]["sourceJobId"] == "25":
            return httpx.Response(500, text="temporary failure")
        return httpx.Response(
            200,
            json={
                "runId": body["worker"]["runId"],
                "received": len(body["jobs"]),
                "saved": len(body["jobs"]),
                "duplicatesSkipped": 0,
                "failed": 0,
                "errors": [],
            },
        )

    client = IngestionClient(_settings(), httpx.Client(transport=httpx.MockTransport(handler)))
    result = client.submit_batches(_payload_with_jobs(60), batch_size=25)

    assert batch_sizes == [25, 25, 25, 10]
    assert result.received == 60
    assert result.saved == 35
    assert result.failed == 25
    assert result.has_failures
    assert result.errors


def test_crawl_lifecycle_calls_use_worker_token() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(204)

    client = IngestionClient(_settings(), httpx.Client(transport=httpx.MockTransport(handler)))

    client.start_crawl("company-1")
    client.mark_crawl_success("company-1", jobs_found=12, jobs_ingested=10)
    client.mark_crawl_failure("company-1", "source unavailable")

    assert [request.url.path for request in seen_requests] == [
        "/api/internal/companies/company-1/crawl/start",
        "/api/internal/companies/company-1/crawl/success",
        "/api/internal/companies/company-1/crawl/failure",
    ]
    assert all(request.headers["X-Worker-Token"] == "test-token" for request in seen_requests)
    success_body = json.loads(seen_requests[1].content)
    failure_body = json.loads(seen_requests[2].content)
    assert success_body == {"jobsFound": 12, "jobsIngested": 10}
    assert failure_body == {"errorMessage": "source unavailable"}

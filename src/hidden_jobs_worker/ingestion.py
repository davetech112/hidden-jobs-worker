import logging
from collections.abc import Iterable

import httpx

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.logging import redact_headers
from hidden_jobs_worker.models import IngestionPayload, IngestionResult

LOGGER = logging.getLogger(__name__)
INGESTION_PATH = "/api/internal/jobs/ingest"
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class IngestionClientError(RuntimeError):
    """Raised when the ingestion API cannot process a request."""


class IngestionAuthError(IngestionClientError):
    """Raised when the ingestion API rejects worker authentication."""


class IngestionClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.worker_request_timeout_seconds)

    def submit(self, payload: IngestionPayload) -> IngestionResult:
        url = f"{self._settings.spring_api_base_url}{INGESTION_PATH}"
        headers = {
            "Content-Type": "application/json",
            "X-Worker-Token": self._settings.worker_ingest_token,
        }
        request_body = payload.model_dump(mode="json", by_alias=True)

        response: httpx.Response | None = None
        for attempt in range(self._settings.worker_max_retries + 1):
            response = self._client.post(url, headers=headers, json=request_body)
            if response.status_code not in RETRY_STATUS_CODES:
                break
            LOGGER.warning(
                "ingestion transient failure",
                extra={
                    "status_code": response.status_code,
                    "attempt": attempt + 1,
                    "headers": redact_headers(headers),
                },
            )

        if response is None:
            raise IngestionClientError("ingestion request was not sent")
        if response.status_code in {401, 403}:
            raise IngestionAuthError("ingestion API rejected worker authentication")
        if response.status_code not in {200, 202}:
            raise IngestionClientError(
                f"ingestion API returned status {response.status_code}: {response.text}"
            )

        if response.status_code == 202 and not response.content:
            return IngestionResult(runId=payload.worker.run_id)
        return IngestionResult.model_validate(response.json())


def batch_jobs[T](items: Iterable[T], batch_size: int) -> Iterable[list[T]]:
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch

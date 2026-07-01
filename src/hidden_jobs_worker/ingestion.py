import logging
from collections.abc import Iterable

import httpx

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.logging import redact_headers
from hidden_jobs_worker.models import BatchIngestionResult, IngestionPayload, IngestionResult

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
        request_body = payload.model_dump(mode="json", by_alias=True)
        response = self._post(INGESTION_PATH, request_body)

        if not response.content:
            return IngestionResult(runId=payload.worker.run_id)
        return IngestionResult.model_validate(_unwrap_response_data(response.json()))

    def submit_batches(
        self,
        payload: IngestionPayload,
        batch_size: int,
    ) -> BatchIngestionResult:
        summary = BatchIngestionResult()
        batches = list(batch_jobs(payload.jobs, batch_size))

        for index, job_batch in enumerate(batches, start=1):
            LOGGER.info(
                "submitting ingestion batch",
                extra={
                    "run_id": payload.worker.run_id,
                    "batch_number": index,
                    "batch_total": len(batches),
                    "batch_size": len(job_batch),
                },
            )
            batch_payload = payload.model_copy(update={"jobs": job_batch})
            try:
                result = self.submit(batch_payload)
            except Exception as exc:
                message = f"batch {index} failed: {exc}"
                summary.received += len(job_batch)
                summary.failed += len(job_batch)
                summary.errors.append(message)
                LOGGER.exception(
                    "ingestion batch failed",
                    extra={
                        "run_id": payload.worker.run_id,
                        "batch_number": index,
                        "batch_size": len(job_batch),
                    },
                )
                continue

            received = result.received or len(job_batch)
            summary.received += received
            summary.saved += result.saved_count
            summary.duplicates_skipped += result.duplicate_count
            summary.failed += result.failed_count
            summary.errors.extend(result.errors)
            LOGGER.info(
                "ingestion batch completed",
                extra={
                    "run_id": result.run_id,
                    "batch_number": index,
                    "received": received,
                    "saved": result.saved_count,
                    "duplicates_skipped": result.duplicate_count,
                    "failed": result.failed_count,
                },
            )

        return summary

    def start_career_board_crawl(self, board_id: str) -> None:
        self._post(f"/api/internal/career-boards/{board_id}/crawl/start", {})

    def mark_career_board_crawl_success(self, board_id: str) -> None:
        self._post(f"/api/internal/career-boards/{board_id}/crawl/success", {})

    def mark_career_board_crawl_failure(self, board_id: str, error_message: str) -> None:
        self._post(
            f"/api/internal/career-boards/{board_id}/crawl/failure",
            {"errorMessage": error_message},
        )

    def _post(self, path: str, request_body: dict) -> httpx.Response:
        url = f"{self._settings.spring_api_base_url}{path}"
        headers = {
            "Content-Type": "application/json",
            "X-Worker-Token": self._settings.worker_ingest_token,
        }

        response: httpx.Response | None = None
        for attempt in range(self._settings.worker_max_retries + 1):
            response = self._client.post(url, headers=headers, json=request_body)
            if response.status_code not in RETRY_STATUS_CODES:
                break
            LOGGER.warning(
                "worker API transient failure",
                extra={
                    "path": path,
                    "status_code": response.status_code,
                    "attempt": attempt + 1,
                    "headers": redact_headers(headers),
                },
            )

        if response is None:
            raise IngestionClientError("worker API request was not sent")
        if response.status_code in {401, 403}:
            raise IngestionAuthError("worker API rejected worker authentication")
        if response.status_code not in {200, 202, 204}:
            raise IngestionClientError(
                f"worker API returned status {response.status_code}: {response.text}"
            )
        return response


def batch_jobs[T](items: Iterable[T], batch_size: int) -> Iterable[list[T]]:
    batch: list[T] = []
    for item in items:
        batch.append(item)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _unwrap_response_data(response_body: object) -> object:
    if isinstance(response_body, dict) and isinstance(response_body.get("data"), dict):
        return response_body["data"]
    return response_body

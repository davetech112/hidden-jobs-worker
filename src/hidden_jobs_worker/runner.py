import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.adapters.manager import AtsAdapterManager
from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.ingestion import IngestionClient
from hidden_jobs_worker.models import (
    CareerBoard,
    IngestionPayload,
    JobRecord,
    WorkerInfo,
    build_run_id,
)
from hidden_jobs_worker.registry import CareerBoardRegistryClient

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DueCareerBoardRunResult:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    discovered: int = 0
    submitted: int = 0


def run_due_career_boards(
    settings: Settings,
    dry_run: bool = False,
    registry_client: CareerBoardRegistryClient | None = None,
    ingestion_client: IngestionClient | None = None,
    adapter_manager: AtsAdapterManager | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
) -> DueCareerBoardRunResult:
    registry = registry_client or CareerBoardRegistryClient(settings)
    ingestion = ingestion_client or IngestionClient(settings)
    adapters = adapter_manager or AtsAdapterManager()
    career_boards = registry.get_due_career_boards()

    attempted = 0
    succeeded = 0
    failed = 0
    skipped = 0
    discovered = 0
    submitted = 0

    for index, career_board in enumerate(career_boards):
        if index > 0 and settings.worker_company_request_delay_seconds > 0:
            sleep_func(settings.worker_company_request_delay_seconds)

        adapter = adapters.get_adapter(career_board)
        if adapter is None:
            skipped += 1
            LOGGER.info(
                "career board skipped because atsType is unsupported",
                extra={
                    "board_id": career_board.board_id,
                    "company_id": career_board.company_id,
                    "ats_type": career_board.ats_type,
                },
            )
            continue

        attempted += 1
        board_ingested = 0
        try:
            if not dry_run:
                ingestion.start_career_board_crawl(career_board.board_id)

            jobs = adapter.fetch_jobs(career_board)
            discovered += len(jobs)
            LOGGER.info(
                "career board jobs discovered",
                extra={
                    "board_id": career_board.board_id,
                    "company_id": career_board.company_id,
                    "company_name": career_board.company_name,
                    "ats_type": career_board.ats_type,
                    "discovered_count": len(jobs),
                    "dry_run": dry_run,
                },
            )

            if not dry_run and jobs:
                run_id = build_run_id(f"{career_board.ats_type.lower()}-{career_board.board_id}")
                payload = _build_career_board_payload(
                    settings,
                    career_board,
                    run_id,
                    jobs,
                    adapter,
                )
                ingestion_result = ingestion.submit_batches(
                    payload,
                    settings.worker_ingest_batch_size,
                )
                board_ingested = ingestion_result.saved
                submitted += board_ingested
                if ingestion_result.has_failures:
                    raise RuntimeError(
                        "one or more ingestion batches failed: "
                        + "; ".join(ingestion_result.errors)
                    )

            if not dry_run:
                ingestion.mark_career_board_crawl_success(career_board.board_id)
            succeeded += 1
        except Exception as exc:
            failed += 1
            if not dry_run:
                try:
                    ingestion.mark_career_board_crawl_failure(career_board.board_id, str(exc))
                except Exception:
                    LOGGER.exception(
                        "career board crawl failure reporting failed",
                        extra={
                            "board_id": career_board.board_id,
                            "company_id": career_board.company_id,
                            "company_name": career_board.company_name,
                        },
                    )
            LOGGER.exception(
                "career board crawl failed",
                extra={
                    "board_id": career_board.board_id,
                    "company_id": career_board.company_id,
                    "company_name": career_board.company_name,
                },
            )

    return DueCareerBoardRunResult(
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        discovered=discovered,
        submitted=submitted,
    )


def _build_career_board_payload(
    settings: Settings,
    career_board: CareerBoard,
    run_id: str,
    job_batch: list[JobRecord],
    adapter: AtsAdapter,
) -> IngestionPayload:
    return IngestionPayload(
        worker=WorkerInfo(
            name=settings.worker_name,
            version=settings.worker_version,
            runId=run_id,
        ),
        source=adapter.source_info(career_board),
        jobs=job_batch,
    )

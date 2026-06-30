import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.adapters.manager import AtsAdapterManager
from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.ingestion import IngestionClient
from hidden_jobs_worker.models import (
    CompanyRecord,
    IngestionPayload,
    JobRecord,
    WorkerInfo,
    build_run_id,
)
from hidden_jobs_worker.registry import CompanyRegistryClient

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class DueCompanyRunResult:
    attempted: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    discovered: int = 0
    submitted: int = 0


def run_due_companies(
    settings: Settings,
    dry_run: bool = False,
    registry_client: CompanyRegistryClient | None = None,
    ingestion_client: IngestionClient | None = None,
    adapter_manager: AtsAdapterManager | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
) -> DueCompanyRunResult:
    registry = registry_client or CompanyRegistryClient(settings)
    ingestion = ingestion_client or IngestionClient(settings)
    adapters = adapter_manager or AtsAdapterManager()
    companies = registry.get_due_companies()

    attempted = 0
    succeeded = 0
    failed = 0
    skipped = 0
    discovered = 0
    submitted = 0

    for index, company in enumerate(companies):
        if index > 0 and settings.worker_company_request_delay_seconds > 0:
            sleep_func(settings.worker_company_request_delay_seconds)

        adapter = adapters.get_adapter(company)
        if adapter is None:
            skipped += 1
            LOGGER.info(
                "company skipped because atsType is unsupported",
                extra={"company_id": company.id, "ats_type": company.ats_type},
            )
            continue

        attempted += 1
        company_ingested = 0
        try:
            if not dry_run:
                ingestion.start_crawl(company.id)

            jobs = adapter.fetch_jobs(company)
            discovered += len(jobs)
            LOGGER.info(
                "company jobs discovered",
                extra={
                    "company_id": company.id,
                    "company_name": company.name,
                    "ats_type": company.ats_type,
                    "discovered_count": len(jobs),
                    "dry_run": dry_run,
                },
            )

            if not dry_run and jobs:
                run_id = build_run_id(f"{company.ats_type.lower()}-{company.id}")
                payload = _build_company_payload(settings, company, run_id, jobs, adapter)
                ingestion_result = ingestion.submit_batches(
                    payload,
                    settings.worker_ingest_batch_size,
                )
                company_ingested = ingestion_result.saved
                submitted += company_ingested
                if ingestion_result.has_failures:
                    raise RuntimeError(
                        "one or more ingestion batches failed: "
                        + "; ".join(ingestion_result.errors)
                    )

            if not dry_run:
                ingestion.mark_crawl_success(
                    company.id,
                    jobs_found=len(jobs),
                    jobs_ingested=company_ingested,
                )
            succeeded += 1
        except Exception as exc:
            failed += 1
            if not dry_run:
                try:
                    ingestion.mark_crawl_failure(company.id, str(exc))
                except Exception:
                    LOGGER.exception(
                        "company crawl failure reporting failed",
                        extra={"company_id": company.id, "company_name": company.name},
                    )
            LOGGER.exception(
                "company crawl failed",
                extra={"company_id": company.id, "company_name": company.name},
            )

    return DueCompanyRunResult(
        attempted=attempted,
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        discovered=discovered,
        submitted=submitted,
    )


def _build_company_payload(
    settings: Settings,
    company: CompanyRecord,
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
        source=adapter.source_info(company),
        jobs=job_batch,
    )

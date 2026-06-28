import argparse
import logging
from collections.abc import Sequence

from hidden_jobs_worker.adapters.remotive import RemotiveAdapter
from hidden_jobs_worker.config import get_settings, get_source_run_settings
from hidden_jobs_worker.ingestion import IngestionClient, batch_jobs
from hidden_jobs_worker.logging import configure_logging
from hidden_jobs_worker.models import IngestionPayload, WorkerInfo, build_run_id

LOGGER = logging.getLogger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hidden-jobs-worker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_source = subparsers.add_parser("run-source", help="Run one source manually.")
    run_source.add_argument("source", choices=["remotive"])
    run_source.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse without ingesting.",
    )

    args = parser.parse_args(argv)
    settings = get_source_run_settings()
    configure_logging(settings.worker_log_level)

    if args.command == "run-source":
        return _run_source(args.source, dry_run=args.dry_run)
    return 1


def _run_source(source: str, dry_run: bool) -> int:
    source_settings = get_source_run_settings()
    adapter = RemotiveAdapter(
        api_url=source_settings.remotive_api_url,
        timeout_seconds=source_settings.worker_request_timeout_seconds,
    )
    jobs = adapter.fetch_jobs()
    run_id = build_run_id(adapter.metadata.key)

    LOGGER.info(
        "source run discovered jobs",
        extra={"source": source, "run_id": run_id, "discovered_count": len(jobs)},
    )
    if dry_run:
        return 0

    settings = get_settings()
    client = IngestionClient(settings)
    for job_batch in batch_jobs(jobs, settings.worker_batch_size):
        payload = IngestionPayload(
            worker=WorkerInfo(
                name=settings.worker_name,
                version=settings.worker_version,
                runId=run_id,
            ),
            source=adapter.metadata.to_source_info(),
            jobs=job_batch,
        )
        result = client.submit(payload)
        LOGGER.info(
            "ingestion batch submitted",
            extra={
                "run_id": result.run_id,
                "accepted": result.accepted,
                "rejected": result.rejected,
                "duplicates": result.duplicates,
            },
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

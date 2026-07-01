import argparse
import logging
from collections.abc import Sequence

from hidden_jobs_worker.adapters.remotive import RemotiveAdapter
from hidden_jobs_worker.config import get_settings, get_source_run_settings
from hidden_jobs_worker.discovery.engine import CompanyDiscoveryEngine
from hidden_jobs_worker.discovery.registration import DiscoveryRegistrationClient
from hidden_jobs_worker.ingestion import IngestionClient
from hidden_jobs_worker.logging import configure_logging
from hidden_jobs_worker.models import (
    AtsType,
    CompanyCandidate,
    IngestionPayload,
    WorkerInfo,
    build_run_id,
)
from hidden_jobs_worker.runner import run_due_companies

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

    run_due_companies_command = subparsers.add_parser(
        "run-due-companies",
        help="Fetch due companies, crawl supported ATS boards, and ingest discovered jobs.",
    )
    run_due_companies_command.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse due companies without ingesting jobs.",
    )

    discover_companies = subparsers.add_parser(
        "discover-companies",
        help="Discover company ATS metadata from a static seed file.",
    )
    discover_companies.add_argument(
        "--seed-file",
        default="discovery/seeds/companies.yml",
        help="Path to the static company seed file.",
    )
    discover_companies.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover candidates without submitting them to the backend.",
    )
    discover_companies.add_argument("--limit", type=int, default=None)
    discover_companies.add_argument(
        "--min-confidence",
        type=float,
        default=0.90,
        help="Minimum confidence required before submitting a discovery.",
    )

    args = parser.parse_args(argv)
    settings = get_source_run_settings()
    configure_logging(settings.worker_log_level)

    if args.command == "run-source":
        return _run_source(args.source, dry_run=args.dry_run)
    if args.command == "run-due-companies":
        settings = get_settings()
        result = run_due_companies(settings, dry_run=args.dry_run)
        LOGGER.info(
            "due company run completed",
            extra={
                "attempted": result.attempted,
                "succeeded": result.succeeded,
                "failed": result.failed,
                "skipped": result.skipped,
                "discovered": result.discovered,
                "submitted": result.submitted,
                "dry_run": args.dry_run,
            },
        )
        return 0
    if args.command == "discover-companies":
        candidates = CompanyDiscoveryEngine().discover_from_seed_file(
            seed_file=args.seed_file,
            limit=args.limit,
        )
        verified_count = sum(1 for candidate in candidates if candidate.confidence_score >= 0.9)
        print(
            "company discovery completed: "
            f"candidates={len(candidates)} verified={verified_count} dry_run={args.dry_run}"
        )
        for candidate in candidates:
            print(
                f"{candidate.name}: atsType={candidate.ats_type} "
                f"atsSlug={candidate.ats_slug or '-'} "
                f"confidence={candidate.confidence_score:.2f}"
            )
        if not args.dry_run:
            settings = get_settings()
            submit_summary = _submit_discovery_candidates(
                candidates,
                min_confidence=args.min_confidence,
                registration_client=DiscoveryRegistrationClient(settings),
            )
            LOGGER.info(
                "company discovery submission completed",
                extra={
                    "submitted": submit_summary["submitted"],
                    "ignored": submit_summary["ignored"],
                    "skipped": submit_summary["skipped"],
                    "failed": submit_summary["failed"],
                    "min_confidence": args.min_confidence,
                },
            )
        return 0
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
    if not jobs:
        return 0

    settings = get_settings()
    client = IngestionClient(settings)
    payload = IngestionPayload(
        worker=WorkerInfo(
            name=settings.worker_name,
            version=settings.worker_version,
            runId=run_id,
        ),
        source=adapter.metadata.to_source_info(),
        jobs=jobs,
    )
    result = client.submit_batches(payload, settings.worker_ingest_batch_size)
    LOGGER.info(
        "source ingestion completed",
        extra={
            "run_id": run_id,
            "received": result.received,
            "saved": result.saved,
            "duplicates_skipped": result.duplicates_skipped,
            "failed": result.failed,
        },
    )
    return 0


def _submit_discovery_candidates(
    candidates: list[CompanyCandidate],
    min_confidence: float,
    registration_client: DiscoveryRegistrationClient,
) -> dict[str, int]:
    summary = {"submitted": 0, "ignored": 0, "skipped": 0, "failed": 0}

    for candidate in candidates:
        if candidate.confidence_score < min_confidence or candidate.ats_type == AtsType.UNKNOWN:
            summary["skipped"] += 1
            LOGGER.info(
                "skipping discovery candidate",
                extra={
                    "candidate_name": candidate.name,
                    "ats_type": candidate.ats_type,
                    "confidence": candidate.confidence_score,
                    "min_confidence": min_confidence,
                },
            )
            continue

        try:
            result = registration_client.submit_career_board(candidate)
        except Exception:
            summary["failed"] += 1
            LOGGER.exception(
                "discovery candidate submission failed",
                extra={
                    "candidate_name": candidate.name,
                    "ats_type": candidate.ats_type,
                    "ats_slug": candidate.ats_slug,
                },
            )
            continue

        if result.submitted:
            summary["submitted"] += 1
        elif result.ignored:
            summary["ignored"] += 1

    return summary


if __name__ == "__main__":
    raise SystemExit(main())

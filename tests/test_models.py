from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from hidden_jobs_worker.models import (
    EmploymentType,
    ExperienceLevel,
    IngestionPayload,
    JobRecord,
    RemoteType,
    SourceInfo,
    SourceType,
    WorkerInfo,
    build_run_id,
)


def test_job_record_serializes_contract_aliases() -> None:
    job = JobRecord(
        sourceName="REMOTIVE",
        sourceJobId="123",
        sourceUrl="https://example.com/jobs/123",
        title=" Backend Engineer ",
        companyName="Example Inc",
        tags=["Python", "python", " backend "],
    )

    assert job.title == "Backend Engineer"
    assert job.source_name == "REMOTIVE"
    assert job.tags == ["backend", "python"]
    assert job.model_dump(mode="json", by_alias=True)["sourceJobId"] == "123"


def test_job_record_serializes_backend_enum_names() -> None:
    job = JobRecord(
        sourceName="remotive",
        sourceUrl="https://example.com/jobs/123",
        title="Backend Engineer",
        companyName="Example Inc",
        remoteType="remote",
        employmentType="full-time",
        experienceLevel="senior level",
    )

    serialized = job.model_dump(mode="json", by_alias=True)

    assert job.remote_type == RemoteType.REMOTE
    assert job.source_name == "REMOTIVE"
    assert job.employment_type == EmploymentType.FULL_TIME
    assert job.experience_level == ExperienceLevel.SENIOR_LEVEL
    assert serialized["remoteType"] == "REMOTE"
    assert serialized["sourceName"] == "REMOTIVE"
    assert serialized["employmentType"] == "FULL_TIME"
    assert serialized["experienceLevel"] == "SENIOR_LEVEL"


def test_ingestion_payload_requires_jobs() -> None:
    with pytest.raises(ValidationError):
        IngestionPayload(
            worker=WorkerInfo(name="hidden-jobs-worker", version="0.1.0", runId="run-1"),
            source=SourceInfo(
                key="source",
                name="Source",
                type=SourceType.REMOTE_JOB_SOURCE,
                baseUrl="https://example.com/jobs",
            ),
            jobs=[],
        )


def test_build_run_id_uses_source_key() -> None:
    run_id = build_run_id("remotive", datetime(2026, 6, 28, tzinfo=UTC))

    assert run_id == "2026-06-28T00:00:00+00:00-remotive"

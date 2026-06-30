from dataclasses import dataclass

from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.models import AtsType, BatchIngestionResult, CompanyRecord, JobRecord
from hidden_jobs_worker.runner import run_due_companies


def _settings() -> Settings:
    return Settings(
        SPRING_API_BASE_URL="https://api.example.com",
        WORKER_INGEST_TOKEN="test-token",
        WORKER_COMPANY_REQUEST_DELAY_SECONDS=0,
    )


def _company(id_value: str, ats_type: str = "GREENHOUSE") -> CompanyRecord:
    return CompanyRecord(
        id=id_value,
        name=f"{id_value} Labs",
        websiteUrl="https://example.com",
        careersUrl="https://example.com/careers",
        atsType=ats_type,
        atsSlug=id_value,
        enabled=True,
    )


def _job(company: CompanyRecord) -> JobRecord:
    return JobRecord(
        sourceName=company.ats_type,
        sourceJobId=f"{company.id}-job",
        sourceUrl=f"https://example.com/jobs/{company.id}",
        title="Engineer",
        companyName=company.name,
    )


@dataclass
class FakeRegistryClient:
    companies: list[CompanyRecord]

    def get_due_companies(self) -> list[CompanyRecord]:
        return self.companies


class FakeIngestionClient:
    def __init__(self) -> None:
        self.payloads = []
        self.started = []
        self.succeeded = []
        self.failed = []
        self.fail_submission_for_company_ids: set[str] = set()
        self.batch_sizes = []

    def submit_batches(self, payload, batch_size: int) -> BatchIngestionResult:
        self.payloads.append(payload)
        self.batch_sizes.append(batch_size)
        company_id = payload.jobs[0].source_job_id.split("-")[0]
        if company_id in self.fail_submission_for_company_ids:
            return BatchIngestionResult(
                received=len(payload.jobs),
                saved=0,
                failed=len(payload.jobs),
                errors=["backend unavailable"],
            )
        return BatchIngestionResult(received=len(payload.jobs), saved=len(payload.jobs))

    def start_crawl(self, company_id: str) -> None:
        self.started.append(company_id)

    def mark_crawl_success(self, company_id: str, jobs_found: int, jobs_ingested: int) -> None:
        self.succeeded.append((company_id, jobs_found, jobs_ingested))

    def mark_crawl_failure(self, company_id: str, error_message: str) -> None:
        self.failed.append((company_id, error_message))


class FakeAtsAdapter(AtsAdapter):
    ats_type = AtsType.GREENHOUSE
    source_name = "GREENHOUSE"
    base_url = "https://example.com"

    def fetch_jobs(self, company: CompanyRecord) -> list[JobRecord]:
        if company.id == "failed":
            raise RuntimeError("source unavailable")
        return [_job(company)]

    def parse_jobs(self, company: CompanyRecord, payload) -> list[JobRecord]:
        return []


class FakeAdapterManager:
    def __init__(self) -> None:
        self.adapter = FakeAtsAdapter()

    def get_adapter(self, company: CompanyRecord):
        if company.ats_type == AtsType.GREENHOUSE:
            return self.adapter
        return None


def test_run_due_companies_dry_run_does_not_ingest() -> None:
    ingestion = FakeIngestionClient()
    result = run_due_companies(
        _settings(),
        dry_run=True,
        registry_client=FakeRegistryClient([_company("one")]),
        ingestion_client=ingestion,
        adapter_manager=FakeAdapterManager(),
    )

    assert result.attempted == 1
    assert result.succeeded == 1
    assert result.discovered == 1
    assert result.submitted == 0
    assert ingestion.payloads == []
    assert ingestion.started == []
    assert ingestion.succeeded == []
    assert ingestion.failed == []


def test_run_due_companies_one_failure_does_not_stop_others() -> None:
    ingestion = FakeIngestionClient()
    companies = [_company("failed"), _company("two"), _company("custom", "CUSTOM")]
    result = run_due_companies(
        _settings(),
        registry_client=FakeRegistryClient(companies),
        ingestion_client=ingestion,
        adapter_manager=FakeAdapterManager(),
    )

    assert result.attempted == 2
    assert result.failed == 1
    assert result.succeeded == 1
    assert result.skipped == 1
    assert result.submitted == 1
    assert len(ingestion.payloads) == 1
    assert ingestion.payloads[0].jobs[0].company_name == "two Labs"
    assert ingestion.started == ["failed", "two"]
    assert ingestion.succeeded == [("two", 1, 1)]
    assert len(ingestion.failed) == 1
    assert ingestion.failed[0][0] == "failed"


def test_run_due_companies_marks_success_with_found_and_ingested_counts() -> None:
    ingestion = FakeIngestionClient()
    result = run_due_companies(
        _settings(),
        registry_client=FakeRegistryClient([_company("one")]),
        ingestion_client=ingestion,
        adapter_manager=FakeAdapterManager(),
    )

    assert result.succeeded == 1
    assert result.failed == 0
    assert result.discovered == 1
    assert result.submitted == 1
    assert ingestion.started == ["one"]
    assert ingestion.succeeded == [("one", 1, 1)]
    assert ingestion.failed == []
    assert ingestion.batch_sizes == [25]


def test_run_due_companies_marks_ingestion_failure_and_continues() -> None:
    ingestion = FakeIngestionClient()
    ingestion.fail_submission_for_company_ids.add("one")
    result = run_due_companies(
        _settings(),
        registry_client=FakeRegistryClient([_company("one"), _company("two")]),
        ingestion_client=ingestion,
        adapter_manager=FakeAdapterManager(),
    )

    assert result.attempted == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.submitted == 1
    assert ingestion.started == ["one", "two"]
    assert ingestion.succeeded == [("two", 1, 1)]
    assert len(ingestion.failed) == 1
    assert ingestion.failed[0][0] == "one"
    assert "ingestion batches failed" in ingestion.failed[0][1]

from dataclasses import dataclass

from hidden_jobs_worker.adapters.ats import AtsAdapter
from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.models import AtsType, BatchIngestionResult, CareerBoard, JobRecord
from hidden_jobs_worker.runner import run_due_career_boards


def _settings() -> Settings:
    return Settings(
        SPRING_API_BASE_URL="https://api.example.com",
        WORKER_INGEST_TOKEN="test-token",
        WORKER_COMPANY_REQUEST_DELAY_SECONDS=0,
    )


def _career_board(id_value: str, ats_type: str = "GREENHOUSE") -> CareerBoard:
    return CareerBoard(
        boardId=id_value,
        boardUrl=f"https://boards.example.com/{id_value}",
        companyId=f"{id_value}-company",
        companyName=f"{id_value} Labs",
        websiteUrl="https://example.com",
        careersUrl="https://example.com/careers",
        atsType=ats_type,
        atsSlug=id_value,
        confidenceScore=0.95,
        failureCount=0,
    )


def _job(career_board: CareerBoard) -> JobRecord:
    return JobRecord(
        sourceName=career_board.ats_type,
        sourceJobId=f"{career_board.board_id}-job",
        sourceUrl=f"https://example.com/jobs/{career_board.board_id}",
        title="Engineer",
        companyName=career_board.company_name,
    )


@dataclass
class FakeRegistryClient:
    career_boards: list[CareerBoard]

    def get_due_career_boards(self) -> list[CareerBoard]:
        return self.career_boards


class FakeIngestionClient:
    def __init__(self) -> None:
        self.payloads = []
        self.started = []
        self.succeeded = []
        self.failed = []
        self.fail_submission_for_board_ids: set[str] = set()
        self.batch_sizes = []

    def submit_batches(self, payload, batch_size: int) -> BatchIngestionResult:
        self.payloads.append(payload)
        self.batch_sizes.append(batch_size)
        board_id = payload.jobs[0].source_job_id.removesuffix("-job")
        if board_id in self.fail_submission_for_board_ids:
            return BatchIngestionResult(
                received=len(payload.jobs),
                saved=0,
                failed=len(payload.jobs),
                errors=["backend unavailable"],
            )
        return BatchIngestionResult(received=len(payload.jobs), saved=len(payload.jobs))

    def start_career_board_crawl(self, board_id: str) -> None:
        self.started.append(board_id)

    def mark_career_board_crawl_success(self, board_id: str) -> None:
        self.succeeded.append(board_id)

    def mark_career_board_crawl_failure(self, board_id: str, error_message: str) -> None:
        self.failed.append((board_id, error_message))


class FakeAtsAdapter(AtsAdapter):
    ats_type = AtsType.GREENHOUSE
    source_name = "GREENHOUSE"
    base_url = "https://example.com"

    def fetch_jobs(self, career_board: CareerBoard) -> list[JobRecord]:
        if career_board.board_id == "failed":
            raise RuntimeError("source unavailable")
        return [_job(career_board)]

    def parse_jobs(self, career_board: CareerBoard, payload) -> list[JobRecord]:
        return []


class FakeAdapterManager:
    def __init__(self) -> None:
        self.adapter = FakeAtsAdapter()
        self.seen_boards = []

    def get_adapter(self, career_board: CareerBoard):
        self.seen_boards.append(career_board)
        if career_board.ats_type == AtsType.GREENHOUSE:
            return self.adapter
        return None


def test_run_due_career_boards_dry_run_does_not_ingest_or_mutate_lifecycle() -> None:
    ingestion = FakeIngestionClient()
    result = run_due_career_boards(
        _settings(),
        dry_run=True,
        registry_client=FakeRegistryClient([_career_board("one")]),
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


def test_run_due_career_boards_dispatches_adapter_from_board_ats_type() -> None:
    adapter_manager = FakeAdapterManager()
    result = run_due_career_boards(
        _settings(),
        dry_run=True,
        registry_client=FakeRegistryClient([_career_board("one", "GREENHOUSE")]),
        ingestion_client=FakeIngestionClient(),
        adapter_manager=adapter_manager,
    )

    assert result.succeeded == 1
    assert adapter_manager.seen_boards[0].board_id == "one"
    assert adapter_manager.seen_boards[0].ats_type == AtsType.GREENHOUSE


def test_run_due_career_boards_one_failure_does_not_stop_others() -> None:
    ingestion = FakeIngestionClient()
    boards = [_career_board("failed"), _career_board("two"), _career_board("custom", "CUSTOM")]
    result = run_due_career_boards(
        _settings(),
        registry_client=FakeRegistryClient(boards),
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
    assert ingestion.succeeded == ["two"]
    assert len(ingestion.failed) == 1
    assert ingestion.failed[0][0] == "failed"


def test_run_due_career_boards_marks_success_and_batches() -> None:
    ingestion = FakeIngestionClient()
    result = run_due_career_boards(
        _settings(),
        registry_client=FakeRegistryClient([_career_board("one")]),
        ingestion_client=ingestion,
        adapter_manager=FakeAdapterManager(),
    )

    assert result.succeeded == 1
    assert result.failed == 0
    assert result.discovered == 1
    assert result.submitted == 1
    assert ingestion.started == ["one"]
    assert ingestion.succeeded == ["one"]
    assert ingestion.failed == []
    assert ingestion.batch_sizes == [25]


def test_run_due_career_boards_marks_ingestion_failure_and_continues() -> None:
    ingestion = FakeIngestionClient()
    ingestion.fail_submission_for_board_ids.add("one")
    result = run_due_career_boards(
        _settings(),
        registry_client=FakeRegistryClient([_career_board("one"), _career_board("two")]),
        ingestion_client=ingestion,
        adapter_manager=FakeAdapterManager(),
    )

    assert result.attempted == 2
    assert result.succeeded == 1
    assert result.failed == 1
    assert result.submitted == 1
    assert ingestion.started == ["one", "two"]
    assert ingestion.succeeded == ["two"]
    assert len(ingestion.failed) == 1
    assert ingestion.failed[0][0] == "one"
    assert "ingestion batches failed" in ingestion.failed[0][1]

import httpx

from hidden_jobs_worker import cli
from hidden_jobs_worker.runner import DueCareerBoardRunResult


def test_cli_dry_run_does_not_require_ingestion_token(monkeypatch) -> None:
    monkeypatch.delenv("SPRING_API_BASE_URL", raising=False)
    monkeypatch.delenv("WORKER_INGEST_TOKEN", raising=False)
    monkeypatch.setenv("REMOTIVE_API_URL", "https://remotive.test/jobs")
    cli.get_source_run_settings.cache_clear()
    cli.get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "abc",
                        "url": "https://remotive.test/jobs/abc",
                        "title": "Data Engineer",
                        "company_name": "Example Inc",
                    }
                ]
            },
        )

    original_client = cli.RemotiveAdapter

    class TestRemotiveAdapter(original_client):
        def __init__(self, api_url: str, timeout_seconds: float) -> None:
            super().__init__(
                api_url=api_url,
                timeout_seconds=timeout_seconds,
                client=httpx.Client(transport=httpx.MockTransport(handler)),
            )

    monkeypatch.setattr(cli, "RemotiveAdapter", TestRemotiveAdapter)

    assert cli.main(["run-source", "remotive", "--dry-run"]) == 0


def test_cli_run_due_career_boards_dry_run(monkeypatch) -> None:
    seen_dry_run_values: list[bool] = []
    monkeypatch.setenv("SPRING_API_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("WORKER_INGEST_TOKEN", "test-token")
    cli.get_source_run_settings.cache_clear()
    cli.get_settings.cache_clear()

    def fake_run_due_career_boards(settings, dry_run: bool):
        seen_dry_run_values.append(dry_run)
        return DueCareerBoardRunResult(attempted=1, succeeded=1)

    monkeypatch.setattr(cli, "run_due_career_boards", fake_run_due_career_boards)

    assert cli.main(["run-due-career-boards", "--dry-run"]) == 0
    assert seen_dry_run_values == [True]

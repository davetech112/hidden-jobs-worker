import httpx
import pytest

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.registry import CareerBoardRegistryAuthError, CareerBoardRegistryClient


def _settings() -> Settings:
    return Settings(
        SPRING_API_BASE_URL="https://api.example.com",
        WORKER_INGEST_TOKEN="test-token",
    )


def test_career_board_registry_client_fetches_due_career_boards() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "content": [
                        {
                            "boardId": "board-1",
                            "boardUrl": "https://boards.greenhouse.io/example",
                            "atsType": "GREENHOUSE",
                            "atsSlug": "example",
                            "companyId": "company-1",
                            "companyName": "Example Labs",
                            "websiteUrl": "https://example.com",
                            "careersUrl": "https://example.com/careers",
                            "confidenceScore": 0.95,
                            "failureCount": 0,
                        }
                    ],
                    "page": 1,
                    "size": 10,
                    "totalElements": 1,
                    "totalPages": 1,
                    "first": True,
                    "last": True,
                },
                "message": "ok",
            },
        )

    client = CareerBoardRegistryClient(
        _settings(),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    boards = client.get_due_career_boards(page=1, size=10)

    assert len(boards) == 1
    assert boards[0].company_name == "Example Labs"
    assert boards[0].board_id == "board-1"
    assert boards[0].ats_slug == "example"
    assert str(seen_requests[0].url) == (
        "https://api.example.com/api/internal/career-boards/due-for-crawl?page=1&size=10"
    )
    assert seen_requests[0].headers["X-Worker-Token"] == "test-token"


def test_career_board_registry_client_classifies_auth_failure() -> None:
    client = CareerBoardRegistryClient(
        _settings(),
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )

    with pytest.raises(CareerBoardRegistryAuthError):
        client.get_due_career_boards()

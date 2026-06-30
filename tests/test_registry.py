import httpx
import pytest

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.registry import CompanyRegistryAuthError, CompanyRegistryClient


def _settings() -> Settings:
    return Settings(
        SPRING_API_BASE_URL="https://api.example.com",
        WORKER_INGEST_TOKEN="test-token",
    )


def test_company_registry_client_fetches_due_companies() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "company-1",
                        "name": "Example Labs",
                        "websiteUrl": "https://example.com",
                        "careersUrl": "https://example.com/careers",
                        "atsType": "GREENHOUSE",
                        "atsSlug": "example",
                        "enabled": True,
                    }
                ],
                "message": "ok",
            },
        )

    client = CompanyRegistryClient(
        _settings(),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )
    companies = client.get_due_companies(page=1, size=10)

    assert len(companies) == 1
    assert companies[0].name == "Example Labs"
    assert companies[0].ats_slug == "example"
    assert str(seen_requests[0].url) == (
        "https://api.example.com/api/internal/companies/due-for-crawl?page=1&size=10"
    )
    assert seen_requests[0].headers["X-Worker-Token"] == "test-token"


def test_company_registry_client_classifies_auth_failure() -> None:
    client = CompanyRegistryClient(
        _settings(),
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )

    with pytest.raises(CompanyRegistryAuthError):
        client.get_due_companies()

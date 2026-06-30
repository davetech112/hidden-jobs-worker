import httpx

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.models import CompanyRecord, CompanyRegistryResult

COMPANIES_DUE_FOR_CRAWL_PATH = "/api/internal/companies/due-for-crawl"


class CompanyRegistryClientError(RuntimeError):
    """Raised when the company registry API cannot process a request."""


class CompanyRegistryAuthError(CompanyRegistryClientError):
    """Raised when the company registry API rejects worker authentication."""


class CompanyRegistryClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.worker_request_timeout_seconds)

    def get_due_companies(self, page: int = 0, size: int = 20) -> list[CompanyRecord]:
        url = f"{self._settings.spring_api_base_url}{COMPANIES_DUE_FOR_CRAWL_PATH}"
        response = self._client.get(
            url,
            headers={"X-Worker-Token": self._settings.worker_ingest_token},
            params={"page": page, "size": size},
        )

        if response.status_code in {401, 403}:
            raise CompanyRegistryAuthError("company registry rejected worker authentication")
        if response.status_code != 200:
            raise CompanyRegistryClientError(
                f"company registry returned status {response.status_code}: {response.text}"
            )

        body = response.json()
        if isinstance(body, list):
            return [CompanyRecord.model_validate(item) for item in body]
        return CompanyRegistryResult.model_validate(body).data

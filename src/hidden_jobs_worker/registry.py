import httpx

from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.models import CareerBoard, CareerBoardRegistryResult

CAREER_BOARDS_DUE_FOR_CRAWL_PATH = "/api/internal/career-boards/due-for-crawl"


class CareerBoardRegistryClientError(RuntimeError):
    """Raised when the career board registry API cannot process a request."""


class CareerBoardRegistryAuthError(CareerBoardRegistryClientError):
    """Raised when the career board registry API rejects worker authentication."""


class CareerBoardRegistryClient:
    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client or httpx.Client(timeout=settings.worker_request_timeout_seconds)

    def get_due_career_boards(self, page: int = 0, size: int = 20) -> list[CareerBoard]:
        url = f"{self._settings.spring_api_base_url}{CAREER_BOARDS_DUE_FOR_CRAWL_PATH}"
        response = self._client.get(
            url,
            headers={"X-Worker-Token": self._settings.worker_ingest_token},
            params={"page": page, "size": size},
        )

        if response.status_code in {401, 403}:
            raise CareerBoardRegistryAuthError(
                "career board registry rejected worker authentication"
            )
        if response.status_code != 200:
            raise CareerBoardRegistryClientError(
                f"career board registry returned status {response.status_code}: {response.text}"
            )

        body = response.json()
        if isinstance(body, list):
            return [CareerBoard.model_validate(item) for item in body]
        if isinstance(body, dict) and isinstance(body.get("data"), dict):
            content = body["data"].get("content")
            if isinstance(content, list):
                return [CareerBoard.model_validate(item) for item in content]
        return CareerBoardRegistryResult.model_validate(body).data

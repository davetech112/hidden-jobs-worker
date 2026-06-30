import httpx

from hidden_jobs_worker.models import AtsType


class BoardVerifier:
    def __init__(self, client: httpx.Client | None = None, timeout_seconds: float = 30.0) -> None:
        self._client = client or httpx.Client(timeout=timeout_seconds)

    def verify(self, ats_type: AtsType, ats_slug: str | None) -> bool:
        if not ats_slug:
            return False
        if ats_type == AtsType.GREENHOUSE:
            return self._is_reachable(
                f"https://boards-api.greenhouse.io/v1/boards/{ats_slug}/jobs"
            )
        if ats_type == AtsType.LEVER:
            return self._is_reachable(f"https://api.lever.co/v0/postings/{ats_slug}?mode=json")
        return False

    def _is_reachable(self, url: str) -> bool:
        try:
            response = self._client.get(url)
        except httpx.HTTPError:
            return False
        return 200 <= response.status_code < 400

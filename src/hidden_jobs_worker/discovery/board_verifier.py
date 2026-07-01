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
        if ats_type == AtsType.ASHBY:
            return self._is_any_reachable(
                (
                    f"https://api.ashbyhq.com/posting-api/job-board/{ats_slug}",
                    f"https://jobs.ashbyhq.com/{ats_slug}",
                )
            )
        if ats_type == AtsType.WORKABLE:
            return self._is_reachable(f"https://apply.workable.com/{ats_slug}")
        if ats_type == AtsType.SMARTRECRUITERS:
            return self._is_reachable(
                f"https://api.smartrecruiters.com/v1/companies/{ats_slug}/postings"
            )
        if ats_type == AtsType.TEAMTAILOR:
            return self._is_reachable(f"https://{ats_slug}.teamtailor.com/jobs")
        if ats_type == AtsType.RECRUITEE:
            return self._is_reachable(f"https://{ats_slug}.recruitee.com/api/offers/")
        if ats_type == AtsType.COMEET:
            return self._is_reachable(
                f"https://www.comeet.com/careers-api/2.0/company/{ats_slug}/positions"
            )
        if ats_type == AtsType.PERSONIO:
            return self._is_reachable(f"https://{ats_slug}.jobs.personio.com/xml")
        return False

    def _is_any_reachable(self, urls: tuple[str, ...]) -> bool:
        return any(self._is_reachable(url) for url in urls)

    def _is_reachable(self, url: str) -> bool:
        try:
            response = self._client.get(url)
        except httpx.HTTPError:
            return False
        return 200 <= response.status_code < 400

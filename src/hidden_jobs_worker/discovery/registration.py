from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.models import CompanyCandidate


class CompanyRegistrationClient:
    """Placeholder for future backend company registration."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def submit_candidate(self, candidate: CompanyCandidate) -> None:
        raise NotImplementedError("backend company registration endpoint is not wired yet")

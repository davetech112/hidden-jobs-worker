import logging

from hidden_jobs_worker.discovery.ats_detector import detect_ats
from hidden_jobs_worker.discovery.board_verifier import BoardVerifier
from hidden_jobs_worker.discovery.careers_finder import CareersPageFinder
from hidden_jobs_worker.discovery.seeds import SeedCompany, load_seed_companies
from hidden_jobs_worker.models import AtsType, CompanyCandidate

LOGGER = logging.getLogger(__name__)


class CompanyDiscoveryEngine:
    def __init__(
        self,
        careers_finder: CareersPageFinder | None = None,
        board_verifier: BoardVerifier | None = None,
    ) -> None:
        self._careers_finder = careers_finder or CareersPageFinder()
        self._board_verifier = board_verifier or BoardVerifier()

    def discover_from_seed_file(
        self,
        seed_file: str,
        limit: int | None = None,
    ) -> list[CompanyCandidate]:
        seeds = load_seed_companies(seed_file)
        if limit is not None:
            seeds = seeds[:limit]
        candidates = []
        for seed in seeds:
            try:
                candidates.append(self.discover_company(seed))
            except Exception:
                LOGGER.exception(
                    "company discovery failed",
                    extra={"company_name": seed.name, "website_url": str(seed.website_url)},
                )
                candidates.append(_failed_candidate(seed))
        return candidates

    def discover_company(self, seed: SeedCompany) -> CompanyCandidate:
        notes: list[str] = []
        website_url = str(seed.website_url)
        careers_page = self._careers_finder.find_page(website_url)
        careers_url = careers_page.url if careers_page else None
        if careers_url:
            notes.append(f"Careers page candidate found: {careers_url}")
        else:
            notes.append("No careers page candidate found")

        detection = detect_ats(
            careers_url or website_url,
            careers_page.html if careers_page else None,
        )
        notes.append(f"ATS detection: {detection.ats_type}")

        verified = self._board_verifier.verify(detection.ats_type, detection.ats_slug)
        if verified:
            notes.append("ATS board verified")
            confidence = 0.95
        elif detection.ats_type != AtsType.UNKNOWN:
            notes.append("ATS board could not be verified")
            confidence = 0.35
        else:
            notes.append("No supported ATS detected")
            confidence = 0.1

        return CompanyCandidate(
            name=seed.name,
            websiteUrl=website_url,
            careersUrl=careers_url,
            boardUrl=detection.matched_url,
            atsType=detection.ats_type,
            atsSlug=detection.ats_slug,
            source="static_seed",
            confidenceScore=confidence,
            discoveryNotes=notes,
        )


def _failed_candidate(seed: SeedCompany) -> CompanyCandidate:
    return CompanyCandidate(
        name=seed.name,
        websiteUrl=str(seed.website_url),
        careersUrl=None,
        boardUrl=None,
        atsType=AtsType.UNKNOWN,
        atsSlug=None,
        source="static_seed",
        confidenceScore=0.1,
        discoveryNotes=["Company discovery failed; skipped safely"],
    )

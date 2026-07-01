import json

import httpx

from hidden_jobs_worker import cli
from hidden_jobs_worker.config import Settings
from hidden_jobs_worker.discovery.ats_detector import detect_ats
from hidden_jobs_worker.discovery.board_verifier import BoardVerifier
from hidden_jobs_worker.discovery.careers_finder import (
    CareersPage,
    CareersPageFinder,
    find_careers_link,
)
from hidden_jobs_worker.discovery.engine import CompanyDiscoveryEngine
from hidden_jobs_worker.discovery.registration import DiscoveryRegistrationClient
from hidden_jobs_worker.discovery.seeds import SeedCompany
from hidden_jobs_worker.models import AtsType, CompanyCandidate


def _settings() -> Settings:
    return Settings(
        SPRING_API_BASE_URL="https://api.example.com",
        WORKER_INGEST_TOKEN="test-token",
    )


def _candidate(
    *,
    name: str = "Example",
    ats_type: str = "LEVER",
    ats_slug: str | None = "example",
    confidence_score: float = 0.95,
) -> CompanyCandidate:
    return CompanyCandidate(
        name=name,
        websiteUrl="https://example.com",
        careersUrl="https://jobs.lever.co/example",
        atsType=ats_type,
        atsSlug=ats_slug,
        source="static_seed",
        confidenceScore=confidence_score,
        discoveryNotes=["ATS board verified"],
    )


def test_detects_greenhouse_url() -> None:
    detection = detect_ats("https://boards.greenhouse.io/example/jobs/123")

    assert detection.ats_type == AtsType.GREENHOUSE
    assert detection.ats_slug == "example"


def test_detects_job_boards_greenhouse_url() -> None:
    detection = detect_ats("https://job-boards.greenhouse.io/example/jobs/123")

    assert detection.ats_type == AtsType.GREENHOUSE
    assert detection.ats_slug == "example"


def test_detects_lever_url() -> None:
    detection = detect_ats("https://jobs.lever.co/example/abc")

    assert detection.ats_type == AtsType.LEVER
    assert detection.ats_slug == "example"


def test_detects_ashby_url() -> None:
    detection = detect_ats("https://jobs.ashbyhq.com/example")

    assert detection.ats_type == AtsType.ASHBY
    assert detection.ats_slug == "example"


def test_detects_ats_from_html_link() -> None:
    html = '<a href="https://jobs.lever.co/example">Open roles</a>'

    detection = detect_ats(html=html)

    assert detection.ats_type == AtsType.LEVER
    assert detection.ats_slug == "example"


def test_detects_ats_from_script_and_link_urls_in_html() -> None:
    html = """
    <html>
      <head>
        <link rel="preconnect" href="https://jobs.ashbyhq.com">
        <script src="https://jobs.ashbyhq.com/example/embed.js"></script>
      </head>
    </html>
    """

    detection = detect_ats(html=html)

    assert detection.ats_type == AtsType.ASHBY
    assert detection.ats_slug == "example"


def test_detects_ats_from_raw_embedded_url_in_html() -> None:
    html = '<script>window.jobsUrl = "https://apply.workable.com/example/";</script>'

    detection = detect_ats(html=html)

    assert detection.ats_type == AtsType.WORKABLE
    assert detection.ats_slug == "example"


def test_careers_finder_from_homepage_html() -> None:
    html = '<html><body><a href="/company/careers">Work with us</a></body></html>'

    assert find_careers_link("https://example.com", html) == "https://example.com/company/careers"


def test_careers_finder_fetches_homepage_when_common_paths_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                html='<a href="https://jobs.lever.co/example">Open roles</a>',
            )
        return httpx.Response(404)

    finder = CareersPageFinder(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert finder.find("https://example.com") == "https://jobs.lever.co/example"


def test_board_verification_success_and_failure_with_mocked_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "valid" in str(request.url):
            return httpx.Response(200, json={"jobs": []})
        return httpx.Response(404)

    verifier = BoardVerifier(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert verifier.verify(AtsType.GREENHOUSE, "valid")
    assert not verifier.verify(AtsType.GREENHOUSE, "missing")


def test_ashby_board_verification_success_and_failure_with_mocked_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/posting-api/job-board/valid":
            return httpx.Response(200, json={"jobs": []})
        return httpx.Response(404)

    verifier = BoardVerifier(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert verifier.verify(AtsType.ASHBY, "valid")
    assert not verifier.verify(AtsType.ASHBY, "missing")


def test_ashby_board_verification_falls_back_to_public_page() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://jobs.ashbyhq.com/valid":
            return httpx.Response(200, html="<html><title>Jobs</title></html>")
        return httpx.Response(404)

    verifier = BoardVerifier(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert verifier.verify(AtsType.ASHBY, "valid")


def test_workable_board_verification_success_and_failure_with_mocked_responses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) == "https://apply.workable.com/valid":
            return httpx.Response(200, html="<html><title>Jobs</title></html>")
        return httpx.Response(404)

    verifier = BoardVerifier(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert verifier.verify(AtsType.WORKABLE, "valid")
    assert not verifier.verify(AtsType.WORKABLE, "missing")


def test_discovery_registration_client_parses_wrapped_response_and_posts_token() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            201,
            json={
                "success": True,
                "data": {
                    "status": "created",
                    "companyId": "company-1",
                    "message": "created",
                },
                "message": "Discovery registered",
                "timestamp": "2026-07-01T00:00:00Z",
            },
        )

    client = DiscoveryRegistrationClient(
        _settings(),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.submit_career_board(_candidate())

    assert result.status == "created"
    assert result.submitted
    assert result.company_id == "company-1"
    assert str(seen_requests[0].url) == (
        "https://api.example.com/api/internal/discoveries/career-boards"
    )
    assert seen_requests[0].headers["X-Worker-Token"] == "test-token"
    request_json = json.loads(seen_requests[0].content)
    assert request_json["atsType"] == "LEVER"
    assert request_json["confidenceScore"] == 0.95


def test_discovery_registration_client_handles_created_updated_and_ignored() -> None:
    responses = iter(
        (
            {"status": "created"},
            {"status": "updated"},
            {"status": "ignored", "message": "duplicate"},
        )
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=next(responses))

    client = DiscoveryRegistrationClient(
        _settings(),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )

    created = client.submit_career_board(_candidate(name="Created"))
    updated = client.submit_career_board(_candidate(name="Updated"))
    ignored = client.submit_career_board(_candidate(name="Ignored"))

    assert created.submitted
    assert updated.submitted
    assert ignored.ignored


def test_discovery_engine_detects_ats_from_careers_page_html() -> None:
    class FakeCareersFinder:
        def find_page(self, website_url: str) -> CareersPage:
            return CareersPage(
                url="https://example.com/careers",
                html='<a href="https://jobs.smartrecruiters.com/example">Open roles</a>',
            )

    class FakeBoardVerifier:
        def verify(self, ats_type: AtsType, ats_slug: str | None) -> bool:
            return ats_type == AtsType.SMARTRECRUITERS and ats_slug == "example"

    engine = CompanyDiscoveryEngine(
        careers_finder=FakeCareersFinder(),
        board_verifier=FakeBoardVerifier(),
    )

    candidate = engine.discover_company(
        SeedCompany(name="Example", websiteUrl="https://example.com")
    )

    assert candidate.ats_type == AtsType.SMARTRECRUITERS
    assert candidate.ats_slug == "example"
    assert candidate.confidence_score == 0.95


def test_discovery_engine_detects_ats_from_final_careers_url() -> None:
    class FakeCareersFinder:
        def find_page(self, website_url: str) -> CareersPage:
            return CareersPage(url="https://jobs.lever.co/example", html="")

    class FakeBoardVerifier:
        def verify(self, ats_type: AtsType, ats_slug: str | None) -> bool:
            return ats_type == AtsType.LEVER and ats_slug == "example"

    engine = CompanyDiscoveryEngine(
        careers_finder=FakeCareersFinder(),
        board_verifier=FakeBoardVerifier(),
    )

    candidate = engine.discover_company(
        SeedCompany(name="Example", websiteUrl="https://example.com")
    )

    assert candidate.ats_type == AtsType.LEVER
    assert candidate.ats_slug == "example"
    assert candidate.confidence_score == 0.95


def test_discovery_engine_marks_verified_ashby_and_workable_high_confidence() -> None:
    pages = {
        "https://ashby.example/": CareersPage(
            url="https://jobs.ashbyhq.com/ashby-example",
            html="",
        ),
        "https://workable.example/": CareersPage(
            url="https://apply.workable.com/workable-example",
            html="",
        ),
    }

    class FakeCareersFinder:
        def find_page(self, website_url: str) -> CareersPage:
            return pages[website_url]

    class FakeBoardVerifier:
        def verify(self, ats_type: AtsType, ats_slug: str | None) -> bool:
            return (ats_type, ats_slug) in {
                (AtsType.ASHBY, "ashby-example"),
                (AtsType.WORKABLE, "workable-example"),
            }

    engine = CompanyDiscoveryEngine(
        careers_finder=FakeCareersFinder(),
        board_verifier=FakeBoardVerifier(),
    )

    candidates = [
        engine.discover_company(
            SeedCompany(name="Ashby Example", websiteUrl="https://ashby.example")
        ),
        engine.discover_company(
            SeedCompany(name="Workable Example", websiteUrl="https://workable.example")
        ),
    ]

    assert [candidate.ats_type for candidate in candidates] == [
        AtsType.ASHBY,
        AtsType.WORKABLE,
    ]
    assert all(candidate.confidence_score >= 0.95 for candidate in candidates)


def test_discovery_cli_dry_run(monkeypatch, tmp_path, capsys) -> None:
    seed_file = tmp_path / "companies.yml"
    seed_file.write_text("- name: Example\n  websiteUrl: https://example.com\n", encoding="utf-8")

    class FakeDiscoveryEngine:
        def discover_from_seed_file(self, seed_file: str, limit: int | None = None):
            return [_candidate()]

    class FailingRegistrationClient:
        def __init__(self, settings: Settings) -> None:
            raise AssertionError("dry-run must not create registration client")

    monkeypatch.setattr(cli, "CompanyDiscoveryEngine", FakeDiscoveryEngine)
    monkeypatch.setattr(cli, "DiscoveryRegistrationClient", FailingRegistrationClient)

    assert cli.main(["discover-companies", "--seed-file", str(seed_file), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "company discovery completed" in output
    assert "Example: atsType=LEVER atsSlug=example confidence=0.95" in output


def test_discovery_cli_submits_verified_candidate(monkeypatch, tmp_path) -> None:
    seed_file = tmp_path / "companies.yml"
    seed_file.write_text("- name: Example\n  websiteUrl: https://example.com\n", encoding="utf-8")
    submitted: list[CompanyCandidate] = []

    class FakeDiscoveryEngine:
        def discover_from_seed_file(self, seed_file: str, limit: int | None = None):
            return [_candidate()]

    class FakeRegistrationClient:
        def __init__(self, settings: Settings) -> None:
            pass

        def submit_career_board(self, candidate: CompanyCandidate):
            submitted.append(candidate)
            return type("Result", (), {"submitted": True, "ignored": False})()

    monkeypatch.setattr(cli, "CompanyDiscoveryEngine", FakeDiscoveryEngine)
    monkeypatch.setattr(cli, "DiscoveryRegistrationClient", FakeRegistrationClient)
    monkeypatch.setattr(cli, "get_settings", _settings)

    assert cli.main(["discover-companies", "--seed-file", str(seed_file)]) == 0
    assert [candidate.name for candidate in submitted] == ["Example"]


def test_discovery_submission_skips_low_confidence_candidate() -> None:
    class FakeRegistrationClient:
        def submit_career_board(self, candidate: CompanyCandidate):
            raise AssertionError("low-confidence candidate must not submit")

    summary = cli._submit_discovery_candidates(
        [_candidate(confidence_score=0.35)],
        min_confidence=0.90,
        registration_client=FakeRegistrationClient(),
    )

    assert summary == {"submitted": 0, "ignored": 0, "skipped": 1, "failed": 0}


def test_discovery_submission_skips_unknown_ats_candidate() -> None:
    class FakeRegistrationClient:
        def submit_career_board(self, candidate: CompanyCandidate):
            raise AssertionError("unknown ATS candidate must not submit")

    summary = cli._submit_discovery_candidates(
        [_candidate(ats_type="UNKNOWN", ats_slug=None)],
        min_confidence=0.90,
        registration_client=FakeRegistrationClient(),
    )

    assert summary == {"submitted": 0, "ignored": 0, "skipped": 1, "failed": 0}


def test_discovery_submission_failed_candidate_does_not_stop_others() -> None:
    class FakeRegistrationClient:
        def submit_career_board(self, candidate: CompanyCandidate):
            if candidate.name == "Fails":
                raise RuntimeError("backend unavailable")
            return type("Result", (), {"submitted": True, "ignored": False})()

    summary = cli._submit_discovery_candidates(
        [
            _candidate(name="Fails"),
            _candidate(name="Succeeds"),
        ],
        min_confidence=0.90,
        registration_client=FakeRegistrationClient(),
    )

    assert summary == {"submitted": 1, "ignored": 0, "skipped": 0, "failed": 1}


def test_discovery_cli_dry_run_shows_verified_ashby_and_workable(
    monkeypatch, tmp_path, capsys
) -> None:
    seed_file = tmp_path / "companies.yml"
    seed_file.write_text(
        "- name: Ashby Example\n"
        "  websiteUrl: https://ashby.example\n"
        "- name: Workable Example\n"
        "  websiteUrl: https://workable.example\n",
        encoding="utf-8",
    )

    class FakeDiscoveryEngine:
        def discover_from_seed_file(self, seed_file: str, limit: int | None = None):
            return [
                CompanyCandidate(
                    name="Ashby Example",
                    websiteUrl="https://ashby.example",
                    careersUrl="https://jobs.ashbyhq.com/ashby-example",
                    atsType="ASHBY",
                    atsSlug="ashby-example",
                    source="static_seed",
                    confidenceScore=0.95,
                    discoveryNotes=["ATS board verified"],
                ),
                CompanyCandidate(
                    name="Workable Example",
                    websiteUrl="https://workable.example",
                    careersUrl="https://apply.workable.com/workable-example",
                    atsType="WORKABLE",
                    atsSlug="workable-example",
                    source="static_seed",
                    confidenceScore=0.95,
                    discoveryNotes=["ATS board verified"],
                ),
            ]

    monkeypatch.setattr(cli, "CompanyDiscoveryEngine", FakeDiscoveryEngine)

    assert cli.main(["discover-companies", "--seed-file", str(seed_file), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "company discovery completed: candidates=2 verified=2 dry_run=True" in output
    assert "Ashby Example: atsType=ASHBY atsSlug=ashby-example confidence=0.95" in output
    assert (
        "Workable Example: atsType=WORKABLE atsSlug=workable-example confidence=0.95"
        in output
    )

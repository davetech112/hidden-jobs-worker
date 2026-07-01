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
from hidden_jobs_worker.discovery.registration import (
    DiscoveryRegistrationAuthError,
    DiscoveryRegistrationClient,
    build_career_board_discovery_payload,
)
from hidden_jobs_worker.discovery.seeds import SeedCompany, load_seed_companies
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
    board_url: str | None = None,
    confidence_score: float = 0.95,
) -> CompanyCandidate:
    return CompanyCandidate(
        name=name,
        websiteUrl="https://example.com",
        careersUrl="https://jobs.lever.co/example",
        boardUrl=board_url,
        atsType=ats_type,
        atsSlug=ats_slug,
        source="static_seed",
        confidenceScore=confidence_score,
        discoveryNotes=["ATS board verified"],
    )


BACKEND_DISCOVERY_PAYLOAD_FIELDS = {
    "companyName",
    "websiteUrl",
    "careersUrl",
    "boardUrl",
    "atsType",
    "atsSlug",
    "confidenceScore",
    "verificationMethod",
    "verificationUrl",
    "detectedFrom",
    "discoveryNotes",
}


def test_default_discovery_seed_file_parses() -> None:
    companies = load_seed_companies("discovery/seeds/companies.yml")
    names = {company.name for company in companies}

    assert len(companies) >= 30
    assert {
        "Bosch",
        "Mentimeter",
        "Recruitee",
        "monday.com",
        "Personio",
    }.issubset(names)
    assert all(str(company.website_url).startswith("https://") for company in companies)


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


def test_detects_adapter_pack_1_urls() -> None:
    cases = [
        (
            "https://jobs.smartrecruiters.com/example/123-backend-engineer",
            AtsType.SMARTRECRUITERS,
            "example",
        ),
        ("https://example.teamtailor.com/jobs", AtsType.TEAMTAILOR, "example"),
        ("https://example.recruitee.com/o/backend-engineer", AtsType.RECRUITEE, "example"),
        (
            "https://www.comeet.com/careers-api/2.0/company/example/positions",
            AtsType.COMEET,
            "example",
        ),
        ("https://example.jobs.personio.com/xml", AtsType.PERSONIO, "example"),
    ]

    for url, ats_type, slug in cases:
        detection = detect_ats(url)

        assert detection.ats_type == ats_type
        assert detection.ats_slug == slug


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


def test_adapter_pack_1_board_verification_success_and_failure() -> None:
    valid_urls = {
        "https://api.smartrecruiters.com/v1/companies/valid/postings",
        "https://valid.teamtailor.com/jobs",
        "https://valid.recruitee.com/api/offers/",
        "https://www.comeet.com/careers-api/2.0/company/valid/positions",
        "https://valid.jobs.personio.com/xml",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) in valid_urls:
            return httpx.Response(200, json={"jobs": []})
        return httpx.Response(404)

    verifier = BoardVerifier(client=httpx.Client(transport=httpx.MockTransport(handler)))

    for ats_type in (
        AtsType.SMARTRECRUITERS,
        AtsType.TEAMTAILOR,
        AtsType.RECRUITEE,
        AtsType.COMEET,
        AtsType.PERSONIO,
    ):
        assert verifier.verify(ats_type, "valid")
        assert not verifier.verify(ats_type, "missing")


def test_discovery_registration_client_parses_wrapped_response_and_posts_token() -> None:
    seen_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_requests.append(request)
        return httpx.Response(
            201,
            json={
                "success": True,
                "data": {
                    "action": "CREATED",
                    "status": "VERIFIED",
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

    assert result.action == "created"
    assert result.status == "VERIFIED"
    assert result.submitted
    assert result.company_id == "company-1"
    assert str(seen_requests[0].url) == (
        "https://api.example.com/api/internal/discoveries/career-boards"
    )
    assert seen_requests[0].headers["X-Worker-Token"] == "test-token"
    request_json = json.loads(seen_requests[0].content)
    assert request_json["atsType"] == "LEVER"
    assert request_json["confidenceScore"] == 0.95


def test_serialized_discovery_payload_matches_backend_contract_exactly() -> None:
    payload = build_career_board_discovery_payload(
        CompanyCandidate(
            name="Example Labs",
            websiteUrl="https://example.com",
            careersUrl="https://example.com/careers",
            boardUrl="https://boards.greenhouse.io/example",
            atsType="GREENHOUSE",
            atsSlug="example",
            source="homepage-link",
            confidenceScore=0.95,
            discoveryNotes=["Found from careers page."],
        )
    )

    assert set(payload) == BACKEND_DISCOVERY_PAYLOAD_FIELDS
    assert payload == {
        "companyName": "Example Labs",
        "websiteUrl": "https://example.com/",
        "careersUrl": "https://example.com/careers",
        "boardUrl": "https://boards.greenhouse.io/example",
        "atsType": "GREENHOUSE",
        "atsSlug": "example",
        "confidenceScore": 0.95,
        "verificationMethod": "greenhouse-board",
        "verificationUrl": "https://boards.greenhouse.io/example",
        "detectedFrom": "homepage-link",
        "discoveryNotes": "Found from careers page.",
    }


def test_vercel_greenhouse_candidate_payload_is_valid() -> None:
    payload = build_career_board_discovery_payload(
        CompanyCandidate(
            name="Vercel",
            websiteUrl="https://vercel.com",
            careersUrl="https://vercel.com/careers",
            boardUrl="https://boards.greenhouse.io/vercel",
            atsType="greenhouse",
            atsSlug="vercel",
            source="static_seed",
            confidenceScore=0.95,
            discoveryNotes=["ATS board verified"],
        )
    )

    assert set(payload) == BACKEND_DISCOVERY_PAYLOAD_FIELDS
    assert payload["companyName"] == "Vercel"
    assert payload["boardUrl"] == "https://boards.greenhouse.io/vercel"
    assert payload["atsType"] == "GREENHOUSE"
    assert payload["atsSlug"] == "vercel"
    assert payload["confidenceScore"] == 0.95
    assert payload["verificationMethod"] == "greenhouse-board"
    assert payload["verificationUrl"] == "https://boards.greenhouse.io/vercel"


def test_ashby_candidate_payload_is_valid() -> None:
    payload = build_career_board_discovery_payload(
        CompanyCandidate(
            name="Ashby Example",
            websiteUrl="https://ashby.example",
            careersUrl="https://jobs.ashbyhq.com/ashby-example",
            atsType="ASHBY",
            atsSlug="ashby-example",
            source="static_seed",
            confidenceScore=0.95,
            discoveryNotes=["ATS board verified"],
        )
    )

    assert set(payload) == BACKEND_DISCOVERY_PAYLOAD_FIELDS
    assert payload["companyName"] == "Ashby Example"
    assert payload["boardUrl"] == "https://jobs.ashbyhq.com/ashby-example"
    assert payload["atsType"] == "ASHBY"
    assert payload["verificationMethod"] == "ashby-board"
    assert payload["verificationUrl"] == "https://jobs.ashbyhq.com/ashby-example"


def test_workable_candidate_payload_is_valid() -> None:
    payload = build_career_board_discovery_payload(
        CompanyCandidate(
            name="Workable Example",
            websiteUrl="https://workable.example",
            careersUrl="https://apply.workable.com/workable-example",
            atsType="WORKABLE",
            atsSlug="workable-example",
            source="static_seed",
            confidenceScore=0.95,
            discoveryNotes=["ATS board verified"],
        )
    )

    assert set(payload) == BACKEND_DISCOVERY_PAYLOAD_FIELDS
    assert payload["companyName"] == "Workable Example"
    assert payload["boardUrl"] == "https://apply.workable.com/workable-example"
    assert payload["atsType"] == "WORKABLE"
    assert payload["verificationMethod"] == "workable-board"
    assert payload["verificationUrl"] == "https://apply.workable.com/workable-example"


def test_discovery_registration_client_handles_created_updated_and_ignored() -> None:
    responses = iter(
        (
            {"action": "created", "status": "VERIFIED"},
            {"action": "updated", "status": "ACTIVE"},
            {"action": "ignored", "status": "DISCOVERED", "message": "duplicate"},
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
    assert created.created
    assert created.status == "VERIFIED"
    assert updated.submitted
    assert updated.updated
    assert updated.status == "ACTIVE"
    assert ignored.ignored
    assert ignored.status == "DISCOVERED"


def test_discovery_registration_client_supports_legacy_status_action_response() -> None:
    client = DiscoveryRegistrationClient(
        _settings(),
        httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"status": "created"})
            )
        ),
    )

    result = client.submit_career_board(_candidate())

    assert result.action == "created"
    assert result.status is None
    assert result.created


def test_discovery_registration_client_classifies_auth_failure() -> None:
    client = DiscoveryRegistrationClient(
        _settings(),
        httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(401))),
    )

    try:
        client.submit_career_board(_candidate())
    except DiscoveryRegistrationAuthError:
        pass
    else:
        raise AssertionError("expected auth failure")


def test_discovery_registration_client_uses_configured_timeout() -> None:
    settings = Settings(
        SPRING_API_BASE_URL="https://api.example.com",
        WORKER_INGEST_TOKEN="test-token",
        WORKER_HTTP_TIMEOUT_SECONDS=12,
    )

    client = DiscoveryRegistrationClient(settings)

    assert client._client.timeout.connect == 12


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
    assert str(candidate.board_url) == "https://jobs.smartrecruiters.com/example"
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
            return type(
                "Result",
                (),
                {"created": True, "updated": False, "ignored": False},
            )()

    monkeypatch.setattr(cli, "CompanyDiscoveryEngine", FakeDiscoveryEngine)
    monkeypatch.setattr(cli, "DiscoveryRegistrationClient", FakeRegistrationClient)
    monkeypatch.setattr(cli, "get_settings", _settings)

    assert cli.main(["discover-companies", "--seed-file", str(seed_file)]) == 0
    assert [candidate.name for candidate in submitted] == ["Example"]


def test_discovery_cli_passes_limit_and_min_confidence(monkeypatch, tmp_path) -> None:
    seed_file = tmp_path / "companies.yml"
    seed_file.write_text("- name: Example\n  websiteUrl: https://example.com\n", encoding="utf-8")
    seen_limits: list[int | None] = []
    submitted: list[CompanyCandidate] = []

    class FakeDiscoveryEngine:
        def discover_from_seed_file(self, seed_file: str, limit: int | None = None):
            seen_limits.append(limit)
            return [_candidate(confidence_score=0.50)]

    class FakeRegistrationClient:
        def __init__(self, settings: Settings) -> None:
            pass

        def submit_career_board(self, candidate: CompanyCandidate):
            submitted.append(candidate)
            return type(
                "Result",
                (),
                {"created": True, "updated": False, "ignored": False},
            )()

    monkeypatch.setattr(cli, "CompanyDiscoveryEngine", FakeDiscoveryEngine)
    monkeypatch.setattr(cli, "DiscoveryRegistrationClient", FakeRegistrationClient)
    monkeypatch.setattr(cli, "get_settings", _settings)

    assert (
        cli.main(
            [
                "discover-companies",
                "--seed-file",
                str(seed_file),
                "--limit",
                "1",
                "--min-confidence",
                "0.50",
            ]
        )
        == 0
    )
    assert seen_limits == [1]
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

    assert summary == {"submitted": 0, "updated": 0, "ignored": 0, "skipped": 1, "failed": 0}


def test_discovery_submission_skips_unknown_ats_candidate() -> None:
    class FakeRegistrationClient:
        def submit_career_board(self, candidate: CompanyCandidate):
            raise AssertionError("unknown ATS candidate must not submit")

    summary = cli._submit_discovery_candidates(
        [_candidate(ats_type="UNKNOWN", ats_slug=None)],
        min_confidence=0.90,
        registration_client=FakeRegistrationClient(),
    )

    assert summary == {"submitted": 0, "updated": 0, "ignored": 0, "skipped": 1, "failed": 0}


def test_discovery_submission_failed_candidate_does_not_stop_others() -> None:
    class FakeRegistrationClient:
        def submit_career_board(self, candidate: CompanyCandidate):
            if candidate.name == "Fails":
                raise RuntimeError("backend unavailable")
            return type(
                "Result",
                (),
                {"created": True, "updated": False, "ignored": False},
            )()

    summary = cli._submit_discovery_candidates(
        [
            _candidate(name="Fails"),
            _candidate(name="Succeeds"),
        ],
        min_confidence=0.90,
        registration_client=FakeRegistrationClient(),
    )

    assert summary == {"submitted": 1, "updated": 0, "ignored": 0, "skipped": 0, "failed": 1}


def test_discovery_submission_counts_updated_ignored_and_skips_duplicates() -> None:
    class FakeRegistrationClient:
        def submit_career_board(self, candidate: CompanyCandidate):
            if candidate.name == "Updated":
                return type(
                    "Result",
                    (),
                    {"created": False, "updated": True, "ignored": False},
                )()
            return type(
                "Result",
                (),
                {"created": False, "updated": False, "ignored": True},
            )()

    summary = cli._submit_discovery_candidates(
        [
            _candidate(name="Updated", ats_slug="updated"),
            _candidate(name="Ignored", ats_slug="ignored"),
            _candidate(name="Duplicate", ats_slug="updated"),
        ],
        min_confidence=0.90,
        registration_client=FakeRegistrationClient(),
    )

    assert summary == {"submitted": 0, "updated": 1, "ignored": 1, "skipped": 1, "failed": 0}


def test_discovery_submission_counts_created() -> None:
    class FakeRegistrationClient:
        def submit_career_board(self, candidate: CompanyCandidate):
            return type(
                "Result",
                (),
                {"created": True, "updated": False, "ignored": False},
            )()

    summary = cli._submit_discovery_candidates(
        [_candidate(name="Created")],
        min_confidence=0.90,
        registration_client=FakeRegistrationClient(),
    )

    assert summary == {"submitted": 1, "updated": 0, "ignored": 0, "skipped": 0, "failed": 0}


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

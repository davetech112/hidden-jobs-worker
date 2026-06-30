import httpx

from hidden_jobs_worker import cli
from hidden_jobs_worker.discovery.ats_detector import detect_ats
from hidden_jobs_worker.discovery.board_verifier import BoardVerifier
from hidden_jobs_worker.discovery.careers_finder import CareersPageFinder, find_careers_link
from hidden_jobs_worker.models import AtsType, CompanyCandidate


def test_detects_greenhouse_url() -> None:
    detection = detect_ats("https://boards.greenhouse.io/example/jobs/123")

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


def test_discovery_cli_dry_run(monkeypatch, tmp_path, capsys) -> None:
    seed_file = tmp_path / "companies.yml"
    seed_file.write_text("- name: Example\n  websiteUrl: https://example.com\n", encoding="utf-8")

    class FakeDiscoveryEngine:
        def discover_from_seed_file(self, seed_file: str, limit: int | None = None):
            return [
                CompanyCandidate(
                    name="Example",
                    websiteUrl="https://example.com",
                    careersUrl="https://jobs.lever.co/example",
                    atsType="LEVER",
                    atsSlug="example",
                    source="static_seed",
                    confidenceScore=0.95,
                    discoveryNotes=["ATS board verified"],
                )
            ]

    monkeypatch.setattr(cli, "CompanyDiscoveryEngine", FakeDiscoveryEngine)

    assert cli.main(["discover-companies", "--seed-file", str(seed_file), "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "company discovery completed" in output
    assert "Example: atsType=LEVER atsSlug=example confidence=0.95" in output

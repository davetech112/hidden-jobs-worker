import httpx

from hidden_jobs_worker.adapters.greenhouse import GreenhouseAdapter
from hidden_jobs_worker.adapters.lever import LeverAdapter
from hidden_jobs_worker.adapters.manager import AtsAdapterManager
from hidden_jobs_worker.models import AtsType, CompanyRecord, EmploymentType, RemoteType


def _company(ats_type: str, ats_slug: str = "example") -> CompanyRecord:
    return CompanyRecord(
        id=f"{ats_type.lower()}-company",
        name="Example Labs",
        websiteUrl="https://example.com",
        careersUrl="https://example.com/careers",
        atsType=ats_type,
        atsSlug=ats_slug,
        enabled=True,
    )


def test_greenhouse_adapter_parses_mocked_response() -> None:
    company = _company("GREENHOUSE")
    adapter = GreenhouseAdapter()
    jobs = adapter.parse_jobs(
        company,
        {
            "jobs": [
                {
                    "id": 123,
                    "title": "Backend Engineer",
                    "absolute_url": "https://boards.greenhouse.io/example/jobs/123",
                    "location": {"name": "Remote"},
                    "content": "<p>Build services.</p>",
                    "updated_at": "2026-06-30T00:00:00Z",
                }
            ]
        },
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "GREENHOUSE"
    assert jobs[0].source_job_id == "123"
    assert jobs[0].company_name == "Example Labs"
    assert jobs[0].remote_type == RemoteType.REMOTE
    assert jobs[0].description_text == "Build services."


def test_greenhouse_adapter_fetches_with_mocked_http_response() -> None:
    company = _company("GREENHOUSE")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
        )
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": 123,
                        "title": "Backend Engineer",
                        "absolute_url": "https://boards.greenhouse.io/example/jobs/123",
                    }
                ]
            },
        )

    adapter = GreenhouseAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert adapter.fetch_jobs(company)[0].title == "Backend Engineer"


def test_lever_adapter_parses_mocked_response() -> None:
    company = _company("LEVER")
    adapter = LeverAdapter()
    jobs = adapter.parse_jobs(
        company,
        [
            {
                "id": "abc",
                "text": "Data Engineer",
                "hostedUrl": "https://jobs.lever.co/example/abc",
                "categories": {
                    "location": "Remote",
                    "commitment": "Full-time",
                    "team": "Data",
                },
                "descriptionPlain": "Build pipelines.",
                "createdAt": 1782777600000,
            }
        ],
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "LEVER"
    assert jobs[0].source_job_id == "abc"
    assert jobs[0].remote_type == RemoteType.REMOTE
    assert jobs[0].employment_type == EmploymentType.FULL_TIME
    assert jobs[0].description_text == "Build pipelines."
    assert jobs[0].tags == ["data", "full-time"]


def test_lever_adapter_fetches_with_mocked_http_response() -> None:
    company = _company("LEVER")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.lever.co/v0/postings/example?mode=json"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "abc",
                    "text": "Data Engineer",
                    "hostedUrl": "https://jobs.lever.co/example/abc",
                }
            ],
        )

    adapter = LeverAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert adapter.fetch_jobs(company)[0].title == "Data Engineer"


def test_ats_adapter_manager_routes_supported_ats_types() -> None:
    manager = AtsAdapterManager(adapters=[GreenhouseAdapter(), LeverAdapter()])

    assert manager.get_adapter(_company("GREENHOUSE")).ats_type == AtsType.GREENHOUSE
    assert manager.get_adapter(_company("LEVER")).ats_type == AtsType.LEVER
    assert manager.get_adapter(_company("ASHBY")) is None

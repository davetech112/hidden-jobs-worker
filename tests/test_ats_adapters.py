import httpx

from hidden_jobs_worker.adapters.greenhouse import GreenhouseAdapter
from hidden_jobs_worker.adapters.lever import LeverAdapter
from hidden_jobs_worker.adapters.manager import AtsAdapterManager
from hidden_jobs_worker.models import AtsType, CareerBoard, EmploymentType, RemoteType


def _career_board(ats_type: str, ats_slug: str = "example") -> CareerBoard:
    return CareerBoard(
        boardId=f"{ats_type.lower()}-board",
        boardUrl=f"https://boards.example.com/{ats_slug}",
        companyId=f"{ats_type.lower()}-company",
        companyName="Example Labs",
        websiteUrl="https://example.com",
        careersUrl="https://example.com/careers",
        atsType=ats_type,
        atsSlug=ats_slug,
        confidenceScore=0.95,
        failureCount=0,
    )


def test_greenhouse_adapter_parses_mocked_response() -> None:
    career_board = _career_board("GREENHOUSE")
    adapter = GreenhouseAdapter()
    jobs = adapter.parse_jobs(
        career_board,
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
    career_board = _career_board("GREENHOUSE")

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

    assert adapter.fetch_jobs(career_board)[0].title == "Backend Engineer"


def test_lever_adapter_parses_mocked_response() -> None:
    career_board = _career_board("LEVER")
    adapter = LeverAdapter()
    jobs = adapter.parse_jobs(
        career_board,
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
    career_board = _career_board("LEVER")

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

    assert adapter.fetch_jobs(career_board)[0].title == "Data Engineer"


def test_ats_adapter_manager_routes_supported_ats_types() -> None:
    manager = AtsAdapterManager(adapters=[GreenhouseAdapter(), LeverAdapter()])

    assert manager.get_adapter(_career_board("GREENHOUSE")).ats_type == AtsType.GREENHOUSE
    assert manager.get_adapter(_career_board("LEVER")).ats_type == AtsType.LEVER
    assert manager.get_adapter(_career_board("ASHBY")) is None

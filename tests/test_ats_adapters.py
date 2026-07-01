import httpx

from hidden_jobs_worker.adapters.ashby import AshbyAdapter
from hidden_jobs_worker.adapters.greenhouse import GreenhouseAdapter
from hidden_jobs_worker.adapters.lever import LeverAdapter
from hidden_jobs_worker.adapters.manager import AtsAdapterManager
from hidden_jobs_worker.adapters.workable import WorkableAdapter
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
    assert jobs[0].source_type == "ATS"
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
    assert jobs[0].source_type == "ATS"
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


def test_ashby_adapter_parses_mocked_response() -> None:
    career_board = _career_board("ASHBY", "ashby-example")
    adapter = AshbyAdapter()
    jobs = adapter.parse_jobs(
        career_board,
        {
            "jobs": [
                {
                    "id": "ashby-1",
                    "title": "Platform Engineer",
                    "jobUrl": "https://jobs.ashbyhq.com/ashby-example/ashby-1",
                    "location": {"name": "Remote"},
                    "employmentType": "FullTime",
                    "department": {"name": "Engineering"},
                    "descriptionHtml": "<p>Build platform systems.</p>",
                    "publishedAt": "2026-07-01T00:00:00Z",
                }
            ]
        },
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "ASHBY"
    assert jobs[0].source_type == "ATS"
    assert jobs[0].source_job_id == "ashby-1"
    assert jobs[0].remote_type == RemoteType.REMOTE
    assert jobs[0].employment_type == EmploymentType.FULL_TIME
    assert jobs[0].description_text == "Build platform systems."
    assert jobs[0].description_html == "<p>Build platform systems.</p>"
    assert jobs[0].tags == ["engineering"]


def test_ashby_adapter_fetches_with_mocked_http_response() -> None:
    career_board = _career_board("ASHBY", "ashby-example")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://api.ashbyhq.com/posting-api/job-board/ashby-example"
        )
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "ashby-1",
                        "title": "Platform Engineer",
                        "jobUrl": "https://jobs.ashbyhq.com/ashby-example/ashby-1",
                    }
                ]
            },
        )

    adapter = AshbyAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert adapter.fetch_jobs(career_board)[0].title == "Platform Engineer"


def test_workable_adapter_parses_mocked_response() -> None:
    career_board = _career_board("WORKABLE", "workable-example")
    adapter = WorkableAdapter()
    jobs = adapter.parse_jobs(
        career_board,
        {
            "results": [
                {
                    "shortcode": "ABC123",
                    "title": "Support Engineer",
                    "url": "https://apply.workable.com/workable-example/j/ABC123/",
                    "location": {"city": "Remote", "country": "United States"},
                    "type": "Full-time",
                    "department": "Customer Success",
                    "description": "<p>Help customers succeed.</p>",
                    "remote": True,
                }
            ]
        },
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "WORKABLE"
    assert jobs[0].source_type == "ATS"
    assert jobs[0].source_job_id == "ABC123"
    assert jobs[0].remote_type == RemoteType.REMOTE
    assert jobs[0].employment_type == EmploymentType.FULL_TIME
    assert jobs[0].description_text == "Help customers succeed."
    assert jobs[0].description_html == "<p>Help customers succeed.</p>"
    assert jobs[0].tags == ["customer success"]


def test_workable_adapter_fetches_with_mocked_http_response() -> None:
    career_board = _career_board("WORKABLE", "workable-example")

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == (
            "https://apply.workable.com/api/v3/accounts/workable-example/jobs"
        )
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "shortcode": "ABC123",
                        "title": "Support Engineer",
                        "url": "https://apply.workable.com/workable-example/j/ABC123/",
                    }
                ]
            },
        )

    adapter = WorkableAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))

    assert adapter.fetch_jobs(career_board)[0].title == "Support Engineer"


def test_ats_adapter_manager_routes_supported_ats_types() -> None:
    manager = AtsAdapterManager(
        adapters=[GreenhouseAdapter(), LeverAdapter(), AshbyAdapter(), WorkableAdapter()]
    )

    assert manager.get_adapter(_career_board("GREENHOUSE")).ats_type == AtsType.GREENHOUSE
    assert manager.get_adapter(_career_board("LEVER")).ats_type == AtsType.LEVER
    assert manager.get_adapter(_career_board("ASHBY")).ats_type == AtsType.ASHBY
    assert manager.get_adapter(_career_board("WORKABLE")).ats_type == AtsType.WORKABLE
    assert manager.get_adapter(_career_board("CUSTOM")) is None


def test_default_ats_adapter_manager_routes_ashby_and_workable() -> None:
    manager = AtsAdapterManager()

    assert manager.get_adapter(_career_board("ASHBY")).ats_type == AtsType.ASHBY
    assert manager.get_adapter(_career_board("WORKABLE")).ats_type == AtsType.WORKABLE


def test_ats_job_record_payload_includes_source_name_and_source_type() -> None:
    career_board = _career_board("ASHBY", "ashby-example")
    job = AshbyAdapter().parse_jobs(
        career_board,
        {
            "jobs": [
                {
                    "id": "ashby-1",
                    "title": "Platform Engineer",
                    "jobUrl": "https://jobs.ashbyhq.com/ashby-example/ashby-1",
                }
            ]
        },
    )[0]

    payload = job.model_dump(mode="json", by_alias=True)

    assert payload["sourceName"] == "ASHBY"
    assert payload["sourceType"] == "ATS"

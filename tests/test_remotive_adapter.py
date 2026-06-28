import httpx

from hidden_jobs_worker.adapters.remotive import RemotiveAdapter
from hidden_jobs_worker.models import EmploymentType, RemoteType


def test_remotive_adapter_parses_jobs_payload() -> None:
    adapter = RemotiveAdapter()
    jobs = adapter.parse_jobs(
        {
            "jobs": [
                {
                    "id": 42,
                    "url": "https://remotive.com/remote-jobs/software-dev/backend-engineer-42",
                    "title": "Backend Engineer",
                    "company_name": "Example Inc",
                    "candidate_required_location": "Worldwide",
                    "job_type": "full_time",
                    "description": "<p>Build APIs.</p>",
                    "publication_date": "2026-06-27T00:00:00Z",
                    "tags": ["Python", "API"],
                    "category": "Software Development",
                    "salary": "$120k",
                }
            ]
        }
    )

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "42"
    assert jobs[0].company_name == "Example Inc"
    assert jobs[0].remote_type == RemoteType.REMOTE
    assert jobs[0].employment_type == EmploymentType.FULL_TIME
    assert jobs[0].description_text == "Build APIs."
    assert jobs[0].tags == ["api", "python"]


def test_remotive_adapter_fetches_with_mocked_http_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://remotive.test/jobs"
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "id": "abc",
                        "url": "https://remotive.test/jobs/abc",
                        "title": "Data Engineer",
                        "company_name": "Example Inc",
                    }
                ]
            },
        )

    adapter = RemotiveAdapter(
        api_url="https://remotive.test/jobs",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert adapter.fetch_jobs()[0].title == "Data Engineer"

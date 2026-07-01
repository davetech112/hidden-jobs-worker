import httpx
import pytest

from hidden_jobs_worker.adapters.ashby import AshbyAdapter
from hidden_jobs_worker.adapters.comeet import ComeetAdapter, ComeetAdapterError
from hidden_jobs_worker.adapters.greenhouse import GreenhouseAdapter
from hidden_jobs_worker.adapters.lever import LeverAdapter
from hidden_jobs_worker.adapters.manager import AtsAdapterManager
from hidden_jobs_worker.adapters.personio import PersonioAdapter, PersonioAdapterError
from hidden_jobs_worker.adapters.recruitee import RecruiteeAdapter, RecruiteeAdapterError
from hidden_jobs_worker.adapters.smartrecruiters import (
    SmartRecruitersAdapter,
    SmartRecruitersAdapterError,
)
from hidden_jobs_worker.adapters.teamtailor import TeamtailorAdapter, TeamtailorAdapterError
from hidden_jobs_worker.adapters.workable import WorkableAdapter, WorkableAdapterError
from hidden_jobs_worker.models import AtsType, CareerBoard, EmploymentType, RemoteType


def _career_board(ats_type: str, ats_slug: str | None = "example") -> CareerBoard:
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


def test_workable_adapter_api_strategy_success() -> None:
    career_board = _career_board("WORKABLE", "workable-example")
    requested_urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
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

    jobs = adapter.fetch_jobs(career_board)

    assert requested_urls == ["https://apply.workable.com/api/v3/accounts/workable-example/jobs"]
    assert jobs[0].title == "Support Engineer"
    assert jobs[0].source_name == "WORKABLE"
    assert jobs[0].source_type == "ATS"


def test_workable_adapter_api_404_then_public_page_embedded_json_success() -> None:
    career_board = _career_board("WORKABLE", "huggingface")
    requested_urls = []
    html = """
    <html>
      <body>
        <script id="__NEXT_DATA__" type="application/json">
        {
          "props": {
            "pageProps": {
              "jobs": [
                {
                  "shortcode": "ABC123",
                  "title": "ML Engineer",
                  "url": "https://apply.workable.com/huggingface/j/ABC123/",
                  "location": {"city": "Remote"},
                  "type": "Full-time",
                  "description": "<p>Build open ML tools.</p>",
                  "remote": true
                }
              ]
            }
          }
        }
        </script>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url).endswith("/api/v3/accounts/huggingface/jobs"):
            return httpx.Response(404)
        return httpx.Response(200, text=html)

    adapter = WorkableAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))
    jobs = adapter.fetch_jobs(career_board)

    assert requested_urls == [
        "https://apply.workable.com/api/v3/accounts/huggingface/jobs",
        "https://apply.workable.com/huggingface/",
    ]
    assert jobs[0].title == "ML Engineer"
    assert jobs[0].source_url.unicode_string() == (
        "https://apply.workable.com/huggingface/j/ABC123/"
    )
    assert jobs[0].description_text == "Build open ML tools."


def test_workable_adapter_html_fallback_job_links_huggingface_style() -> None:
    career_board = _career_board("WORKABLE", "huggingface")
    html = """
    <html>
      <body>
        <a href="/huggingface/j/ABC123/">Research Engineer, Inference</a>
        <a href="/huggingface/">Company profile</a>
      </body>
    </html>
    """

    jobs = WorkableAdapter().parse_jobs(
        career_board,
        html,
        page_url="https://apply.workable.com/huggingface/",
    )

    assert len(jobs) == 1
    assert jobs[0].title == "Research Engineer, Inference"
    assert jobs[0].source_job_id == "ABC123"
    assert jobs[0].source_url.unicode_string() == (
        "https://apply.workable.com/huggingface/j/ABC123/"
    )
    assert jobs[0].source_name == "WORKABLE"
    assert jobs[0].source_type == "ATS"


def test_workable_adapter_all_strategies_fail_gives_clear_error() -> None:
    career_board = _career_board("WORKABLE", "huggingface")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, request=request)

    adapter = WorkableAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))

    with pytest.raises(WorkableAdapterError) as exc_info:
        adapter.fetch_jobs(career_board)

    message = str(exc_info.value)
    assert "Workable fetch failed for board workable-board" in message
    assert "https://apply.workable.com/api/v3/accounts/huggingface/jobs" in message
    assert "https://apply.workable.com/huggingface/" in message
    assert "https://apply.workable.com/huggingface/jobs" in message


def test_smartrecruiters_adapter_parses_mocked_response() -> None:
    jobs = SmartRecruitersAdapter().parse_jobs(
        _career_board("SMARTRECRUITERS"),
        {
            "content": [
                {
                    "id": "sr-1",
                    "name": "Backend Engineer",
                    "releasedUrl": "https://jobs.smartrecruiters.com/example/sr-1",
                    "location": {"city": "Remote"},
                    "typeOfEmployment": "Full-time",
                    "jobAd": {"sections": {"jobDescription": {"text": "<p>Build APIs.</p>"}}},
                }
            ]
        },
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "SMARTRECRUITERS"
    assert jobs[0].source_type == "ATS"
    assert jobs[0].source_job_id == "sr-1"
    assert jobs[0].remote_type == RemoteType.REMOTE
    assert jobs[0].employment_type == EmploymentType.FULL_TIME
    assert jobs[0].description_text == "Build APIs."


def test_teamtailor_adapter_parses_mocked_response() -> None:
    jobs = TeamtailorAdapter().parse_jobs(
        _career_board("TEAMTAILOR"),
        {
            "data": [
                {
                    "id": "tt-1",
                    "attributes": {
                        "title": "Product Designer",
                        "body": "<p>Design product workflows.</p>",
                        "location": "Remote",
                        "employmentType": "Full-time",
                    },
                    "links": {
                        "careersite-job-url": "https://example.teamtailor.com/jobs/tt-1"
                    },
                }
            ]
        },
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "TEAMTAILOR"
    assert jobs[0].source_type == "ATS"
    assert jobs[0].source_job_id == "tt-1"
    assert jobs[0].remote_type == RemoteType.REMOTE
    assert jobs[0].description_text == "Design product workflows."


def test_recruitee_adapter_parses_mocked_response() -> None:
    jobs = RecruiteeAdapter().parse_jobs(
        _career_board("RECRUITEE"),
        {
            "offers": [
                {
                    "id": 123,
                    "title": "Data Engineer",
                    "careers_url": "https://example.recruitee.com/o/data-engineer",
                    "location": "Remote",
                    "employmentType": "Full-time",
                    "description": "<p>Build data systems.</p>",
                }
            ]
        },
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "RECRUITEE"
    assert jobs[0].source_type == "ATS"
    assert jobs[0].source_job_id == "123"
    assert jobs[0].employment_type == EmploymentType.FULL_TIME
    assert jobs[0].description_text == "Build data systems."


def test_comeet_adapter_parses_mocked_response() -> None:
    jobs = ComeetAdapter().parse_jobs(
        _career_board("COMEET"),
        {
            "positions": [
                {
                    "uid": "cm-1",
                    "name": "Platform Engineer",
                    "url_active_page": "https://www.comeet.com/jobs/example/cm-1",
                    "location": {"name": "Remote"},
                    "employment_type": "Full-time",
                    "description": "<p>Build platform tools.</p>",
                }
            ]
        },
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "COMEET"
    assert jobs[0].source_type == "ATS"
    assert jobs[0].source_job_id == "cm-1"
    assert jobs[0].remote_type == RemoteType.REMOTE
    assert jobs[0].description_text == "Build platform tools."


def test_personio_adapter_parses_mocked_xml_response() -> None:
    jobs = PersonioAdapter().parse_jobs(
        _career_board("PERSONIO"),
        """
        <workzag-jobs>
          <position>
            <id>pn-1</id>
            <name>Support Engineer</name>
            <jobUrl>https://example.jobs.personio.com/job/pn-1</jobUrl>
            <office>Remote</office>
            <employmentType>Full-time</employmentType>
            <jobDescriptions><p>Support customers.</p></jobDescriptions>
          </position>
        </workzag-jobs>
        """,
    )

    assert len(jobs) == 1
    assert jobs[0].source_name == "PERSONIO"
    assert jobs[0].source_type == "ATS"
    assert jobs[0].source_job_id == "pn-1"
    assert jobs[0].employment_type == EmploymentType.FULL_TIME
    assert jobs[0].description_text == "Support customers."


def test_adapter_pack_1_fetches_with_mocked_http_responses() -> None:
    cases = [
        (
            SmartRecruitersAdapter,
            "SMARTRECRUITERS",
            "https://api.smartrecruiters.com/v1/companies/example/postings",
            {"content": [{"id": "sr-1", "name": "Backend", "releasedUrl": "https://sr.test/job"}]},
        ),
        (
            RecruiteeAdapter,
            "RECRUITEE",
            "https://example.recruitee.com/api/offers/",
            {"offers": [{"id": "rc-1", "title": "Backend", "careers_url": "https://rc.test/job"}]},
        ),
        (
            ComeetAdapter,
            "COMEET",
            "https://www.comeet.com/careers-api/2.0/company/example/positions",
            {
                "positions": [
                    {"uid": "cm-1", "name": "Backend", "url_active_page": "https://cm.test/job"}
                ]
            },
        ),
    ]

    for adapter_class, ats_type, expected_url, payload in cases:

        def handler(
            request: httpx.Request,
            *,
            expected_url: str = expected_url,
            payload: dict = payload,
        ) -> httpx.Response:
            assert str(request.url) == expected_url
            return httpx.Response(200, json=payload)

        adapter = adapter_class(client=httpx.Client(transport=httpx.MockTransport(handler)))

        assert adapter.fetch_jobs(_career_board(ats_type))[0].title == "Backend"


def test_adapter_pack_1_unsupported_variants_fail_clearly() -> None:
    cases = [
        (SmartRecruitersAdapter(), SmartRecruitersAdapterError, "SMARTRECRUITERS"),
        (TeamtailorAdapter(), TeamtailorAdapterError, "TEAMTAILOR"),
        (RecruiteeAdapter(), RecruiteeAdapterError, "RECRUITEE"),
        (ComeetAdapter(), ComeetAdapterError, "COMEET"),
        (PersonioAdapter(), PersonioAdapterError, "PERSONIO"),
    ]

    for adapter, error_type, ats_type in cases:
        with pytest.raises(error_type, match="atsSlug"):
            adapter.fetch_jobs(_career_board(ats_type, ats_slug=None))


def test_ats_adapter_manager_routes_supported_ats_types() -> None:
    manager = AtsAdapterManager(
        adapters=[
            GreenhouseAdapter(),
            LeverAdapter(),
            AshbyAdapter(),
            WorkableAdapter(),
            SmartRecruitersAdapter(),
            TeamtailorAdapter(),
            RecruiteeAdapter(),
            ComeetAdapter(),
            PersonioAdapter(),
        ]
    )

    assert manager.get_adapter(_career_board("GREENHOUSE")).ats_type == AtsType.GREENHOUSE
    assert manager.get_adapter(_career_board("LEVER")).ats_type == AtsType.LEVER
    assert manager.get_adapter(_career_board("ASHBY")).ats_type == AtsType.ASHBY
    assert manager.get_adapter(_career_board("WORKABLE")).ats_type == AtsType.WORKABLE
    assert manager.get_adapter(_career_board("SMARTRECRUITERS")).ats_type == AtsType.SMARTRECRUITERS
    assert manager.get_adapter(_career_board("TEAMTAILOR")).ats_type == AtsType.TEAMTAILOR
    assert manager.get_adapter(_career_board("RECRUITEE")).ats_type == AtsType.RECRUITEE
    assert manager.get_adapter(_career_board("COMEET")).ats_type == AtsType.COMEET
    assert manager.get_adapter(_career_board("PERSONIO")).ats_type == AtsType.PERSONIO
    assert manager.get_adapter(_career_board("CUSTOM")) is None


def test_default_ats_adapter_manager_routes_ashby_and_workable() -> None:
    manager = AtsAdapterManager()

    assert manager.get_adapter(_career_board("ASHBY")).ats_type == AtsType.ASHBY
    assert manager.get_adapter(_career_board("WORKABLE")).ats_type == AtsType.WORKABLE
    assert manager.get_adapter(_career_board("SMARTRECRUITERS")).ats_type == AtsType.SMARTRECRUITERS
    assert manager.get_adapter(_career_board("TEAMTAILOR")).ats_type == AtsType.TEAMTAILOR
    assert manager.get_adapter(_career_board("RECRUITEE")).ats_type == AtsType.RECRUITEE
    assert manager.get_adapter(_career_board("COMEET")).ats_type == AtsType.COMEET
    assert manager.get_adapter(_career_board("PERSONIO")).ats_type == AtsType.PERSONIO


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


def test_adapter_pack_1_job_record_payload_includes_source_name_and_source_type() -> None:
    cases = [
        (
            SmartRecruitersAdapter(),
            "SMARTRECRUITERS",
            {
                "content": [
                    {"id": "sr-1", "name": "Backend", "releasedUrl": "https://sr.test/job"}
                ]
            },
        ),
        (
            TeamtailorAdapter(),
            "TEAMTAILOR",
            {
                "data": [
                    {
                        "id": "tt-1",
                        "attributes": {"title": "Backend"},
                        "links": {"careersite-job-url": "https://tt.test/job"},
                    }
                ]
            },
        ),
        (
            RecruiteeAdapter(),
            "RECRUITEE",
            {"offers": [{"id": "rc-1", "title": "Backend", "careers_url": "https://rc.test/job"}]},
        ),
        (
            ComeetAdapter(),
            "COMEET",
            {
                "positions": [
                    {"uid": "cm-1", "name": "Backend", "url_active_page": "https://cm.test/job"}
                ]
            },
        ),
        (
            PersonioAdapter(),
            "PERSONIO",
            (
                "<workzag-jobs><position><id>pn-1</id><name>Backend</name>"
                "<jobUrl>https://pn.test/job</jobUrl></position></workzag-jobs>"
            ),
        ),
    ]

    for adapter, ats_type, payload in cases:
        job = adapter.parse_jobs(_career_board(ats_type), payload)[0]
        serialized = job.model_dump(mode="json", by_alias=True)

        assert serialized["sourceName"] == ats_type
        assert serialized["sourceType"] == "ATS"

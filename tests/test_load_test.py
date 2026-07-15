import asyncio

import httpx

from scripts.load_test import send_request


def test_pdf_load_request_polls_job_to_completion() -> None:
    requested_urls: list[str] = []
    polls = iter(
        [
            {"status": "running", "completed_pages": 1},
            {"status": "completed", "completed_pages": 2},
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.method == "POST":
            return httpx.Response(
                202,
                json={
                    "job_id": "job-1",
                    "status_url": "/jobs/job-1",
                    "result_urls": {
                        "json": "/jobs/job-1/result/json",
                        "markdown": "/jobs/job-1/result/markdown",
                    },
                },
                request=request,
            )
        if "/result/" in request.url.path:
            return httpx.Response(200, content=b"result", request=request)
        return httpx.Response(200, json=next(polls), request=request)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await send_request(
                client,
                b"pdf",
                "document.pdf",
                "http://test:8001/parse/pdf",
                "both",
                1,
                "key",
                5,
                0,
            )
        assert result.status_code == 200
        assert result.job_status == "completed"
        assert result.processed_pages == 2
        assert "http://test:8001/jobs/job-1" in requested_urls
        assert "http://test:8001/jobs/job-1/result/json" in requested_urls

    asyncio.run(run())

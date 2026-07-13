#!/usr/bin/env python3
"""
API Load Test for PaddleOCR-VL

Sends N concurrent requests to the API with the same PDF/image file
and reports latency statistics, throughput, and error rates.

Usage:
    python scripts/load_test.py <file_path> -n 10
    python scripts/load_test.py <file_path> -n 20 --endpoint /parse/image
    python scripts/load_test.py <file_path> -n 5 --timeout 600
    python scripts/load_test.py <file_path> -n 10 --format markdown
    python scripts/load_test.py <file_path> -n 10 --output results.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx


@dataclass
class RequestResult:
    request_num: int
    status_code: int | None = None
    latency_ms: float = 0.0
    error: str | None = None
    processed_pages: int = 0
    response_size_bytes: int = 0


@dataclass
class LoadTestResults:
    file_path: str
    file_size_bytes: int
    endpoint: str
    total_requests: int
    concurrency: int
    output_format: str
    started_at: float = 0.0
    finished_at: float = 0.0
    results: list[RequestResult] = field(default_factory=list)

    @property
    def successful(self) -> list[RequestResult]:
        return [r for r in self.results if r.status_code == 200]

    @property
    def failed(self) -> list[RequestResult]:
        return [r for r in self.results if r.status_code != 200]

    @property
    def latencies(self) -> list[float]:
        return [r.latency_ms for r in self.successful]

    @property
    def total_duration_s(self) -> float:
        return self.finished_at - self.started_at

    def summary(self) -> str:
        lines = []
        lines.append("")
        lines.append("=" * 70)
        lines.append("  LOAD TEST RESULTS")
        lines.append("=" * 70)
        lines.append("")
        lines.append(f"  File:              {self.file_path}")
        lines.append(f"  File size:         {self.file_size_bytes / 1024 / 1024:.1f} MB")
        lines.append(f"  Endpoint:          {self.endpoint}")
        lines.append(f"  Concurrency:       {self.concurrency}")
        lines.append(f"  Output format:     {self.output_format}")
        lines.append(f"  Total requests:    {self.total_requests}")
        lines.append("")
        lines.append("-" * 70)
        lines.append("  OUTCOMES")
        lines.append("-" * 70)
        lines.append(f"  Success (200):     {len(self.successful)}")
        lines.append(f"  Failed:            {len(self.failed)}")
        lines.append(f"  Success rate:      {len(self.successful) / self.total_requests * 100:.1f}%")
        lines.append("")
        lines.append("-" * 70)
        lines.append("  LATENCY (successful requests)")
        lines.append("-" * 70)

        if self.latencies:
            lats = sorted(self.latencies)
            n = len(lats)
            lines.append(f"  Min:               {lats[0]:>10.0f} ms  ({lats[0] / 1000:.1f}s)")
            lines.append(f"  Max:               {lats[-1]:>10.0f} ms  ({lats[-1] / 1000:.1f}s)")
            lines.append(f"  Avg:               {sum(lats) / n:>10.0f} ms  ({sum(lats) / n / 1000:.1f}s)")
            lines.append(f"  P50 (median):      {lats[n // 2]:>10.0f} ms  ({lats[n // 2] / 1000:.1f}s)")
            if n >= 20:
                p95_idx = int(n * 0.95)
                p99_idx = int(n * 0.99)
                lines.append(f"  P95:               {lats[p95_idx]:>10.0f} ms  ({lats[p95_idx] / 1000:.1f}s)")
                lines.append(f"  P99:               {lats[p99_idx]:>10.0f} ms  ({lats[p99_idx] / 1000:.1f}s)")
        else:
            lines.append("  No successful requests")

        lines.append("")
        lines.append("-" * 70)
        lines.append("  THROUGHPUT")
        lines.append("-" * 70)
        lines.append(f"  Total duration:    {self.total_duration_s:.1f}s")
        if self.latencies:
            avg_latency_s = sum(self.latencies) / len(self.latencies) / 1000
            lines.append(f"  Avg latency:       {avg_latency_s:.1f}s")
            lines.append(f"  Effective RPS:     {len(self.successful) / self.total_duration_s:.2f} req/s")
        lines.append(f"  Throughput:        {self.file_size_bytes * len(self.successful) / 1024 / 1024 / self.total_duration_s:.2f} MB/s")
        lines.append("")

        if self.failed:
            lines.append("-" * 70)
            lines.append("  ERRORS")
            lines.append("-" * 70)
            error_counts: dict[str, int] = {}
            for r in self.failed:
                key = f"HTTP {r.status_code}: {r.error or 'unknown'}"
                error_counts[key] = error_counts.get(key, 0) + 1
            for error, count in sorted(error_counts.items()):
                lines.append(f"  {error} (x{count})")
            lines.append("")

        lines.append("-" * 70)
        lines.append("  PER-REQUEST TIMELINE")
        lines.append("-" * 70)
        for r in self.results:
            status = "OK" if r.status_code == 200 else f"ERR({r.status_code})"
            err_msg = f" - {r.error}" if r.error and r.status_code != 200 else ""
            pages = f" [{r.processed_pages} pages]" if r.processed_pages else ""
            size = f" ({r.response_size_bytes / 1024:.0f}KB)" if r.response_size_bytes else ""
            lines.append(
                f"  #{r.request_num:>3d}  {status:>8s}  {r.latency_ms:>8.0f}ms"
                f"{pages}{size}{err_msg}"
            )
        lines.append("")
        lines.append("=" * 70)
        return "\n".join(lines)


async def send_request(
    client: httpx.AsyncClient,
    file_bytes: bytes,
    file_name: str,
    endpoint: str,
    output_format: str,
    request_num: int,
    api_key: str,
) -> RequestResult:
    """Send a single request and return the result."""
    result = RequestResult(request_num=request_num)
    start = time.perf_counter()

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        params = {"output_format": output_format} if "pdf" in endpoint else {}

        files = {"file": (file_name, file_bytes, "application/pdf")}
        response = await client.post(
            endpoint,
            files=files,
            headers=headers,
            params=params,
            timeout=None,  # no timeout — inference can take minutes
        )

        result.latency_ms = (time.perf_counter() - start) * 1000
        result.status_code = response.status_code
        result.response_size_bytes = len(response.content)

        if response.status_code == 200:
            if response.headers.get("content-type", "").startswith("text/markdown"):
                result.processed_pages = int(response.headers["x-processed-pages"])
            else:
                body = response.json()
                result.processed_pages = body.get("processed_pages", 0)
        else:
            body = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
            result.error = body.get("detail", response.text[:200])

    except httpx.TimeoutException:
        result.latency_ms = (time.perf_counter() - start) * 1000
        result.error = "Request timed out"
    except httpx.ConnectError as e:
        result.latency_ms = (time.perf_counter() - start) * 1000
        result.error = f"Connection failed: {e}"
    except Exception as e:
        result.latency_ms = (time.perf_counter() - start) * 1000
        result.error = str(e)

    return result


async def run_load_test(
    base_url: str,
    api_key: str,
    file_path: Path,
    endpoint: str,
    concurrency: int,
    output_format: str,
) -> LoadTestResults:
    """Run the full load test."""
    file_size = file_path.stat().st_size
    full_url = f"{base_url.rstrip('/')}{endpoint}"

    test = LoadTestResults(
        file_path=str(file_path),
        file_size_bytes=file_size,
        endpoint=endpoint,
        total_requests=concurrency,
        concurrency=concurrency,
        output_format=output_format,
    )

    print(f"\n  Starting load test: {concurrency} concurrent requests")
    print(f"  File: {file_path.name} ({file_size / 1024 / 1024:.1f} MB)")
    print(f"  Endpoint: {full_url}")
    print(f"  Format: {output_format}")
    print()

    test.started_at = time.perf_counter()

    # Read file once, reuse bytes for all requests
    file_bytes = file_path.read_bytes()

    async with httpx.AsyncClient() as client:
        # Launch all requests concurrently
        tasks = [
            send_request(
                client, file_bytes, file_path.name, full_url,
                output_format, i + 1, api_key,
            )
            for i in range(concurrency)
        ]

        # Print progress as each completes
        completed = 0
        for coro in asyncio.as_completed(tasks):
            result = await coro
            test.results.append(result)
            completed += 1
            status = "OK" if result.status_code == 200 else f"FAIL({result.status_code})"
            print(
                f"  [{completed:>3d}/{concurrency}]  "
                f"#{result.request_num:>3d}  {status:>8s}  "
                f"{result.latency_ms:>8.0f}ms  "
                f"{result.processed_pages:>3d} pages"
            )

    test.finished_at = time.perf_counter()
    return test


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load test for PaddleOCR-VL API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/load_test.py document.pdf -n 5
  python scripts/load_test.py image.png -n 10 --endpoint /parse/image
  python scripts/load_test.py doc.pdf -n 20 --format markdown --output results.json
        """,
    )
    parser.add_argument("file", type=Path, help="PDF or image file to upload")
    parser.add_argument(
        "-n", "--concurrency", type=int, default=5,
        help="Number of concurrent requests (default: 5)",
    )
    parser.add_argument(
        "--endpoint", default="/parse/pdf",
        choices=["/parse/pdf", "/parse/image"],
        help="API endpoint to test (default: /parse/pdf)",
    )
    parser.add_argument(
        "--format", dest="output_format", default="both",
        choices=["json", "markdown", "both"],
        help="Output format to request (default: both)",
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8080",
        help="API base URL (default: http://localhost:8080)",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="API key (reads from .env if not provided)",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Save detailed results to JSON file",
    )
    return parser.parse_args()


def load_api_key() -> str:
    """Load API key from .env file."""
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("PUBLIC_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def main() -> None:
    args = parse_args()

    # Validate file
    if not args.file.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    # Auto-detect endpoint from file extension
    if args.endpoint == "/parse/pdf" and args.file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".tiff", ".tif"}:
        args.endpoint = "/parse/image"
        print(f"  Auto-detected image file, using {args.endpoint}")

    # Load API key
    api_key = args.api_key or load_api_key()
    if not api_key:
        print("Error: No API key. Set --api-key or PUBLIC_API_KEY in .env", file=sys.stderr)
        sys.exit(1)

    # Run the test
    test = asyncio.run(
        run_load_test(
            base_url=args.base_url,
            api_key=api_key,
            file_path=args.file,
            endpoint=args.endpoint,
            concurrency=args.concurrency,
            output_format=args.output_format,
        )
    )

    # Print summary
    print(test.summary())

    # Save results if requested
    if args.output:
        output_data = {
            "file_path": test.file_path,
            "file_size_bytes": test.file_size_bytes,
            "endpoint": test.endpoint,
            "total_requests": test.total_requests,
            "concurrency": test.concurrency,
            "output_format": test.output_format,
            "total_duration_s": test.total_duration_s,
            "success_count": len(test.successful),
            "failed_count": len(test.failed),
            "latencies_ms": test.latencies,
            "requests": [
                {
                    "request_num": r.request_num,
                    "status_code": r.status_code,
                    "latency_ms": r.latency_ms,
                    "error": r.error,
                    "processed_pages": r.processed_pages,
                    "response_size_bytes": r.response_size_bytes,
                }
                for r in test.results
            ],
        }
        args.output.write_text(json.dumps(output_data, indent=2), encoding="utf-8")
        print(f"  Results saved to: {args.output}")


if __name__ == "__main__":
    main()

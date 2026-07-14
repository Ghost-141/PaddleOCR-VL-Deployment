# Async PaddleOCR-VL API

Authenticated document parsing for one NVIDIA GPU. FastAPI accepts work, SQLite
stores durable page tasks, four workers render PDF pages with `pypdfium2`, Triton
runs layout detection on the selected device, and vLLM continuously batches the
vision-language requests on the GPU.

Only FastAPI is published, on `APP_PORT` (8080 by default). PaddleOCR and
PaddlePaddle are not installed in the API/worker image.

## Run

Requirements: Docker Compose v2, NVIDIA Container Toolkit, and one supported
NVIDIA GPU. The default CPU layout mode also needs enough host RAM for four
layout-pipeline instances.

```bash
cp .env.example .env
openssl rand -hex 32  # put this value in PUBLIC_API_KEY
docker compose up --build
```

`LAYOUT_DEVICE` selects the matching PaddleX HPS image and runtime device.
`LAYOUT_INSTANCE_COUNT` controls the Triton pipeline instances (defaults to 4
for CPU and 1 for GPU when unset), and `VL_MAX_CONCURRENCY` controls recognition
concurrency inside each instance.

```env
LAYOUT_DEVICE=cpu
LAYOUT_INSTANCE_COUNT=4
VL_MAX_CONCURRENCY=2
PADDLEX_HPS_USE_HPIP=0
```

HPIP remains disabled by default because PP-DocLayoutV3 is not currently
compatible with the attempted Paddle2ONNX conversion in this deployment.

The one-shot `model-setup` service downloads the pinned PP-DocLayoutV3 model and
the PaddleOCR-VL 1.6 / PaddleX 3.7 high-stability SDK. It patches the Triton model
repository for the selected device, no dynamic batching, vLLM at
`http://paddleocr-vlm-server:8118/v1`, and the configured instance/concurrency
limits. Changing any of these settings automatically invalidates the prepared
SDK.

Apply HPS configuration changes with:

```bash
docker compose stop api worker triton
docker compose up --build --force-recreate model-setup
docker compose up -d --force-recreate triton api worker
```

Initial vLLM limits are in `deploy/vllm_config.yaml`:

```yaml
gpu-memory-utilization: 0.40
max-num-seqs: 2
max-model-len: 8192
max-num-batched-tokens: 8192
enforce-eager: true
mm-processor-cache-gb: 0
```

## API

`/health` is public. Every parsing, job, cancellation, and result endpoint needs:

```text
Authorization: Bearer <PUBLIC_API_KEY>
```

Submit a PDF:

```bash
curl --fail-with-body -X POST \
  'http://localhost:8080/parse/pdf?output_format=both' \
  -H "Authorization: Bearer $OCR_API_KEY" \
  -F file=@document.pdf
```

The `202 Accepted` response contains a status URL and separate JSON/Markdown
result URLs. See [docs/API.md](docs/API.md) for the full contract.

Images remain synchronous:

```bash
curl --fail-with-body -X POST http://localhost:8080/parse/image \
  -H "Authorization: Bearer $OCR_API_KEY" \
  -F file=@page.png
```

## Operations

```bash
docker compose ps
docker compose logs -f api worker triton paddleocr-vlm-server
curl http://localhost:8080/health
```

The queue accepts 20 active PDF jobs by default. Page leases recover work after
worker crashes, transient backend failures receive three bounded retries, and
terminal jobs are removed after 24 hours. Data lives in the local `app-data`
volume; do not place the SQLite database on NFS.

Use `LAYOUT_DEVICE=gpu` when CPU layout detection starves vLLM, then compare
pages per second, p95 latency, and GPU memory against the default CPU mode.

## Development

```bash
uv sync
uv run pytest -q
docker compose config --quiet
```

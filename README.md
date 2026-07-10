# PaddleOCR-VL API

Authenticated FastAPI service for PaddleOCR-VL. The deployment runs two GPU
containers:

- `paddleocr-vlm-server`: official PaddleOCR vLLM inference service.
- `api`: layout analysis, uploads, result assembly, and HTTP endpoints.

Both containers share one NVIDIA GPU. The supplied vLLM configuration uses 70%
of VRAM, leaving capacity for the layout model on a 24 GB card.

## Project Structure

```text
paddlocr_vl/
├── api/
│   ├── router.py
│   └── routes/
│       ├── documents.py
│       └── health.py
├── core/
│   ├── config.py
│   ├── dependencies.py
│   └── logger.py
├── service/
│   └── paddleocr_vl.py
├── utils/
│   └── file_utils.py
├── main.py
└── schemas.py
```

`PaddleOCRVLService` in `paddlocr_vl/service/paddleocr_vl.py` owns the current
provider integration. It initializes PaddleOCR-VL, calls the vLLM backend,
serializes GPU inference, saves page results, and assembles multi-page output.
The API routers obtain it through `core/dependencies.py` instead of importing
PaddleOCR directly.

The `service` package is the extension point for additional VL OCR providers.
A future provider can be added as another module, for example:

```text
paddlocr_vl/service/
├── paddleocr_vl.py
├── olmocr.py
└── granite_docling.py
```

Provider selection is not dynamic yet. Adding another provider also requires
registering it during application startup and exposing it through the dependency
layer.

## Requirements

- Linux with an NVIDIA GPU of compute capability 8.0 or newer
- NVIDIA driver capable of CUDA 13.x
- Docker Engine 19.03 or newer
- Docker Compose v2 (`docker compose`)
- NVIDIA Container Toolkit
- Internet access for the first image and model download

The application lockfile installs `paddlepaddle-gpu==3.3.0` from
PaddlePaddle's official CUDA 13.0 index. The official PaddleOCR containers may
carry their own tested CUDA runtime; containers use the host NVIDIA driver, not
the host CUDA toolkit installation.

Official references:

- [PaddleOCR-VL usage and deployment](https://www.paddleocr.ai/latest/en/version3.x/pipeline_usage/PaddleOCR-VL.html)
- [PaddlePaddle installation](https://www.paddlepaddle.org.cn/documentation/docs/en/install/index_en.html)
- [NVIDIA Container Toolkit installation](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)

## Verify The Host

Confirm that the driver can see the GPU:

```bash
nvidia-smi
```

Confirm that Docker can expose it to a CUDA 13 container:

```bash
docker run --rm --gpus all \
  nvidia/cuda:13.0.0-base-ubuntu24.04 nvidia-smi
```

Resolve Docker or NVIDIA Container Toolkit errors before starting this stack.

## Configure

Create the local environment file:

```bash
cp .env.example .env
```

Generate a public API key and place it in `.env`:

```bash
openssl rand -hex 32
```

Important settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `PUBLIC_API_KEY` | Required | Bearer token accepted by parsing endpoints |
| `APP_PORT` | `8080` | Port exposed on the host |
| `GPU_DEVICE_ID` | `0` | NVIDIA GPU assigned to both containers |
| `VL_REC_MAX_CONCURRENCY` | `1` | Concurrent vLLM recognition requests |
| `MAX_FILE_SIZE_MB` | `100` | Maximum uploaded file size |
| `MAX_PAGES` | `100` | Maximum PDF pages processed |
| `DELETE_TEMP_FILES` | `true` | Delete request files after responding |
| `API_BASE_IMAGE` | Official online image | PaddleOCR API base image |
| `VLLM_IMAGE` | Official online image | PaddleOCR vLLM image |

Do not commit `.env`; it is excluded by `.gitignore` and `.dockerignore`.

For a 24 GB GPU, retain the default settings initially. If CUDA reports an
out-of-memory error, reduce `gpu-memory-utilization` in
`deploy/vllm_config.yaml`, for example from `0.7` to `0.6`.

## Deploy

Pull the official service image, build the API, and start both services:

```bash
docker compose pull
docker compose build
docker compose up -d
```

The first start is slow because images and model weights must be downloaded.
Watch initialization:

```bash
docker compose logs -f
```

Check container state:

```bash
docker compose ps
```

The API is ready when `api` reports healthy. Test it from the server:

```bash
curl http://localhost:8080/health
```

Interactive API documentation is available at:

```text
http://localhost:8080/docs
```

## Connect

Set the connection details in the client shell. Replace the host with the
server DNS name or IP when connecting remotely:

```bash
export OCR_API_URL=http://localhost:8080
export OCR_API_KEY='the-value-from-PUBLIC_API_KEY'
```

Only `/health` is public. Parsing endpoints require this header:

```text
Authorization: Bearer <PUBLIC_API_KEY>
```

For remote access, allow `APP_PORT` through the host firewall or place the API
behind an HTTPS reverse proxy. Do not expose an unencrypted public HTTP endpoint
because the bearer token and uploaded documents would travel in plaintext.

## Image API

`POST /parse/image` accepts one PNG, JPEG, WebP, or TIFF image per request and
returns both the structured JSON and Markdown results.

```bash
curl --fail-with-body \
  -X POST "$OCR_API_URL/parse/image" \
  -H "Authorization: Bearer $OCR_API_KEY" \
  -F "file=@page.png"
```

Multiple images must currently be sent as separate requests.

## PDF API

`POST /parse/pdf` accepts a multi-page PDF. Processing stops at `MAX_PAGES`.
Use the optional `output_format` query parameter:

| Value | Returned result |
| --- | --- |
| `json` | Page-level structured JSON only |
| `markdown` | Final combined Markdown only |
| `both` | Page JSON, page Markdown, and final combined Markdown |
| Omitted | Same as `both` |

Return both formats:

```bash
curl --fail-with-body \
  -X POST "$OCR_API_URL/parse/pdf" \
  -H "Authorization: Bearer $OCR_API_KEY" \
  -F "file=@document.pdf"
```

Return only final Markdown:

```bash
curl --fail-with-body \
  -X POST "$OCR_API_URL/parse/pdf?output_format=markdown" \
  -H "Authorization: Bearer $OCR_API_KEY" \
  -F "file=@document.pdf"
```

Return only page JSON:

```bash
curl --fail-with-body \
  -X POST "$OCR_API_URL/parse/pdf?output_format=json" \
  -H "Authorization: Bearer $OCR_API_KEY" \
  -F "file=@document.pdf"
```

## Operate

Useful lifecycle commands:

```bash
docker compose restart
docker compose logs -f api
docker compose logs -f paddleocr-vlm-server
docker compose down
```

`docker compose down` keeps the named model and application volumes. To remove
those volumes as well, use `docker compose down --volumes`; subsequent startup
will download models again.

## Local Development

Install the locked Python environment:

```bash
uv sync
```

The local API still requires a reachable vLLM backend. Start the Compose vLLM
service and publish its internal port if doing host-based API development, or
run the complete Compose stack for the supported path.

The ASGI application import path is:

```bash
PUBLIC_API_KEY=development-key \
VLLM_SERVER_URL=http://localhost:8118/v1 \
uv run uvicorn paddlocr_vl.main:app --host 0.0.0.0 --port 8080
```

This command requires a vLLM service reachable at port `8118`. Run tests without
model initialization:

```bash
uv run pytest -q
```

The production API uses one worker because `PaddleOCRVLService` holds a
GPU-resident pipeline and serializes inference calls. Do not increase Uvicorn
workers without accounting for duplicated GPU model memory.

## Troubleshooting

**Container cannot access the GPU**

Run the CUDA container check from `Verify The Host`. Confirm Docker is
configured with NVIDIA Container Toolkit and restart Docker after changing its
runtime configuration.

**vLLM remains unhealthy during first startup**

Model download and initialization can take several minutes. Check
`docker compose logs -f paddleocr-vlm-server`. The health check allows a
10-minute startup period.

**CUDA out of memory**

Stop other GPU processes, verify the selected `GPU_DEVICE_ID`, and lower
`gpu-memory-utilization` in `deploy/vllm_config.yaml`.

**HTTP 401**

The bearer value does not match `PUBLIC_API_KEY`. After changing `.env`, recreate
the API container with `docker compose up -d --force-recreate api`.

**HTTP 413**

The upload exceeds `MAX_FILE_SIZE_MB`. Increase the setting deliberately and
recreate the API container.

**HTTP 415**

The file extension or content type is unsupported, or the file was sent to the
wrong image/PDF endpoint.

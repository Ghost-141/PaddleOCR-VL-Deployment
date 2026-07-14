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
The vendored official SDK selects `config_cpu.pbtxt` or `config_gpu.pbtxt` at
startup. CPU mode has four Triton instances; GPU mode has one. VL recognition
concurrency is two in `deploy/hps/server/pipeline_config.yaml`.

```env
LAYOUT_DEVICE=cpu
PADDLEX_HPS_USE_HPIP=0
```

HPIP remains disabled by default because PP-DocLayoutV3 is not currently
compatible with the attempted Paddle2ONNX conversion in this deployment.

The one-shot `model-setup` service only downloads the pinned PP-DocLayoutV3
model. The official PaddleOCR-VL 1.6 / PaddleX 3.7 HPS server is checked in at
`deploy/hps/server` with no dynamic batching and vLLM configured at
`http://paddleocr-vlm-server:8118/v1`.

Apply HPS configuration changes with:

```bash
docker compose up -d --force-recreate triton
```

## Hardware tuning

Start with the profile closest to the deployment host, then change one value at
a time and compare pages/second, p95 job latency, Triton memory, vLLM waiting
requests, and GPU memory. These are starting points, not capacity guarantees.

| Host | Layout device | HPS instances | Workers | VL concurrency |
|---|---|---:|---:|---:|
| 8 CPU cores, 16 GB RAM | CPU | 1-2 | 2 | 1-2 |
| 16 CPU cores, 32 GB RAM, one 24 GB GPU | CPU | 4 | 4 | 2 |
| 32+ CPU cores, 64+ GB RAM, one GPU | CPU | 6-8 | 6-8 | 2 |
| CPU-constrained host sharing one GPU with vLLM | GPU | 1 | 2-4 | 1-2 |
| Separate layout GPU | GPU | 1-2 per GPU | 4-8 | 2 |

The main controls are in different files:

| Control | File | Effect |
|---|---|---|
| Layout device | `.env`: `LAYOUT_DEVICE=cpu|gpu` | Selects the HPS image and CPU/GPU Triton config |
| CPU instances | `deploy/hps/server/model_repo/layout-parsing/config_cpu.pbtxt` | Independent CPU page pipelines; each copy consumes RAM |
| GPU instances | `deploy/hps/server/model_repo/layout-parsing/config_gpu.pbtxt` | Independent GPU page pipelines; each copy consumes GPU memory |
| VL concurrency | `deploy/hps/server/pipeline_config.yaml`: `max_concurrency` | Maximum simultaneous vLLM calls from each HPS instance |
| PDF workers | `compose.yaml`: `worker.deploy.replicas` | Number of pages that can be submitted to Triton concurrently |

Keep HPS instances and workers close to each other. Extra instances usually sit
idle when there are fewer workers, while too many workers only add queueing when
all instances are busy. A single PDF is limited to two running pages, so higher
worker counts primarily help when several documents are queued.

The maximum possible VL fan-out is approximately `HPS instances x
max_concurrency`, although rendering, layout detection, page contents, and the
worker count usually make the observed value lower. Increasing only vLLM
`max-num-seqs` does not create more work when vLLM is waiting for the CPU layout
stage.

Leave Triton dynamic batching disabled for this Python pipeline. The
`max_batch_size: 8` declarations describe accepted request batches; they do not
combine the separate one-page requests sent by the workers. Keep HPIP disabled
unless the installed PP-DocLayoutV3 version successfully passes a separate HPIP
compatibility test.

For the default 16-core/32-GB/24-GB-GPU host, use CPU layout, four HPS instances,
four workers, and `max_concurrency: 2`. Try `max_concurrency: 3` only when vLLM
has no sustained waiting queue and GPU memory has headroom. Try more CPU HPS
instances only when workers are waiting for Triton and host CPU/RAM have
headroom. Docker CPU percentages are per core: on a 16-core host, `1600%` is the
whole machine and `100%` is one core.

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

Start the complete stack in the background:

```bash
docker compose up --build -d
docker compose ps
curl --fail-with-body http://localhost:${APP_PORT:-8080}/health
```

Stop and resume containers without deleting them:

```bash
docker compose stop
docker compose up -d
```

Restart an unchanged service after a transient failure:

```bash
docker compose restart api
```

`restart` does not apply changed environment variables, images, mounted
configuration, or Compose settings; use the `up --force-recreate` commands
below for those changes.

Stop and remove containers and the Compose network while preserving jobs,
models, and caches in named volumes:

```bash
docker compose down
```

Do not add `--volumes` unless all jobs, results, downloaded models, and caches
may be deleted.

Apply changes according to what was edited:

```bash
# HPS pipeline or Triton config
docker compose up -d --force-recreate triton

# vLLM settings in deploy/vllm_config.yaml
docker compose up -d --force-recreate paddleocr-vlm-server triton

# API/worker Python, requirements, or Dockerfile
docker compose up -d --build api worker

# .env or compose.yaml changes across the stack
docker compose up -d --force-recreate
```

After changing `worker.deploy.replicas`, reconcile the workers with:

```bash
docker compose up -d worker
```

Inspect status and logs:

```bash
docker compose ps
docker compose logs --tail=200 triton
docker compose logs -f api worker triton paddleocr-vlm-server
docker compose top
docker compose events
```

Validate the resolved Compose configuration before restarting:

```bash
docker compose config --quiet
docker compose config
docker compose port api 8080
```

Check public and internal readiness without requiring `curl` in the Triton
container:

```bash
curl --fail-with-body http://localhost:${APP_PORT:-8080}/health
docker compose exec triton python3 -c \
  "import urllib.request; urllib.request.urlopen('http://localhost:8000/v2/health/ready', timeout=5).close(); print('ready')"
docker compose exec api python -c \
  "import urllib.request; urllib.request.urlopen('http://triton:8000/v2/health/ready', timeout=5).close(); print('ready')"
```

Inspect the HPS configuration actually generated at container startup:

```bash
docker compose exec triton grep -n -A5 instance_group \
  /paddlex/var/paddlex_model_repo/layout-parsing/config.pbtxt
docker compose exec triton grep -n -E \
  'model_dir:|server_url:|max_concurrency:' /app/pipeline_config.yaml
```

Monitor resource pressure during a load test:

```bash
docker stats
nvidia-smi
nvidia-smi dmon -s pucm
```

When a service is unhealthy or exits, start with its first startup error rather
than the final dependency failure:

```bash
docker compose ps --all
docker compose logs --tail=300 model-setup
docker compose logs --tail=300 paddleocr-vlm-server
docker compose logs --tail=300 triton
docker compose logs --tail=300 api worker
```

For an interactive restart that keeps the failing service attached to the
terminal:

```bash
docker compose stop triton
docker compose up triton
```

Common failure checks:

| Symptom | First check |
|---|---|
| `dependency ... is unhealthy` | Read the dependency's earlier logs; the dependency message is usually only the final symptom |
| Triton says `failed to load all models` | Search earlier Triton logs for the first `ERROR`, invalid `config.pbtxt`, model mismatch, or conversion failure |
| API is healthy but unreachable remotely | Run `docker compose port api 8080`, use the host IP and published port, then check the host firewall |
| API cannot reach Triton | Run the internal readiness command above from the API container |
| Model setup repeatedly downloads | Check the `models` volume, `HF_TOKEN`, free disk space, and `model-setup` logs |
| Image pull or Python package download times out | Check host DNS, proxy, registry/PyPI access, and retry; host networking does not fix a missing package version |
| A utility such as `curl` is missing in Triton | Use the Python readiness command above instead of installing debugging tools in the container |

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

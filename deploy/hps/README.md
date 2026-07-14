# PaddleX HPS server

This is the official PaddleOCR-VL 1.6 HPS server from PaddleX 3.7, SDK version
`0.1.0`, mounted directly at `/app` by Compose.

Source archive:
`https://paddle-model-ecology.bj.bcebos.com/paddlex/PaddleX3.0/deploy/paddlex_hps/public/sdks/v3.7/paddlex_hps_PaddleOCR-VL-1.6_sdk.tar.gz`

SHA-256: `dc7f8e825eace854a824b0eee5daa41507a3e28981b6d53ec72ebe94a2592474`

Deployment settings live in:

- `server/pipeline_config.yaml`: layout model path, vLLM URL and VL concurrency.
- `server/model_repo/layout-parsing/config_cpu.pbtxt`: CPU instance count.
- `server/model_repo/layout-parsing/config_gpu.pbtxt`: GPU instance count.

After editing these files, recreate Triton:

```bash
docker compose up -d --force-recreate triton
```

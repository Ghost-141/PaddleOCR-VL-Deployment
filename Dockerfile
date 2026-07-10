# Official PaddleOCR NVIDIA GPU image documented for PaddleOCR-VL.
ARG PADDLEOCR_IMAGE=ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-nvidia-gpu
FROM ${PADDLEOCR_IMAGE}

# uv's official distroless image supplies a pinned package-manager binary.
COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

COPY pyproject.toml uv.lock README.md ./
RUN python -m venv --system-site-packages /opt/venv \
    && uv sync --frozen --no-dev --no-install-project

COPY paddlocr_vl ./paddlocr_vl
COPY server.py ./server.py
RUN uv sync --frozen --no-dev

EXPOSE 8080
CMD ["uvicorn", "paddlocr_vl.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

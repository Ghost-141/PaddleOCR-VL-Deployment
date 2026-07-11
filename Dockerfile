# Official PaddleOCR NVIDIA GPU image documented for PaddleOCR-VL.
ARG PADDLEOCR_IMAGE=ccr-2vdh3abv-pub.cnc.bj.baidubce.com/paddlepaddle/paddleocr-vl:latest-nvidia-gpu-offline
FROM ${PADDLEOCR_IMAGE}

# The official PaddleOCR image uses an unprivileged default user. Root is
# used by PaddleOCR's own documented Compose deployment.
USER root

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY requirements.docker.txt ./requirements.docker.txt
# Install only the small application-owned runtime set. The heavyweight
# PaddleOCR/PaddlePaddle/CUDA stack remains inherited from the base image.
RUN python -m pip install \
    --no-cache-dir \
    --disable-pip-version-check \
    --timeout 300 \
    --retries 10 \
    -r requirements.docker.txt

COPY paddlocr_vl ./paddlocr_vl
COPY scripts ./scripts
COPY server.py ./server.py

# Fail during build if either the installed application dependencies or the
# provider runtime inherited from the official image is unavailable.
RUN command -v hf \
    && python -c "import dotenv, fastapi, multipart, paddleocr, safetensors, uvicorn"

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "paddlocr_vl.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

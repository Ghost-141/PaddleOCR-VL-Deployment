# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends bash ca-certificates curl libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.docker.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    for attempt in 1 2 3 4 5; do \
        python -m pip install --disable-pip-version-check --timeout 120 --retries 10 \
            -r requirements.docker.txt && break; \
        test "$attempt" = 5 && exit 1; \
        sleep "$((attempt * 5))"; \
    done

COPY paddlocr_vl ./paddlocr_vl
COPY scripts ./scripts

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "paddlocr_vl.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

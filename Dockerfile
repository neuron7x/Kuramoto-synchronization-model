# SPDX-License-Identifier: MIT

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY constraints/security.txt constraints/security.txt
COPY requirements.lock requirements.lock

RUN pip install --no-cache-dir -c constraints/security.txt -r requirements.lock

COPY . .

EXPOSE 8000

CMD [
    "python",
    "-m",
    "uvicorn",
    "application.api.service:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000"
]

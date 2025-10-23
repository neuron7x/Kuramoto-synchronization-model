# SPDX-License-Identifier: MIT
FROM python:3.11.9-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADEPULSE_HTTP_PORT=8000

WORKDIR /app

# Keep the base image patched to satisfy vulnerability scanners.
RUN apt-get update \
    && apt-get dist-upgrade -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.lock

COPY . ./

EXPOSE 8000

ENTRYPOINT ["python", "-m", "application.runtime.serve"]

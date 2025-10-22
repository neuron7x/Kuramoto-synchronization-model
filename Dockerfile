# SPDX-License-Identifier: MIT

# ---- Build stage ---------------------------------------------------------
FROM python:3.12-slim AS builder

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN python -m venv "$VIRTUAL_ENV"

# Install system headers required for Python packages that ship C extensions.
RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        libffi-dev \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock ./

RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir --requirement requirements.lock

# ---- Runtime stage -------------------------------------------------------
FROM python:3.12-slim

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Runtime shared libraries for optional database drivers, TLS, and native extensions.
RUN apt-get update \
    && apt-get upgrade --yes \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        curl \
        libffi8 \
        libgomp1 \
        libpq5 \
        libssl3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# Create an unprivileged user that owns application files.
RUN addgroup --system tradepulse \
    && adduser --system --ingroup tradepulse tradepulse

WORKDIR /app

COPY --chown=tradepulse:tradepulse . ./

RUN mkdir -p /app/state \
    && chown -R tradepulse:tradepulse /app/state

USER tradepulse

EXPOSE 8001

CMD ["uvicorn", "application.api.service:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]

# SPDX-License-Identifier: MIT
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y \
        build-essential \
        curl \
        libpq-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.lock ./
RUN python -m pip install --no-cache-dir -r requirements.lock

RUN useradd --create-home --shell /bin/bash tradepulse

# Copy the application source so the API server and supporting packages
# are available inside the container image used by the smoke tests.
COPY --chown=tradepulse:tradepulse . .

EXPOSE 8000

USER tradepulse

CMD ["uvicorn", "application.api.service:app", "--host", "0.0.0.0", "--port", "8000"]

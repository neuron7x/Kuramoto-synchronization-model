# SPDX-License-Identifier: MIT

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRADEPULSE_HTTP_PORT=8000 \
    TRADEPULSE_CONFIG_VAULT_PATH=/tmp/tradepulse/config_vault.json \
    TRADEPULSE_KILL_SWITCH_STORE_PATH=/tmp/tradepulse/kill_switch_state.sqlite

WORKDIR /app

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY constraints/security.txt constraints/security.txt
COPY requirements.lock requirements.lock

RUN pip install --no-cache-dir -c constraints/security.txt -r requirements.lock

COPY . .

RUN chmod +x docker/entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/bin/sh", "docker/entrypoint.sh"]

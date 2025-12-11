# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies if needed (none currently required)
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     <package-name> \
#     && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies with security constraints
COPY requirements.lock ./
COPY constraints/security.txt ./constraints/
RUN pip install --no-cache-dir -c constraints/security.txt -r requirements.lock

# Copy FastAPI application sources and supporting packages.
COPY application ./application
COPY analytics ./analytics
COPY core ./core
COPY domain ./domain
COPY execution ./execution
COPY observability ./observability
COPY src ./src

# Runtime assets required by the service.
COPY configs ./configs
COPY sitecustomize.py ./sitecustomize.py

RUN mkdir -p state

EXPOSE 8000

CMD ["python", "-m", "application.runtime.server"]

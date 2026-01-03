# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary

# =============================================================================
# Stage 1: Lightweight scan stage (for security scanning only)
# This stage excludes heavy GPU dependencies to reduce image size
# =============================================================================
FROM python:3.12.8-slim AS scan

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Update system packages to fix known vulnerabilities
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    ca-certificates \
    libexpat1 \
    libssl3 \
    libkrb5-3 && \
    rm -rf /var/lib/apt/lists/* && \
    apt-get clean

ENV SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt

# Copy requirements files (scan lock excludes torch and NVIDIA CUDA libraries)
COPY requirements-scan.lock ./
COPY constraints/security.txt ./constraints/

# Install minimal dependencies for security scanning
# This excludes torch and therefore avoids pulling heavy NVIDIA CUDA libraries (~2GB)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -c constraints/security.txt -r requirements-scan.lock

# Copy application code for scanning
COPY application ./application
COPY analytics ./analytics
COPY core ./core
COPY domain ./domain
COPY execution ./execution
COPY observability ./observability
COPY src ./src
COPY configs ./configs
COPY sitecustomize.py ./sitecustomize.py

RUN mkdir -p state

EXPOSE 8000

CMD ["python", "-m", "application.runtime.server"]

# =============================================================================
# Stage 2: Full runtime stage with GPU support (for production)
# =============================================================================
FROM python:3.11-slim AS runtime

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

# Copy and install ALL dependencies including GPU libraries
COPY requirements.lock ./
COPY constraints/security.txt ./constraints/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -c constraints/security.txt -r requirements.lock

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

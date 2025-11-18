# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
FROM python:3.12-slim

# Security: Create non-root user for running the application
RUN groupadd -r tradepulse && useradd -r -g tradepulse tradepulse

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.lock ./

# Security: Install dependencies with constraint file to enforce security versions
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

# Legacy components that remain part of the runtime environment.
COPY nfpro ./nfpro

RUN mkdir -p state && chown -R tradepulse:tradepulse /app

# Security: Switch to non-root user
USER tradepulse

EXPOSE 8000

# Security: Set default host binding for container environment
ENV API_SERVER_HOST=0.0.0.0

CMD ["python", "-m", "application.runtime.server"]

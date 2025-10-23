# SPDX-License-Identifier: MIT
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

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

RUN mkdir -p state

EXPOSE 8000

CMD ["uvicorn", "application.api.service:app", "--host", "0.0.0.0", "--port", "8000"]

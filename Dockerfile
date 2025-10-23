# SPDX-License-Identifier: MIT
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock

# Copy application packages and supporting modules required at runtime.
COPY analytics ./analytics
COPY application ./application
COPY backtest ./backtest
COPY core ./core
COPY domain ./domain
COPY execution ./execution
COPY interfaces ./interfaces
COPY markets ./markets
COPY nfpro ./nfpro
COPY observability ./observability
COPY src ./src
COPY tools ./tools

# Runtime assets and configuration templates consumed by the API service.
COPY configs ./configs
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY sitecustomize.py ./sitecustomize.py
COPY VERSION ./VERSION

RUN mkdir -p state

EXPOSE 8000

CMD ["uvicorn", "application.api.service:app", "--host", "0.0.0.0", "--port", "8000"]

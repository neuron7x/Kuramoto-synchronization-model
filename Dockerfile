# SPDX-License-Identifier: MIT
FROM python:3.11-slim

WORKDIR /app

# Development defaults ensure the FastAPI service can boot without external secrets.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=0 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app \
    TRADEPULSE_AUDIT_SECRET=local-dev-audit-secret

COPY requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock

# Copy application packages and supporting modules required at runtime.
COPY analytics application backtest core domain execution interfaces \
    markets nfpro observability src tools ./

# Runtime assets and configuration templates consumed by the API service.
COPY configs alembic.ini migrations sitecustomize.py VERSION ./

RUN mkdir -p state

EXPOSE 8000

CMD ["uvicorn", "application.api.service:app", "--host", "0.0.0.0", "--port", "8000"]

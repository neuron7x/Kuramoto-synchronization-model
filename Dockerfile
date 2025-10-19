# SPDX-License-Identifier: MIT

FROM python:3.11-slim AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1
WORKDIR /build

COPY requirements.lock requirements-dev.lock ./

RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --requirement requirements.lock \
    && /opt/venv/bin/pip install --requirement requirements-dev.lock

COPY . .

ENV PATH="/opt/venv/bin:$PATH"

RUN pytest -m "not slow"


FROM python:3.11-slim AS api
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build /app

EXPOSE 8000

CMD ["uvicorn", "application.api.service:app", "--host", "0.0.0.0", "--port", "8000"]


FROM python:3.11-slim AS runner
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"
WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /build /app

ENTRYPOINT ["python", "-m", "interfaces.cli", "live"]

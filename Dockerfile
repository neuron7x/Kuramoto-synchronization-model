# syntax=docker/dockerfile:1.7
# SPDX-License-Identifier: MIT

ARG PYTHON_VERSION=3.11-slim
ARG BUILDER_IMAGE=python:${PYTHON_VERSION}
ARG RUNTIME_IMAGE=python:${PYTHON_VERSION}

FROM ${BUILDER_IMAGE} AS builder

LABEL org.opencontainers.image.source="https://github.com/example/TradePulse" \
      org.opencontainers.image.description="TradePulse build stage" \
      org.opencontainers.image.licenses="MIT"

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/venv

WORKDIR /workspace

RUN --mount=type=cache,target=/var/cache/apt \
    apt-get update \
    && apt-get install --yes --no-install-recommends build-essential git \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:${PATH}"

COPY requirements.lock ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install --requirement requirements.lock

COPY pyproject.toml ./
COPY README.md README.txt ./
COPY constraints ./constraints
COPY . .

RUN pip install --no-deps .

FROM ${RUNTIME_IMAGE} AS runtime

LABEL org.opencontainers.image.title="TradePulse" \
      org.opencontainers.image.description="Quantitative research and execution platform" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /workspace/nfpro ./nfpro
COPY --from=builder /workspace/analytics ./analytics
COPY --from=builder /workspace/application ./application
COPY --from=builder /workspace/configs ./configs
COPY --from=builder /workspace/conf ./conf
COPY --from=builder /workspace/core ./core
COPY --from=builder /workspace/data ./data
COPY --from=builder /workspace/domain ./domain
COPY --from=builder /workspace/execution ./execution
COPY --from=builder /workspace/libs ./libs
COPY --from=builder /workspace/markets ./markets
COPY --from=builder /workspace/schemas ./schemas
COPY --from=builder /workspace/strategies ./strategies
COPY --from=builder /workspace/scripts ./scripts
COPY --from=builder /workspace/constraints ./constraints
COPY --from=builder /workspace/sitecustomize.py ./sitecustomize.py
COPY --from=builder /workspace/requirements.lock ./requirements.lock
COPY --from=builder /workspace/sample.csv ./sample.csv 2>/dev/null || true

RUN addgroup --system tradepulse \
    && adduser --system --ingroup tradepulse --disabled-password tradepulse \
    && chown -R tradepulse:tradepulse /app

USER tradepulse

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/health', timeout=5.0)" || exit 1

CMD ["python", "-m", "nfpro", "--mode", "paper"]

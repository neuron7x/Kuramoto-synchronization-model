# ── Stage 1: dependency layer (cached) ────────────────────────────
FROM python:3.11-slim AS deps

WORKDIR /build
COPY coherence_bridge/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: production image ────────────────────────────────────
FROM python:3.11-slim

# Non-root user (CIS Docker Benchmark 4.1)
RUN groupadd -r bridge && useradd -r -g bridge -d /app -s /sbin/nologin bridge

WORKDIR /app
COPY --from=deps /install /usr/local
COPY coherence_bridge/ coherence_bridge/

USER bridge
EXPOSE 50051 8080

HEALTHCHECK --interval=10s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" \
    || exit 1

ENTRYPOINT ["python", "-m", "coherence_bridge.main"]

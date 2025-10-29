FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY . .
RUN pip install --upgrade pip setuptools wheel \
    && pip install .
RUN mkdir -p /app/state
FROM gcr.io/distroless/python3-debian12
WORKDIR /app
COPY --from=build /usr/local /usr/local
COPY . .
COPY --from=build --chown=65532:65532 /app/state /app/state
USER 65532:65532
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD ["python","healthcheck.py"]
ENTRYPOINT ["python","-m","app"]

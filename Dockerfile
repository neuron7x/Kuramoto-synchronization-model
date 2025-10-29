FROM python:3.12-slim AS build
WORKDIR /app
COPY pyproject.toml poetry.lock* ./
RUN pip install --no-cache-dir poetry && poetry export -f requirements.txt --output requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-cache-dir -r requirements.txt
FROM gcr.io/distroless/python3-debian12
WORKDIR /app
COPY --from=build /usr/local /usr/local
COPY . .
USER 65532:65532
ENV PYTHONUNBUFFERED=1
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD ["python","healthcheck.py"]
ENTRYPOINT ["python","-m","app"]

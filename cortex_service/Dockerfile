# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3

WORKDIR /service

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY cortex_service ./cortex_service

ENV CORTEX_CONFIG_PATH=/service/cortex_service/config/service.yaml

EXPOSE 8001

CMD ["uvicorn", "cortex_service.app.api:create_app", "--host", "0.0.0.0", "--port", "8001", "--factory"]

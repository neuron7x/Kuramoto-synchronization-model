# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3

WORKDIR /service

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY cortex_service ./cortex_service
COPY core/__init__.py ./core/__init__.py
COPY core/security ./core/security

ENV CORTEX_CONFIG_PATH=/service/cortex_service/config/service.yaml

EXPOSE 8001

CMD ["python", "-m", "cortex_service.app.runtime"]

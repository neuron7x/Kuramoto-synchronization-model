# SPDX-License-Identifier: MIT
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.lock ./

RUN pip install --no-cache-dir -r requirements.lock

COPY . ./

EXPOSE 8001

CMD [
    "python",
    "-m",
    "uvicorn",
    "application.api.service:create_app",
    "--factory",
    "--host",
    "0.0.0.0",
    "--port",
    "8001"
]

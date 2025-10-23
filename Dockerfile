# SPDX-License-Identifier: MIT
FROM python:3.13-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADEPULSE_HTTP_PORT=8000

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

COPY . ./

EXPOSE 8000

CMD ["/bin/sh", "-c", "python -m uvicorn application.api.service:app --host 0.0.0.0 --port ${TRADEPULSE_HTTP_PORT}"]

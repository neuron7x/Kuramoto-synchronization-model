# syntax=docker/dockerfile:1
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

RUN apt-get update \
    && apt-get install --no-install-recommends -y build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY sandbox/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY sandbox ./sandbox

EXPOSE 8000

ENTRYPOINT ["uvicorn", "--factory"]
CMD ["sandbox.market.app:create_app", "--host", "0.0.0.0", "--port", "8000"]

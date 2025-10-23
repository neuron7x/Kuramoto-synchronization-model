# SPDX-License-Identifier: MIT
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Copy the application source so the API server and supporting packages
# are available inside the container image used by the smoke tests.
COPY . .

EXPOSE 8000

CMD ["uvicorn", "application.api.service:app", "--host", "0.0.0.0", "--port", "8000"]

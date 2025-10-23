# SPDX-License-Identifier: MIT

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install the pinned dependency set before copying the full source tree to
# maximise Docker layer caching for frequent local iterations.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Copy the application source code and assets required for runtime.
COPY . .

EXPOSE 8000

# Launch the FastAPI service with uvicorn so the health check endpoint is
# available for docker compose smoke tests.
CMD [
    "uvicorn",
    "application.api.service:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000"
]

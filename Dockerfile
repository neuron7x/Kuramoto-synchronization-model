# SPDX-License-Identifier: MIT
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Copy the application source code into the image. We copy the project
# in two stages to leverage Docker layer caching for dependency
# installation above.
COPY . ./

# Expose the public HTTP port used by the FastAPI service.
EXPOSE 8001

# Start the FastAPI application with uvicorn. The application object is
# exposed as ``app`` in ``application.api.service``.
CMD [
    "uvicorn",
    "application.api.service:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8001"
]

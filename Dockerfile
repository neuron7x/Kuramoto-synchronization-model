# SPDX-License-Identifier: MIT
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

ARG APP_USER=tradepulse
ARG APP_GROUP=tradepulse

WORKDIR /app

# Create an unprivileged user before copying sources so the runtime container
# does not execute as root. This improves the security posture flagged by the
# CI scanners.
RUN groupadd --system "${APP_GROUP}" \
    && useradd --system --create-home --gid "${APP_GROUP}" "${APP_USER}"

COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock

# Copy the application source code into the image. We copy the project
# in two stages to leverage Docker layer caching for dependency
# installation above.
COPY docker/entrypoint.sh /usr/local/bin/tradepulse-entrypoint.sh
COPY . ./

RUN chmod +x /usr/local/bin/tradepulse-entrypoint.sh \
    && chown -R "${APP_USER}:${APP_GROUP}" /app

# Expose the public HTTP port used by the FastAPI service.
EXPOSE 8001

USER "${APP_USER}"
ENTRYPOINT ["/usr/local/bin/tradepulse-entrypoint.sh"]

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

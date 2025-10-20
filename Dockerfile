# SPDX-License-Identifier: MIT
# NOTE: requirements.lock is generated with Python 3.12.
# Use the matching runtime to avoid resolving wheels that are
# unavailable for newer interpreters during CI image builds.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock
COPY nfpro/ ./nfpro/
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "nfpro", "--mode", "paper"]

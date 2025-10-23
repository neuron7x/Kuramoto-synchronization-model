#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Utility entrypoint used by docker-compose health checks."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from typing import Final


HEALTHCHECK_URL: Final[str] = "http://127.0.0.1:8000/health"
REQUEST_TIMEOUT_SECONDS: Final[float] = 5.0
EXPECTED_STATUS: Final[str] = "ok"


def main() -> int:
    try:
        with urllib.request.urlopen(HEALTHCHECK_URL, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            if response.status != 200:
                print(f"Unexpected HTTP status: {response.status}", file=sys.stderr)
                return 1

            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Health endpoint request failed: {exc}", file=sys.stderr)
        return 1
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(f"Health endpoint returned invalid JSON: {exc}", file=sys.stderr)
        return 1

    if payload.get("status") != EXPECTED_STATUS:
        print(f"Service reported unhealthy payload: {payload}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())

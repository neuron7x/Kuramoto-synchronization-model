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
EXPECTED_STATUS: Final[str] = "ready"


def main() -> int:
    try:
        with urllib.request.urlopen(
            HEALTHCHECK_URL, timeout=REQUEST_TIMEOUT_SECONDS
        ) as response:
            if response.status != 200:
                print(f"Unexpected HTTP status: {response.status}", file=sys.stderr)
                return 1

            raw_body = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"Health endpoint request failed: {exc}", file=sys.stderr)
        return 1
    try:
        body = raw_body.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"Health endpoint returned undecodable payload: {exc}", file=sys.stderr)
        return 1

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        print(f"Health endpoint returned invalid JSON: {exc}", file=sys.stderr)
        return 1

    if not isinstance(payload, dict):
        print(f"Health payload must be a JSON object: {payload!r}", file=sys.stderr)
        return 1

    status = payload.get("status")
    if status != EXPECTED_STATUS:
        print(
            f"Service reported status={status!r}; expected '{EXPECTED_STATUS}'",
            file=sys.stderr,
        )
        return 1

    components = payload.get("components")
    if not isinstance(components, dict):
        print("Health payload missing components section", file=sys.stderr)
        return 1

    unhealthy = []
    malformed = []
    for name, component in components.items():
        if not isinstance(component, dict):
            malformed.append(name)
            continue
        healthy = component.get("healthy")
        if healthy is True:
            continue
        unhealthy.append(name)

    if malformed:
        detail = ", ".join(sorted(malformed))
        print(f"Malformed component payloads: {detail}", file=sys.stderr)
        return 1

    if unhealthy:
        detail = ", ".join(sorted(unhealthy))
        print(f"Unhealthy components reported: {detail}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())

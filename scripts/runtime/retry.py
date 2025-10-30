"""HTTP retry helpers for scripts dealing with rate limits and transient failures."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from typing import Iterable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

_DEFAULT_STATUSES = frozenset({429, 500, 502, 503, 504})
_DEFAULT_METHODS = frozenset(
    {"HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"}
)


def create_resilient_session(
    *,
    total_retries: int = 5,
    backoff_factor: float = 0.5,
    status_forcelist: Iterable[int] | None = None,
    allowed_methods: Iterable[str] | None = None,
    respect_retry_after_header: bool = True,
) -> requests.Session:
    """Return a :class:`requests.Session` configured with sensible retry defaults."""

    retry = Retry(
        total=total_retries,
        status=total_retries,
        read=total_retries,
        connect=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=list(status_forcelist or _DEFAULT_STATUSES),
        allowed_methods=list(allowed_methods or _DEFAULT_METHODS),
        respect_retry_after_header=respect_retry_after_header,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

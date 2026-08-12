# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Simple in-memory intrusion detection helpers."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import DefaultDict


class IDS:
    """Lightweight rate limiting and brute-force detection."""

    def __init__(self) -> None:
        self.failed_attempts: DefaultDict[str, list[datetime]] = defaultdict(list)
        self.rate_limits: DefaultDict[str, list[datetime]] = defaultdict(list)
        self.logger = logging.getLogger("security.ids")

    @staticmethod
    def _sanitize(user: str) -> str:
        """Return a log-safe user identifier."""

        return str(user).replace("\n", "_").replace("\r", "_")

    def check_brute_force(self, user: str, max_attempts: int = 5) -> bool:
        """Return True if blocked due to excessive failures."""

        now = datetime.now()
        self.failed_attempts[user] = [
            t for t in self.failed_attempts[user] if now - t < timedelta(minutes=15)
        ]

        if len(self.failed_attempts[user]) >= max_attempts:
            self.logger.warning("BRUTE_FORCE_DETECTED: %s", self._sanitize(user))
            return True
        return False

    def record_failure(self, user: str) -> None:
        """Record a failed attempt for the user."""

        self.failed_attempts[user].append(datetime.now())

    def check_rate_limit(self, user: str, max_requests: int = 100) -> bool:
        """Return True if blocked due to rate limiting."""

        now = datetime.now()
        self.rate_limits[user] = [
            t for t in self.rate_limits[user] if now - t < timedelta(minutes=1)
        ]

        if len(self.rate_limits[user]) >= max_requests:
            self.logger.warning("RATE_LIMIT_EXCEEDED: %s", self._sanitize(user))
            return True

        self.rate_limits[user].append(now)
        return False


ids = IDS()

"""System-level actions for WML (CPU affinity, control plane integration)."""

import os
import json
from dataclasses import dataclass
from typing import Dict, Optional, List
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from ..actions import Action, ActionPlan


@dataclass
class SystemActions(Action):
    """System-level action implementation.

    Handles:
    - CPU affinity pinning (Linux only)
    - Control plane communication for distributed systems
    - Graceful degradation on non-Linux platforms
    """

    control_base_url: Optional[str] = None
    pid: int = os.getpid()
    _fail_count: int = 0  # NEW: Track control plane failures

    def __post_init__(self) -> None:
        """Initialize action state."""
        self._prior_affinity: Dict[str, List[int]] = {}

    def _set_affinity(self, cpus: List[int]) -> None:
        """Set CPU affinity (Linux only, no-op elsewhere)."""
        if hasattr(os, "sched_setaffinity"):
            try:
                os.sched_setaffinity(self.pid, set(cpus))
            except Exception:
                pass  # No-op on non-Linux or without permissions

    def _get_affinity(self) -> List[int]:
        """Get current CPU affinity."""
        if hasattr(os, "sched_getaffinity"):
            try:
                return sorted(list(os.sched_getaffinity(self.pid)))
            except Exception:
                return list(range(os.cpu_count() or 1))
        return list(range(os.cpu_count() or 1))

    def _choose_cpus_for_hotpath(self, plan: ActionPlan) -> List[int]:
        """Choose CPU cores based on fusion depth."""
        depth = int(plan.conduct.get("fusion_depth", 1))
        want = 1 if depth <= 2 else 2
        total = os.cpu_count() or 1
        return list(range(min(want, total)))

    def _control_push(self, path: str, plan: ActionPlan) -> None:
        """Push action plan to control plane."""
        if not self.control_base_url:
            return

        payload = {
            "path": path,
            "timing": plan.timing,
            "conduct": plan.conduct,
            "metabolic": plan.metabolic,
        }
        data = json.dumps(payload).encode("utf-8")
        url = f"{self.control_base_url.rstrip('/')}/apply"
        req = Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )

        try:
            with urlopen(req, timeout=1.5) as r:
                _ = r.status
            self._fail_count = 0
        except (URLError, HTTPError):
            self._fail_count += 1

    def _control_rollback(self, path: str) -> None:
        """Rollback via control plane."""
        if not self.control_base_url:
            return

        data = json.dumps({"path": path}).encode("utf-8")
        url = f"{self.control_base_url.rstrip('/')}/rollback"
        req = Request(
            url, data=data, headers={"Content-Type": "application/json"}, method="POST"
        )

        try:
            with urlopen(req, timeout=1.5) as r:
                _ = r.status
        except (URLError, HTTPError):
            self._fail_count += 1

    def apply(self, path: str, plan: ActionPlan) -> None:
        """Apply action plan to the system."""
        # Save current affinity for rollback
        if path not in self._prior_affinity:
            self._prior_affinity[path] = self._get_affinity()

        # Apply CPU pinning if requested
        if plan.conduct.get("pinning", False):
            self._set_affinity(self._choose_cpus_for_hotpath(plan))

        # Push to control plane
        self._control_push(path, plan)

    def rollback(self, path: str, plan: ActionPlan) -> None:
        """Rollback action plan."""
        # Restore previous CPU affinity
        prev = self._prior_affinity.get(path)
        if prev is not None:
            self._set_affinity(prev)

        # Rollback via control plane
        self._control_rollback(path)

    @property
    def fail_count(self) -> int:
        """Get control plane failure count (for diagnostics)."""
        return self._fail_count

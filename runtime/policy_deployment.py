"""Policy deployment utilities with rollback and shadow routing."""

from __future__ import annotations

import concurrent.futures
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

from runtime.model_registry import ModelMetadata


PolicyHandler = Callable[..., Any]


@dataclass(frozen=True)
class PolicyVersion:
    """A concrete policy version with handler and metadata."""

    policy_id: str
    version: str
    handler: PolicyHandler
    metadata: Optional[ModelMetadata] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class ShadowDeployment:
    """State container for a shadow deployment."""

    policy_id: str
    primary_version: PolicyVersion
    shadow_version: PolicyVersion
    traffic_ratio: float = 0.1
    active: bool = True
    metrics: List[Dict[str, float]] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    def record_metrics(self, metrics: Mapping[str, float]) -> None:
        self.metrics.append({k: float(v) for k, v in metrics.items()})

    def summarize(self) -> Dict[str, float]:
        if not self.metrics:
            return {}
        keys = self.metrics[0].keys()
        summary: Dict[str, float] = {}
        for key in keys:
            values = [m.get(key, 0.0) for m in self.metrics]
            summary[f"{key}_avg"] = float(sum(values) / max(len(values), 1))
        return summary


@dataclass(frozen=True)
class RollbackPlan:
    """Rollback plan for a policy deployment."""

    policy_id: str
    from_version: PolicyVersion
    to_version: PolicyVersion
    reason: str
    created_at: float = field(default_factory=time.time)


class PolicyDeploymentManager:
    """Manage policy activation, shadow deployment, and rollback."""

    def __init__(self, *, safe_mode_handler: PolicyHandler | None = None) -> None:
        self._versions: Dict[str, Dict[str, PolicyVersion]] = {}
        self._active: Dict[str, PolicyVersion] = {}
        self._shadow: Dict[str, ShadowDeployment] = {}
        self.rollback_history: List[RollbackPlan] = []
        self._safe_mode_handler = safe_mode_handler or self._default_safe_mode_handler

    @staticmethod
    def _default_safe_mode_handler(*args: Any, **kwargs: Any) -> Dict[str, object]:
        return {
            "action": "hold",
            "safe_mode": True,
            "reason": "policy_fallback",
        }

    def register_policy(
        self,
        policy_id: str,
        version: str,
        handler: PolicyHandler,
        *,
        metadata: Optional[ModelMetadata] = None,
    ) -> PolicyVersion:
        version_map = self._versions.setdefault(policy_id, {})
        if version in version_map:
            return version_map[version]
        policy_version = PolicyVersion(
            policy_id=policy_id,
            version=version,
            handler=handler,
            metadata=metadata,
        )
        version_map[version] = policy_version
        if policy_id not in self._active:
            self._active[policy_id] = policy_version
        return policy_version

    def activate_policy(self, policy_id: str, version: str) -> PolicyVersion:
        policy_version = self._versions[policy_id][version]
        self._active[policy_id] = policy_version
        return policy_version

    def get_active_policy(self, policy_id: str) -> PolicyVersion:
        return self._active[policy_id]

    def start_shadow(
        self,
        policy_id: str,
        shadow_version: str,
        *,
        traffic_ratio: float = 0.1,
    ) -> ShadowDeployment:
        primary = self._active[policy_id]
        shadow = self._versions[policy_id][shadow_version]
        deployment = ShadowDeployment(
            policy_id=policy_id,
            primary_version=primary,
            shadow_version=shadow,
            traffic_ratio=traffic_ratio,
        )
        self._shadow[policy_id] = deployment
        return deployment

    def stop_shadow(self, policy_id: str) -> None:
        if policy_id in self._shadow:
            self._shadow[policy_id].active = False

    def shadow_infer(
        self,
        policy_id: str,
        *args: Any,
        timeout: float | None = 0.3,
        fallback_handler: PolicyHandler | None = None,
        **kwargs: Any,
    ) -> Any:
        primary = self._active[policy_id]
        handler = primary.handler
        if timeout is None or timeout <= 0:
            timeout = None
        try:
            if timeout is None:
                result = handler(*args, **kwargs)
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(handler, *args, **kwargs)
                    try:
                        result = future.result(timeout=timeout)
                    except concurrent.futures.TimeoutError as exc:
                        future.cancel()
                        raise TimeoutError(
                            f"policy_infer exceeded {timeout:.3f}s timeout"
                        ) from exc
        except Exception:
            safe_handler = fallback_handler or self._safe_mode_handler
            return safe_handler(*args, **kwargs)
        shadow = self._shadow.get(policy_id)
        if shadow and shadow.active and random.random() <= shadow.traffic_ratio:
            shadow.handler(*args, **kwargs)
        return result

    def create_rollback_plan(self, policy_id: str, reason: str) -> RollbackPlan:
        current = self._active[policy_id]
        versions = list(self._versions[policy_id].values())
        if len(versions) < 2:
            raise ValueError("No previous policy version available for rollback")
        previous = sorted(versions, key=lambda v: v.created_at)[-2]
        return RollbackPlan(
            policy_id=policy_id,
            from_version=current,
            to_version=previous,
            reason=reason,
        )

    def execute_rollback(self, plan: RollbackPlan) -> PolicyVersion:
        self.rollback_history.append(plan)
        return self.activate_policy(plan.policy_id, plan.to_version.version)

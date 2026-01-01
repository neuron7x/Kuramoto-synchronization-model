"""Neural controller integration bridge for TradePulse."""

from __future__ import annotations

import inspect
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping

import numpy as np
import yaml

from ..config import load_default_config, merge_config
from ..core.emh_model import EMHSSM
from ..core.params import (
    EKFConfig,
    HomeoConfig,
    MarketAdapterConfig,
    Params,
    PolicyConfig,
    PolicyModeConfig,
    PredictiveConfig,
    RiskConfig,
    SensoryConfig,
    TemporalGatingConfig,
)
from ..core.state import EMHState
from ..core.sensory_schema import SCHEMA_VERSION
from ..estimation.belief import VolBelief
from ..estimation.ekf import EMHEKF
from ..homeostasis.homeo import HomeostaticModule
from ..policy.controller import BasalGangliaController
from ..risk.cvar import CVARGate
from ..telemetry.metrics import DecisionMetricsExporter, MetricsEmitter
from ..util.logging import log_decision
from .sensory_pipeline import SensoryPipeline

log = logging.getLogger(__name__)


def _call_with_known_kwargs(func: Callable[..., Any], **kwargs: Any) -> Any:
    signature = inspect.signature(func)
    accepted = {
        name: kwargs[name]
        for name in signature.parameters
        if name in kwargs
        and signature.parameters[name].kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    if accepted:
        return func(**accepted)
    return func(**kwargs)


class TACLSystem:
    """Adapter around the production TACL optimisation layer."""

    def __init__(
        self,
        impl: Any | None = None,
        *,
        generations: int = 10,
    ) -> None:
        self.generations = generations
        self._impl = impl or self._resolve_impl()
        self._optimizer = self._extract_optimizer(self._impl)

    @staticmethod
    def _resolve_impl() -> Any | None:
        provider = os.getenv("TRADEPULSE_NEURO_TACL_PROVIDER", "noop").lower()
        if provider not in {"runtime", "noop"}:
            log.warning("Unknown TACL provider %s", provider)
        if provider == "runtime":
            try:
                import networkx as nx

                from runtime.thermo_controller import ThermoController

                return ThermoController(nx.DiGraph())
            except Exception as exc:  # pragma: no cover - best effort
                log.warning(
                    "Failed to load runtime ThermoController",  # noqa: TRY400
                    extra={"event": "neuro.tacl_import_failed", "error": str(exc)},
                )
        return None

    @staticmethod
    def _extract_optimizer(impl: Any | None) -> Callable[..., Any] | None:
        if impl is None:
            return None
        for candidate in ("optimize_allocations", "optimize"):
            func = getattr(impl, candidate, None)
            if callable(func):
                return func
        return None

    def optimize(
        self,
        allocs: Mapping[str, float],
        temperature: float,
        *,
        generations: int | None = None,
    ) -> Dict[str, Any]:
        gens = generations if generations is not None else self.generations
        base = {"allocs": dict(allocs), "optimized": False}
        if self._optimizer is None:
            return base
        try:
            result = _call_with_known_kwargs(
                self._optimizer,
                allocs=dict(allocs),
                temperature=temperature,
                generations=gens,
            )
        except TypeError:
            result = self._optimizer(dict(allocs), temperature, gens)  # type: ignore[arg-type]
        except Exception as exc:  # pragma: no cover - defensive
            log.exception(
                "TACL optimisation failed",
                extra={"event": "neuro.tacl_error", "error": str(exc)},
            )
            return base
        if isinstance(result, Mapping) and "allocs" in result:
            return dict(result)
        return base


class KuramotoSync:
    """Fetch Kuramoto order parameter from production or fallback sources."""

    def __init__(self, monitor: Callable[[], float] | None = None) -> None:
        self._monitor = monitor or self._resolve_monitor()

    @staticmethod
    def _resolve_monitor() -> Callable[[], float]:
        provider = os.getenv("TRADEPULSE_NEURO_KURAMOTO_PROVIDER", "noop").lower()
        if provider == "cortex":  # pragma: no cover - optional dependency
            try:
                from cortex_service.app.sync.ensemble import kuramoto_order_parameter

                def _monitor() -> float:
                    return float(kuramoto_order_parameter([]))

                return _monitor
            except Exception as exc:
                log.warning(
                    "Kuramoto provider failed",  # noqa: TRY400
                    extra={"event": "neuro.kuramoto_import_failed", "error": str(exc)},
                )
        return lambda: 0.5

    def get_order_parameter(self) -> float:
        try:
            value = float(self._monitor())
        except Exception as exc:  # pragma: no cover - defensive path
            log.exception(
                "Kuramoto monitor failure",
                extra={"event": "neuro.kuramoto_error", "error": str(exc)},
            )
            return 0.5
        return float(np.clip(value, 0.0, 1.0))


class NeuralMarketController:
    """Full neuro stack combining EMH dynamics, EKF, policy, and safety gates."""

    def __init__(
        self,
        params: Params,
        ekf: EKFConfig,
        policy: PolicyConfig,
        risk: RiskConfig,
        homeo: HomeoConfig,
        sensory: SensoryConfig | None = None,
        sensory_schema: SensorySchema | None = None,
        predictive: PredictiveConfig | None = None,
        adapter: MarketAdapterConfig | None = None,
        temporal_gating: TemporalGatingConfig | None = None,
        *,
        emit_predictive_state: bool = False,
    ) -> None:
        self.model = EMHSSM(params, EMHState())
        self.ekf = EMHEKF(params, ekf)
        self.belief = VolBelief()
        self.homeo = HomeostaticModule(homeo.M_target, homeo.k_sigmoid)
        self.ctrl = BasalGangliaController(
            policy.temp,
            policy.tau_E_amber,
            mode_configs=policy.policy_modes,
        )
        self.cvar = CVARGate(risk.cvar_alpha, risk.cvar_limit, risk.lookback)
        self.pipeline = SensoryPipeline(
            sensory=sensory,
            sensory_schema=sensory_schema,
            predictive=predictive,
            temporal_gating=temporal_gating,
        )
        self._last_prediction_error = 0.0
        self._last_predictive_state = None
        self.sync_threshold = 0.30
        self.generations = 10
        self.metrics = MetricsEmitter()
        self.metrics_exporter = DecisionMetricsExporter()
        self.adapter_config = adapter or MarketAdapterConfig()
        self.emit_predictive_state = bool(emit_predictive_state)

    @classmethod
    def from_yaml(cls, path: str | None = None) -> "NeuralMarketController":
        if path is None:
            cfg = dict(load_default_config())
        else:
            yaml_path = Path(path)
            with yaml_path.open("r", encoding="utf-8") as stream:
                raw_cfg = yaml.safe_load(stream)
            default_cfg = load_default_config()
            cfg = merge_config(default_cfg, raw_cfg, safe_merge=True)
        schema_version = cfg.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                "Unsupported sensory schema version "
                f"{schema_version!r}; expected {SCHEMA_VERSION}."
            )
        params = Params(**cfg["model"])
        ekf = EKFConfig(**cfg["ekf"])
        policy_modes = {
            mode: PolicyModeConfig(**values)
            for mode, values in (cfg.get("policy_modes", {}) or {}).items()
        }
        policy = PolicyConfig(**cfg["policy"], policy_modes=policy_modes)
        risk = RiskConfig(**cfg["risk"])
        homeo = HomeoConfig(**cfg["homeostasis"])
        sensory = SensoryConfig(**(cfg.get("sensory", {}) or {}))
        predictive = PredictiveConfig(**(cfg.get("predictive", {}) or {}))
        temporal_gating = TemporalGatingConfig(**(cfg.get("temporal_gating", {}) or {}))
        adapter_cfg = MarketAdapterConfig(**(cfg.get("market_adapter", {}) or {}))
        inst = cls(
            params,
            ekf,
            policy,
            risk,
            homeo,
            sensory=sensory,
            predictive=predictive,
            adapter=adapter_cfg,
            temporal_gating=temporal_gating,
        )
        bridge_cfg = cfg.get("tacl_bridge", {}) or {}
        inst.sync_threshold = float(
            bridge_cfg.get("sync_threshold", inst.sync_threshold)
        )
        inst.generations = int(bridge_cfg.get("generations", inst.generations))
        inst.emit_predictive_state = bool(
            bridge_cfg.get("emit_predictive_state", inst.emit_predictive_state)
        )
        return inst

    def decide(
        self,
        obs: Dict[str, Any],
        *,
        include_prediction_snapshot: bool = False,
    ) -> Dict[str, Any]:
        obs = dict(obs)
        schema_version = obs.pop("schema_version", None)
        expected_fields = obs.pop("expected_fields", None)
        pipeline_result = self.pipeline.apply(
            obs,
            schema_version=schema_version,
            expected_fields=expected_fields,
        )
        prediction_error = pipeline_result.prediction_error
        self._last_prediction_error = prediction_error
        self._last_predictive_state = pipeline_result.predictive_state
        timing_sensory_ms = pipeline_result.timing_sensory_ms
        timing_predictive_ms = pipeline_result.timing_predictive_ms

        belief = self.belief.step(float(obs.get("vol", 0.0)))
        obs["belief_term"] = belief - 0.5

        start = time.perf_counter()
        snapshot = self.model.step(obs)
        timing_model_step_ms = (time.perf_counter() - start) * 1000.0
        snapshot["S"] = float(
            np.clip(snapshot["S"] + 0.10 * self.homeo.pressure(snapshot["M"]), 0.0, 1.0)
        )

        estimate = self.ekf.step(obs)
        estimate_scoped = {f"{key}_est": value for key, value in estimate.items()}

        start = time.perf_counter()
        action, extra = self.ctrl.decide(
            {**snapshot, **estimate}, snapshot["mode"], snapshot["RPE"]
        )
        timing_ctrl_decide_ms = (time.perf_counter() - start) * 1000.0

        scale = self.cvar.update(float(obs.get("reward", 0.0)))
        extra["alloc_main"] = float(extra["alloc_main"] * scale)
        extra["alloc_alt"] = float(extra["alloc_alt"] * scale)

        decision: Dict[str, Any] = {
            **snapshot,
            **estimate_scoped,
            **extra,
            "alloc_scale": scale,
            "belief": belief,
            "prediction_error": prediction_error,
            "action": action,
            "reward": float(obs.get("reward", 0.0)),
            "sensory_confidence": float(obs.get("sensory_confidence", 1.0)),
            "timing_sensory_ms": timing_sensory_ms,
            "timing_predictive_ms": timing_predictive_ms,
            "timing_model_step_ms": timing_model_step_ms,
            "timing_ctrl_decide_ms": timing_ctrl_decide_ms,
        }
        if include_prediction_snapshot or self.emit_predictive_state:
            pred_snapshot = self._last_predictive_state or self.pipeline.snapshot()
            decision.update(
                {
                    "prediction_mu": pred_snapshot.mu,
                    "prediction_error_channels": pred_snapshot.error,
                }
            )

        metrics = self.metrics_exporter.update(decision)
        decision.update(metrics)
        self.metrics.emit(**metrics)
        return decision


class NeuralTACLBridge:
    """Map neural decisions into TACL inputs and apply synchrony guardrails."""

    def __init__(
        self,
        neural: NeuralMarketController,
        tacl: TACLSystem,
        kuramoto: KuramotoSync,
        *,
        sync_threshold: float | None = None,
        generations: int | None = None,
    ) -> None:
        self.neural = neural
        self.tacl = tacl
        self.kuramoto = kuramoto
        self.tacl.generations = neural.generations
        if sync_threshold is not None:
            self.neural.sync_threshold = float(sync_threshold)
        if generations is not None:
            self.neural.generations = int(generations)
            self.tacl.generations = int(generations)

    @staticmethod
    def _action_to_temp(action: str) -> float:
        return {
            "increase_risk": 1.8,
            "decrease_risk": 0.3,
            "switch_to_alt": 1.2,
            "hedge": 0.6,
            "hold": 1.0,
        }.get(action, 1.0)

    @staticmethod
    def _mode_to_coupling(mode: str) -> float:
        return {"GREEN": 0.5, "AMBER": 0.9, "RED": 1.5}.get(mode, 0.5)

    def step(
        self,
        obs: Dict[str, Any],
        *,
        include_prediction_snapshot: bool = False,
    ) -> Dict[str, Any]:
        decision = self.neural.decide(
            obs, include_prediction_snapshot=include_prediction_snapshot
        )
        temperature = self._action_to_temp(decision["action"])
        coupling = self._mode_to_coupling(decision["mode"])

        initial_allocs = {"main": decision["alloc_main"], "alt": decision["alloc_alt"]}
        tacl_out = self.tacl.optimize(
            initial_allocs, temperature, generations=self.neural.generations
        )
        optim_allocs = dict(tacl_out.get("allocs", initial_allocs))

        sync = self.kuramoto.get_order_parameter()
        desync_throttle = sync < self.neural.sync_threshold
        if desync_throttle:
            optim_allocs["main"] *= 0.5
            optim_allocs["alt"] *= 0.5

        decision.update(
            {
                "temperature": temperature,
                "coupling": coupling,
                "sync_order": sync,
                "desync_throttle_applied": desync_throttle,
                "allocs": optim_allocs,
            }
        )
        decision["alloc_main"] = optim_allocs["main"]
        decision["alloc_alt"] = optim_allocs["alt"]
        decision["tacl_optimized"] = bool(tacl_out.get("optimized", False))
        log_decision(decision)
        return decision

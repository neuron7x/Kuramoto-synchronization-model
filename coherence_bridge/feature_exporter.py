"""RF meta-labeling feature export for Askar's ML pipeline.

18 features in 3 tiers:

Tier 1 — Physics (7): topology + synchronization + spectral
  gamma_distance, r_coherence, ricci_sign, lyapunov_sign,
  regime_encoded, regime_confidence, risk_scalar

Tier 2 — Neuroeconomic (7): decision dynamics under uncertainty
  v_net, ei_ratio, kelly_mult, alpha_t, surprise,
  effort_gate, uncertainty_encoded

Tier 3 — Behavioral (4): system arbitration state
  lambda_pav, lambda_hab, lambda_goal, decision_encoded

Why 18 and not 7:
  Tier 1 = WHAT the market is doing (Askar already has OFI for this)
  Tier 2 = HOW CERTAIN the system is (no existing analog in OFI/PCA)
  Tier 3 = WHAT THE SYSTEM DECIDED and why (meta-label of the meta-label)

  Tier 2+3 are orthogonal to everything Askar has. They measure
  the decision process, not the market. This is what hedge funds pay for.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd

from geosync.neuroeconomics.flow_controller import FlowOutput

_REGIME_ENCODING: dict[str, int] = {
    "COHERENT": 0,
    "METASTABLE": 1,
    "DECOHERENT": 2,
    "CRITICAL": 3,
    "UNKNOWN": -1,
}

_DECISION_ENCODING: dict[str, int] = {
    "TRADE": 1,
    "OBSERVE": 0,
    "ABORT": -1,
    "DISSOCIATED": -2,
}

_UNCERTAINTY_ENCODING: dict[str, int] = {
    "EXPECTED": 0,
    "RISK": 1,
    "AMBIGUITY": 2,
    "UNEXPECTED": 3,
}


class RegimeFeatureExporter:
    """Converts regime signals + flow decisions to ML-ready feature dicts."""

    @staticmethod
    def to_ml_features(signal: dict[str, Any]) -> dict[str, float]:
        """Tier 1: 7 physics features from signal dict."""
        gamma = _safe(signal.get("gamma", 1.0))
        ricci = _safe(signal.get("ricci_curvature", 0.0))
        lyap = _safe(signal.get("lyapunov_max", 0.0))

        return {
            "gamma_distance": abs(gamma - 1.0) if math.isfinite(gamma) else 1.0,
            "r_coherence": _safe(signal.get("order_parameter_R", 0.0)),
            "ricci_sign": float(_sign(ricci)),
            "lyapunov_sign": float(_sign(lyap)),
            "regime_encoded": float(_REGIME_ENCODING.get(str(signal.get("regime", "UNKNOWN")), -1)),
            "regime_confidence": _safe(signal.get("regime_confidence", 0.0)),
            "risk_scalar": _safe(signal.get("risk_scalar", 0.0)),
        }

    @staticmethod
    def to_neuro_features(flow: FlowOutput) -> dict[str, float]:
        """Tier 2: 7 neuroeconomic features from FlowOutput."""
        return {
            "v_net": flow.v_net,
            "ei_ratio": flow.ei_ratio,
            "kelly_mult": flow.kelly_mult,
            "alpha_t": flow.alpha_t,
            "surprise": min(1.0, flow.surprise / 4.0),  # normalized to [0,1]
            "effort_gate": flow.effort_gate,
            "uncertainty_encoded": float(_UNCERTAINTY_ENCODING.get(flow.uncertainty_type, 0)),
        }

    @staticmethod
    def to_behavioral_features(flow: FlowOutput) -> dict[str, float]:
        """Tier 3: 4 behavioral arbitration features from FlowOutput."""
        return {
            "lambda_pav": flow.lambda_weights[0],
            "lambda_hab": flow.lambda_weights[1],
            "lambda_goal": flow.lambda_weights[2],
            "decision_encoded": float(_DECISION_ENCODING.get(flow.decision.value, 0)),
        }

    @staticmethod
    def to_dislocation_features(
        dislocation: Any,
    ) -> dict[str, float]:
        """Tier 4: 4 topology dislocation features (DislocationState)."""
        if dislocation is None:
            return {
                "kappa_velocity": 0.0,
                "gamma_velocity": 0.0,
                "r_acceleration": 0.0,
                "dislocation_score": 0.0,
            }
        return {
            "kappa_velocity": float(getattr(dislocation, "kappa_velocity", 0.0)),
            "gamma_velocity": float(getattr(dislocation, "gamma_velocity", 0.0)),
            "r_acceleration": float(getattr(dislocation, "r_acceleration", 0.0)),
            "dislocation_score": float(getattr(dislocation, "dislocation_score", 0.0)),
        }

    @staticmethod
    def to_full_features(
        signal: dict[str, Any],
        flow: FlowOutput,
        dislocation: Any = None,
    ) -> dict[str, float]:
        """All 22 features: physics + neuroeconomic + behavioral + dislocation."""
        features: dict[str, float] = {}
        features.update(RegimeFeatureExporter.to_ml_features(signal))
        features.update(RegimeFeatureExporter.to_neuro_features(flow))
        features.update(RegimeFeatureExporter.to_behavioral_features(flow))
        features.update(RegimeFeatureExporter.to_dislocation_features(dislocation))
        return features

    @staticmethod
    def to_questdb_feature_table(
        signals: list[dict[str, Any]],
        flows: list[FlowOutput] | None = None,
    ) -> pd.DataFrame:
        """DataFrame for QuestDB ASOF JOIN. 7 or 18 features."""
        rows: list[dict[str, object]] = []
        for i, sig in enumerate(signals):
            if flows is not None and i < len(flows):
                row: dict[str, object] = dict(RegimeFeatureExporter.to_full_features(sig, flows[i]))
            else:
                row = dict(RegimeFeatureExporter.to_ml_features(sig))
            row["timestamp"] = pd.Timestamp(sig.get("timestamp_ns", 0), unit="ns", tz="UTC")
            row["instrument"] = sig.get("instrument", "")
            rows.append(row)
        return pd.DataFrame(rows)


def _safe(v: object) -> float:
    """NaN/Inf-safe float conversion — fail-closed to 0.0."""
    if isinstance(v, (int, float)):
        f = float(v)
        return f if math.isfinite(f) else 0.0
    return 0.0


def _sign(x: float) -> int:
    """Ternary sign: -1, 0, or +1."""
    if not math.isfinite(x) or x == 0.0:
        return 0
    return 1 if x > 0 else -1

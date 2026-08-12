# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Runtime binding for the Neuron7X verification-protocol governance kernel.

``data/governance/neuron7x_verification_protocol_v2026_8.json`` declared a full
scoring pipeline — ``score_function``, ``thresholds``, ``conformance_states`` and
a ``weakest_link_rule`` — but **nothing in the codebase loaded or executed it**.
The artifact was policy-theater: a contract described in JSON with no runtime
that honoured it.

This module is that runtime. It loads the kernel, parses the declared weighted
score ``K`` **from the artifact's own formula** (not hardcoded), quantizes ``K``
into the declared conformance state via the declared thresholds, and enforces the
declared weakest-link clamp. Change the kernel's weights or thresholds and the
verdict changes accordingly — that coupling is the binding.

Every contract violation fails closed with ``ValueError``; there is no silent
best-effort path (mirrors the kernel's own fail-closed governance posture).

Boundary: governance conformance only. No runtime, physics, market, trading, or
model-training claim is verified here — this mirrors the kernel's ``boundary``
field verbatim and asserts nothing beyond it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

#: Canonical location of the kernel this module binds.
DEFAULT_KERNEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "governance"
    / "neuron7x_verification_protocol_v2026_8.json"
)

#: Governance-only boundary; this engine verifies conformance, nothing else.
CLAIM_BOUNDARY = "governance_conformance_only_not_runtime_physics_market_or_trading"

#: Tolerances for the declared contract.
_WEIGHT_SUM_TOL = 1e-9
_THRESHOLD_TOL = 1e-9

#: Parses ``0.18R`` / ``0.18*R`` / ``0.18 R`` weight-symbol terms from the formula.
_TERM_RE = re.compile(r"([0-9]*\.?[0-9]+)\s*\*?\s*([A-Za-z_]\w*)")


@dataclass(frozen=True, slots=True)
class Verdict:
    """Outcome of evaluating an artifact against the verification protocol.

    ``score`` is the declared weighted ``K``. ``raw_state`` is the band the score
    falls into. ``weakest_link_state`` is the strongest state the supplied proof
    chain can justify. ``final_state`` is ``min(raw_state, weakest_link_state)``
    by the kernel's conformance order — the weakest-link rule: "the score cannot
    promote a state above the weakest required proof link".
    """

    score: float
    raw_state: str
    weakest_link_state: str
    final_state: str
    clamped: bool


@dataclass(frozen=True, slots=True)
class _Band:
    min: float
    max: float
    state: str


@dataclass(frozen=True, slots=True)
class VerificationProtocol:
    """Executable view of the verification-protocol kernel.

    Built only via :meth:`load`, which validates the artifact fail-closed. The
    weights, thresholds and state order are read from the artifact, so this object
    is a faithful executor of *that* kernel rather than a re-implementation.
    """

    kernel_id: str
    version: str
    weights: tuple[tuple[str, float], ...]
    thresholds: tuple[_Band, ...]
    conformance_order: tuple[str, ...]
    weakest_link_rule: str
    boundary: str

    # ----------------------------------------------------------------- loading
    @classmethod
    def load(cls, path: str | Path | None = None) -> VerificationProtocol:
        """Load and validate the kernel. Raises ``ValueError`` on any violation."""
        kernel_path = Path(path) if path is not None else DEFAULT_KERNEL_PATH
        try:
            raw: Any = json.loads(kernel_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"verification kernel unreadable at {kernel_path}: {exc}") from exc
        if not isinstance(raw, dict):
            raise ValueError("verification kernel must be a JSON object")

        states = raw.get("conformance_states")
        if (
            not isinstance(states, list)
            or len(states) < 2
            or not all(isinstance(s, str) for s in states)
        ):
            raise ValueError("conformance_states must be a list of >= 2 state strings")
        conformance_order: tuple[str, ...] = tuple(states)

        weights = cls._parse_weights(raw)
        thresholds = cls._parse_thresholds(raw, conformance_order)

        weakest_link_rule = raw.get("weakest_link_rule")
        if not isinstance(weakest_link_rule, str) or not weakest_link_rule:
            raise ValueError("weakest_link_rule must be a non-empty string")
        boundary = raw.get("boundary")
        if not isinstance(boundary, str) or not boundary:
            raise ValueError("boundary must be a non-empty string")
        kernel_id = raw.get("id")
        version = raw.get("version")
        if not isinstance(kernel_id, str) or not isinstance(version, str):
            raise ValueError("kernel id and version must be strings")

        return cls(
            kernel_id=kernel_id,
            version=version,
            weights=weights,
            thresholds=thresholds,
            conformance_order=conformance_order,
            weakest_link_rule=weakest_link_rule,
            boundary=boundary,
        )

    @staticmethod
    def _parse_weights(raw: Mapping[str, Any]) -> tuple[tuple[str, float], ...]:
        score_function = raw.get("score_function")
        if not isinstance(score_function, dict):
            raise ValueError("score_function must be an object")
        explicit = score_function.get("weights")
        parsed: dict[str, float]
        if isinstance(explicit, dict) and explicit:
            parsed = {str(k): float(v) for k, v in explicit.items()}
        else:
            formula = score_function.get("formula")
            if not isinstance(formula, str) or "=" not in formula:
                raise ValueError("score_function.formula must be a string 'K = wR + ...'")
            rhs = formula.split("=", 1)[1]
            parsed = {sym: float(w) for w, sym in _TERM_RE.findall(rhs)}
        if not parsed:
            raise ValueError("score_function declares no weighted terms")
        variables = score_function.get("variables")
        if isinstance(variables, dict) and variables:
            declared = set(variables)
            if set(parsed) != declared:
                raise ValueError(
                    f"score_function variables {sorted(declared)} do not match formula terms "
                    f"{sorted(parsed)}"
                )
        if any(w < 0.0 for w in parsed.values()):
            raise ValueError("score_function weights must be non-negative")
        total = sum(parsed.values())
        if abs(total - 1.0) > _WEIGHT_SUM_TOL:
            raise ValueError(f"score_function weights must sum to 1.0; got {total!r}")
        return tuple(sorted(parsed.items()))

    @staticmethod
    def _parse_thresholds(
        raw: Mapping[str, Any], conformance_order: tuple[str, ...]
    ) -> tuple[_Band, ...]:
        thresholds = raw.get("thresholds")
        if not isinstance(thresholds, list) or not thresholds:
            raise ValueError("thresholds must be a non-empty list")
        bands: list[_Band] = []
        for entry in thresholds:
            if not isinstance(entry, dict) or not {"min", "max", "state"} <= set(entry):
                raise ValueError("each threshold needs numeric min, max and a state")
            band = _Band(float(entry["min"]), float(entry["max"]), str(entry["state"]))
            if band.state not in conformance_order:
                raise ValueError(f"threshold state {band.state!r} not in conformance_states")
            if not band.min < band.max:
                raise ValueError(f"threshold band {band} must have min < max")
            bands.append(band)
        bands.sort(key=lambda b: b.min)
        if abs(bands[0].min - 0.0) > _THRESHOLD_TOL or abs(bands[-1].max - 1.0) > _THRESHOLD_TOL:
            raise ValueError("thresholds must partition the full [0, 1] range")
        for lower, upper in zip(bands, bands[1:]):
            if abs(lower.max - upper.min) > _THRESHOLD_TOL:
                raise ValueError(f"thresholds have a gap/overlap between {lower} and {upper}")
        return tuple(bands)

    # -------------------------------------------------------------- evaluation
    @property
    def variables(self) -> tuple[str, ...]:
        return tuple(sym for sym, _ in self.weights)

    def score(self, subscores: Mapping[str, float]) -> float:
        """Declared weighted score ``K`` = Σ wᵢ·sᵢ. Fail-closed on bad subscores."""
        missing = set(self.variables) - set(subscores)
        extra = set(subscores) - set(self.variables)
        if missing or extra:
            raise ValueError(
                f"subscores must cover exactly {sorted(self.variables)}; "
                f"missing={sorted(missing)} extra={sorted(extra)}"
            )
        total = 0.0
        for sym, weight in self.weights:
            value = float(subscores[sym])
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"subscore {sym}={value!r} must lie in [0, 1]")
            total += weight * value
        # Numerically clamp the weighted sum of in-range terms to [0, 1].
        return min(1.0, max(0.0, total))

    def quantize(self, k: float) -> str:
        """Map a score in [0, 1] to its declared conformance state. Fail-closed."""
        if not 0.0 <= k <= 1.0:
            raise ValueError(f"score {k!r} must lie in [0, 1]")
        for band in self.thresholds:
            upper_inclusive = abs(band.max - 1.0) <= _THRESHOLD_TOL
            if band.min - _THRESHOLD_TOL <= k and (
                k < band.max or (upper_inclusive and k <= band.max + _THRESHOLD_TOL)
            ):
                return band.state
        raise ValueError(f"score {k!r} fell outside the declared thresholds")

    def _rank(self, state: str) -> int:
        try:
            return self.conformance_order.index(state)
        except ValueError as exc:
            raise ValueError(f"unknown conformance state {state!r}") from exc

    def evaluate(self, subscores: Mapping[str, float], weakest_link_state: str) -> Verdict:
        """Score, quantize, then apply the weakest-link clamp.

        ``weakest_link_state`` is the strongest state the supplied proof chain can
        justify (e.g. ``UNVERIFIED`` if there is no CI evidence yet). The final
        state can never exceed it, regardless of the numeric score.
        """
        raw_rank = self._rank(weakest_link_state)  # validates the input state
        k = self.score(subscores)
        raw_state = self.quantize(k)
        if self._rank(raw_state) > raw_rank:
            return Verdict(k, raw_state, weakest_link_state, weakest_link_state, clamped=True)
        return Verdict(k, raw_state, weakest_link_state, raw_state, clamped=False)

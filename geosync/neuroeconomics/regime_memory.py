"""Online regime transition memory with Dirichlet-smoothed probabilities.

Maintains a 5×5 transition matrix P(regime_t+1 | regime_t) updated
with every new signal. Detects anomalous transitions via surprise score.

Neckpinch connection (Askar's arXiv paper):
  Rapid topology change in Ricci flow = anomalous transition.
  P matrix detects this as: P(METASTABLE→CRITICAL) >> historical base rate.

Trading application:
  - High surprise → uncertainty spike → reduce position
  - Pattern match: DECOHERENT→METASTABLE→COHERENT = entry setup
  - Pattern match: COHERENT→CRITICAL = exit immediately
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

_REGIMES = ("COHERENT", "METASTABLE", "DECOHERENT", "CRITICAL", "UNKNOWN")
_REGIME_INDEX: dict[str, int] = {r: i for i, r in enumerate(_REGIMES)}


@dataclass(frozen=True, slots=True)
class TransitionInfo:
    """Result of observing a regime transition."""

    previous: str
    current: str
    probability: float  # P(current | previous) from learned matrix
    surprise: float  # -log2 P(current | previous)
    pattern: str | None  # "ENTRY_SETUP" | "EXIT_NOW" | None


class RegimeMemory:
    """Online Bayesian transition matrix with Dirichlet prior.

    Parameters
    ----------
    prior_count
        Pseudo-counts for Dirichlet smoothing. Higher = more uniform prior.
    """

    def __init__(self, prior_count: float = 1.0) -> None:
        self._prior = prior_count
        # Per-instrument counts: counts[inst][from_idx][to_idx]
        self._counts: dict[str, list[list[float]]] = {}
        self._last_regime: dict[str, str] = {}
        self._history: dict[str, list[str]] = defaultdict(list)

    def _ensure_instrument(self, instrument: str) -> None:
        if instrument not in self._counts:
            n = len(_REGIMES)
            self._counts[instrument] = [[self._prior] * n for _ in range(n)]

    def observe(self, instrument: str, regime: str) -> TransitionInfo:
        """Register new regime observation. Returns transition info with surprise."""
        self._ensure_instrument(instrument)
        self._history[instrument].append(regime)

        prev = self._last_regime.get(instrument)
        self._last_regime[instrument] = regime

        if prev is None or prev not in _REGIME_INDEX:
            return TransitionInfo(
                previous="NONE",
                current=regime,
                probability=1.0,
                surprise=0.0,
                pattern=None,
            )

        from_idx = _REGIME_INDEX[prev]
        to_idx = _REGIME_INDEX.get(regime, _REGIME_INDEX["UNKNOWN"])

        # Update counts
        self._counts[instrument][from_idx][to_idx] += 1.0

        # Compute probability
        row = self._counts[instrument][from_idx]
        total = sum(row)
        prob = row[to_idx] / total if total > 0 else 0.0

        # Surprise = -log2(P)
        surprise = -math.log2(max(prob, 1e-12))

        # Pattern detection
        pattern = self._detect_pattern(instrument)

        return TransitionInfo(
            previous=prev,
            current=regime,
            probability=round(prob, 4),
            surprise=round(surprise, 4),
            pattern=pattern,
        )

    def get_transition_probability(
        self,
        instrument: str,
        from_regime: str,
        to_regime: str,
    ) -> float:
        """P(to_regime | from_regime) from learned matrix."""
        self._ensure_instrument(instrument)
        from_idx = _REGIME_INDEX.get(from_regime)
        to_idx = _REGIME_INDEX.get(to_regime)
        if from_idx is None or to_idx is None:
            return 0.0
        row = self._counts[instrument][from_idx]
        total = sum(row)
        return row[to_idx] / total if total > 0 else 0.0

    def get_expected_next(self, instrument: str) -> str:
        """Most likely next regime given current."""
        self._ensure_instrument(instrument)
        current = self._last_regime.get(instrument, "UNKNOWN")
        from_idx = _REGIME_INDEX.get(current, _REGIME_INDEX["UNKNOWN"])
        row = self._counts[instrument][from_idx]
        best_idx = max(range(len(row)), key=lambda i: row[i])
        return _REGIMES[best_idx]

    def _detect_pattern(self, instrument: str) -> str | None:
        """Detect known regime sequences."""
        hist = self._history[instrument]

        # Exit signal: coherent → critical (2-step pattern, check first)
        if len(hist) >= 2 and hist[-2] == "COHERENT" and hist[-1] == "CRITICAL":
            return "EXIT_NOW"

        if len(hist) < 3:
            return None

        # Entry setup: desync → metastable → coherent (3-step pattern)
        if hist[-3] == "DECOHERENT" and hist[-2] == "METASTABLE" and hist[-1] == "COHERENT":
            return "ENTRY_SETUP"

        return None

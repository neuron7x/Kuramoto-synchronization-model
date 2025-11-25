"""Early Warning System aggregator for TradePulse Neuro-Architecture.

This module implements the EWS logic that aggregates sensor outputs
to determine market regime state: KILL, EMERGENT, or CAUTION.
"""

from __future__ import annotations

import os
from typing import Literal

import numpy as np

__all__ = ["EWSAggregator", "EWSConfig", "EWSResult"]


class EWSConfig:
    """Configuration for EWS aggregator.

    Parameters
    ----------
    dr_threshold : float, optional
        Threshold for ΔR decline indicating stress, by default 0.1
    topo_threshold : float, optional
        Threshold for topological anomaly, by default 0.15
    ricci_kill_threshold : float, optional
        Ricci curvature below this triggers KILL, by default -0.3
    """

    def __init__(
        self,
        dr_threshold: float | None = None,
        topo_threshold: float | None = None,
        ricci_kill_threshold: float = -0.3,
    ):
        # Load from environment or use defaults
        self.dr_threshold = (
            float(os.getenv("TP_EWS_DR_THRESHOLD", "0.1"))
            if dr_threshold is None
            else dr_threshold
        )
        self.topo_threshold = (
            float(os.getenv("TP_EWS_TOPO_THRESHOLD", "0.15"))
            if topo_threshold is None
            else topo_threshold
        )
        self.ricci_kill_threshold = ricci_kill_threshold


class EWSResult:
    """Result from EWS aggregation.

    Attributes
    ----------
    state : Literal["KILL", "EMERGENT", "CAUTION"]
        Current regime state
    confidence : float
        Confidence in the state (0-1)
    """

    def __init__(
        self,
        state: Literal["KILL", "EMERGENT", "CAUTION"],
        confidence: float,
    ):
        self.state = state
        self.confidence = confidence


class EWSAggregator:
    """Aggregates early warning signals into regime states.

    Implements the logic:
    - KILL: (ΔR < -τ AND κ_min < 0) OR topo > τ OR !TE_pass
    - EMERGENT: R high AND κ_min > 0 AND TE_pass
    - CAUTION: Otherwise

    Parameters
    ----------
    config : EWSConfig, optional
        Configuration for thresholds
    """

    def __init__(self, config: EWSConfig | None = None):
        self.config = config or EWSConfig()

    def decide(
        self,
        R: float,
        dR: float,
        kappa_min: float,
        topo_score: float,
        te_pass: bool,
    ) -> tuple[Literal["KILL", "EMERGENT", "CAUTION"], float]:
        """Determine regime state and confidence.

        Parameters
        ----------
        R : float
            Kuramoto order parameter (synchrony)
        dR : float
            Change in order parameter
        kappa_min : float
            Minimum Ricci curvature
        topo_score : float
            Topological anomaly score
        te_pass : bool
            Whether causal test passed

        Returns
        -------
        tuple[Literal["KILL", "EMERGENT", "CAUTION"], float]
            State and confidence (0-1)
        """
        # KILL conditions (high priority)
        kill_conditions = []

        # Condition 1: Sharp synchrony drop AND negative curvature
        if dR < -self.config.dr_threshold and kappa_min < 0:
            kill_conditions.append(("dR_kappa", 0.9))

        # Condition 2: Extreme negative curvature
        if kappa_min < self.config.ricci_kill_threshold:
            kill_conditions.append(("kappa_extreme", 0.95))

        # Condition 3: High topological anomaly
        if topo_score > self.config.topo_threshold:
            kill_conditions.append(("topo_anomaly", 0.8))

        # Condition 4: Failed causality test
        if not te_pass:
            kill_conditions.append(("no_causality", 0.7))

        # If any KILL condition triggered, return KILL
        if kill_conditions:
            # Use maximum confidence from triggered conditions
            max_confidence = max(conf for _, conf in kill_conditions)
            return "KILL", max_confidence

        # EMERGENT conditions (strong positive signals)
        emergent_score = 0.0
        n_checks = 0

        # High synchrony
        if R > 0.7:
            emergent_score += R
            n_checks += 1

        # Positive curvature (stable network)
        if kappa_min > 0:
            emergent_score += min(kappa_min, 0.5) * 2  # Scale to 0-1
            n_checks += 1

        # Causal structure intact
        if te_pass:
            emergent_score += 0.8
            n_checks += 1

        # Low topological anomaly
        if topo_score < 0.05:
            emergent_score += 0.7
            n_checks += 1

        # Stable or increasing synchrony
        if dR >= 0:
            emergent_score += 0.6
            n_checks += 1

        # If most emergent conditions met, return EMERGENT
        if n_checks > 0:
            avg_score = emergent_score / n_checks
            # Require strong average score AND at least 3 conditions met
            if avg_score > 0.7 and n_checks >= 3:
                return "EMERGENT", avg_score

        # Otherwise, CAUTION (default state)
        # Compute confidence based on distance from boundaries
        caution_confidence = self._compute_caution_confidence(
            R, dR, kappa_min, topo_score, te_pass
        )

        return "CAUTION", caution_confidence

    def _compute_caution_confidence(
        self,
        R: float,
        dR: float,
        kappa_min: float,
        topo_score: float,
        te_pass: bool,
    ) -> float:
        """Compute confidence for CAUTION state.

        Based on how far we are from KILL/EMERGENT boundaries.
        """
        # Start with moderate confidence
        confidence = 0.6

        # Increase confidence if clearly away from kill conditions
        if dR > -self.config.dr_threshold / 2:
            confidence += 0.1

        if kappa_min > self.config.ricci_kill_threshold * 0.5:
            confidence += 0.1

        if topo_score < self.config.topo_threshold * 0.5:
            confidence += 0.1

        if te_pass:
            confidence += 0.1

        # Clip to valid range
        confidence = float(np.clip(confidence, 0.3, 0.9))

        return confidence

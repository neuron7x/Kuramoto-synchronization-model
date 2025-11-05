"""Basal Ganglia policy module for Go/No-Go trading decisions.

This module implements action selection logic inspired by the basal ganglia's
role in action gating, combining EWS regime state with risk assessment to
make trading decisions.
"""

from __future__ import annotations

from typing import Literal

__all__ = ["BasalGangliaPolicy", "PolicyResult"]


class PolicyResult:
    """Result from policy decision.

    Attributes
    ----------
    action : Literal["GO", "NO_GO", "HOLD"]
        Trading action decision
    size_hint : float
        Suggested position size (0-1), to be scaled by Kelly fraction
    """

    def __init__(
        self,
        action: Literal["GO", "NO_GO", "HOLD"],
        size_hint: float,
    ):
        self.action = action
        self.size_hint = size_hint


class BasalGangliaPolicy:
    """Basal ganglia-inspired action selection policy.

    Implements the decision logic:
    - KILL or BREACH → NO_GO (size=0)
    - EMERGENT + OK → GO (size_hint = 0.5 + 0.5*R)
    - Otherwise → HOLD (size_hint = 0.2)

    This mimics the basal ganglia's role in action gating, where
    the direct pathway facilitates actions (GO) and the indirect
    pathway inhibits them (NO_GO).

    Parameters
    ----------
    hold_size_hint : float, optional
        Default size hint for HOLD state, by default 0.2
    """

    def __init__(self, hold_size_hint: float = 0.2):
        self.hold_size_hint = hold_size_hint

    def decide(
        self,
        state: dict,
        ews_state: Literal["KILL", "EMERGENT", "CAUTION"],
        risk_state: Literal["OK", "BREACH"],
    ) -> tuple[Literal["GO", "NO_GO", "HOLD"], float]:
        """Make Go/No-Go decision based on EWS and risk states.

        Parameters
        ----------
        state : dict
            Market state features, must contain 'R' (Kuramoto order parameter)
        ews_state : Literal["KILL", "EMERGENT", "CAUTION"]
            Early warning system state
        risk_state : Literal["OK", "BREACH"]
            Risk assessment state (BREACH if ES exceeds limit)

        Returns
        -------
        tuple[Literal["GO", "NO_GO", "HOLD"], float]
            Action decision and size hint (0-1)
        """
        # NO_GO conditions (inhibitory pathway)
        if ews_state == "KILL" or risk_state == "BREACH":
            return "NO_GO", 0.0

        # GO conditions (direct pathway)
        if ews_state == "EMERGENT" and risk_state == "OK":
            # Size hint scales with synchrony (R)
            R = state.get("R", 0.5)
            size_hint = 0.5 + 0.5 * R
            # Clip to valid range
            size_hint = max(0.0, min(1.0, size_hint))
            return "GO", size_hint

        # Default: HOLD (cautious state)
        return "HOLD", self.hold_size_hint

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from types import MappingProxyType
from typing import Mapping

__all__ = [
    "HyperdirectVetoError",
    "HyperdirectConfig",
    "VetoDecision",
    "HyperdirectVeto",
]


class HyperdirectVetoError(RuntimeError):
    """Raised when the veto contract or its inputs are violated.

    Fail-closed boundary: an unreadable or out-of-contract input is never
    silently coerced into a PASS.
    """


@dataclass(frozen=True)
class HyperdirectConfig:
    """Parameters of the cortico-subthalamic STOP analogue.

    Neuro origin: the cortico-basal-ganglia *hyperdirect* pathway. The
    anterior cingulate cortex monitors response conflict; under high
    conflict the cortex drives the subthalamic nucleus, which (a) applies
    a fast global STOP and (b) *raises the decision threshold in
    proportion to conflict* (Frank 2006; Cavanagh & Frank 2011).

    Two parameters, one for each faithful behaviour:

    * ``hard_ceiling`` — the single-channel STOP. Any one residual
      conflict channel at or above this aborts promotion regardless of
      how strong the evidence is (disjunctive ``max`` veto, never a
      mean — one saturated red flag is not allowed to be averaged away).
    * ``base_margin`` / ``conflict_gain`` — the conflict-proportional
      decision threshold. The evidence margin a claim must clear is
      ``base_margin + conflict_gain * mean(conflict)``. This is
      deterministic in the conflict it is given; it is NOT seeded noise.
    """

    hard_ceiling: float = 0.8
    base_margin: float = 0.0
    conflict_gain: float = 1.0


@dataclass(frozen=True)
class VetoDecision:
    """Terminal, immutable outcome. There is no third state."""

    passed: bool
    reason: str
    c_max: float
    c_aggregate: float
    required_margin: float
    evidence_margin: float
    vetoing_channel: str | None
    conflict_vector: Mapping[str, float]


class HyperdirectVeto:
    """Disjunctive, conflict-proportional pre-promotion brake.

    Stateless and pure: same inputs always produce the same
    :class:`VetoDecision`. No clock, no RNG, no I/O, no global state — the
    strongest possible reproducibility contract.

    Caller contract (HDV-007): ``conflict`` must contain **only residual
    channels** — signals that are not already hard-gated upstream. Passing
    channels that another gate has already vetoed on does not make this
    brake stronger; it only re-encodes a decision already taken. Keeping
    the channel set residual is what makes every channel here load-bearing.

    Enumerated invariants:

    * HDV-001  Decision is binary: ``passed`` is exactly the conjunction
      of "no single-channel STOP" and "evidence margin clears the
      conflict-proportional threshold".
    * HDV-002  Single-channel STOP uses ``max`` over channels, never a
      mean or sum: one channel ``>= hard_ceiling`` vetoes.
    * HDV-003  The required margin rises monotonically with aggregate
      conflict and is a pure function of the supplied conflict — never
      randomised.
    * HDV-004  Every conflict channel value is a finite real in
      ``[0, 1]``; any other value fail-closes (no clamping, no skipping).
    * HDV-005  ``evidence_margin`` is a finite real; a negative margin
      (null beat the hypothesis) can never PASS a non-negative threshold.
    * HDV-006  An empty conflict mapping is a valid "no residual
      conflict" state; the base margin must still be cleared.
    * HDV-007  Channels are residual-only by caller contract (documented,
      not enforceable here — enforcing it would require the upstream gate
      set this primitive is deliberately decoupled from).
    * HDV-008  ``VetoDecision`` and its ``conflict_vector`` are immutable.

    What a PASS does and does not mean: a PASS asserts only that, under
    the caller-supplied conflict and margin, no STOP fired and the
    evidence cleared the conflict-scaled bar. It does NOT assert that the
    margin or the channel scores correspond to reality — that obligation
    lives upstream, with whatever computed them.
    """

    def __init__(self, config: HyperdirectConfig | None = None) -> None:
        self._config = config or HyperdirectConfig()
        self._validate_config(self._config)

    @property
    def config(self) -> HyperdirectConfig:
        return self._config

    def evaluate(
        self,
        conflict: Mapping[str, float],
        evidence_margin: float,
    ) -> VetoDecision:
        """Return the terminal :class:`VetoDecision` for one promotion."""

        if not isinstance(conflict, Mapping):
            raise HyperdirectVetoError(
                "veto denied: conflict must be a mapping of residual channels"
            )
        try:
            channel_pairs = tuple(conflict.items())
        except Exception as exc:
            raise HyperdirectVetoError("veto denied: conflict mapping could not be read") from exc

        validated: dict[str, float] = {}
        for name, value in channel_pairs:
            if not isinstance(name, str) or not name:
                raise HyperdirectVetoError(
                    "veto denied: conflict channel names must be non-empty strings"
                )
            channel = self._require_finite_real(
                value,
                message=f"veto denied: channel {name!r} must be a finite real number",
            )
            if not (0.0 <= channel <= 1.0):
                raise HyperdirectVetoError(f"veto denied: channel {name!r} must lie in [0, 1]")
            validated[name] = channel

        margin = self._require_finite_real(
            evidence_margin,
            message="veto denied: evidence_margin must be a finite real number",
        )

        frozen_vector = MappingProxyType(dict(validated))

        if validated:
            vetoing_channel = max(validated, key=lambda k: validated[k])
            c_max = validated[vetoing_channel]
            c_aggregate = sum(validated.values()) / len(validated)
        else:
            vetoing_channel = None
            c_max = 0.0
            c_aggregate = 0.0

        required_margin = self._config.base_margin + self._config.conflict_gain * c_aggregate

        # HDV-002: disjunctive single-channel STOP takes precedence.
        if c_max >= self._config.hard_ceiling:
            return VetoDecision(
                passed=False,
                reason=f"single_channel_stop:{vetoing_channel}",
                c_max=c_max,
                c_aggregate=c_aggregate,
                required_margin=required_margin,
                evidence_margin=margin,
                vetoing_channel=vetoing_channel,
                conflict_vector=frozen_vector,
            )

        # HDV-003: conflict-proportional decision threshold.
        if margin < required_margin:
            return VetoDecision(
                passed=False,
                reason="insufficient_margin_under_conflict",
                c_max=c_max,
                c_aggregate=c_aggregate,
                required_margin=required_margin,
                evidence_margin=margin,
                vetoing_channel=None,
                conflict_vector=frozen_vector,
            )

        return VetoDecision(
            passed=True,
            reason="cleared",
            c_max=c_max,
            c_aggregate=c_aggregate,
            required_margin=required_margin,
            evidence_margin=margin,
            vetoing_channel=None,
            conflict_vector=frozen_vector,
        )

    @staticmethod
    def _require_finite_real(value: object, *, message: str) -> float:
        if isinstance(value, bool) or not isinstance(value, Real):
            raise HyperdirectVetoError(message)
        try:
            if not isfinite(value):  # type: ignore[arg-type]
                raise HyperdirectVetoError(message)
        except (TypeError, ValueError) as exc:
            raise HyperdirectVetoError(message) from exc
        return float(value)

    @staticmethod
    def _validate_config(config: HyperdirectConfig) -> None:
        if not (0.0 < config.hard_ceiling <= 1.0):
            raise ValueError("hard_ceiling must be in (0, 1]")
        if config.base_margin < 0.0 or not isfinite(config.base_margin):
            raise ValueError("base_margin must be a finite value >= 0")
        if config.conflict_gain < 0.0 or not isfinite(config.conflict_gain):
            raise ValueError("conflict_gain must be a finite value >= 0")

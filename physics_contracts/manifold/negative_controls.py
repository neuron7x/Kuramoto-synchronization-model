# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Unified physics negative-control battery → one fail-closed ``ComparisonReport``.

This adapter folds the four canonical null controls that already exist in
``core.kuramoto.falsification`` —

1. time-shuffle (``time_shuffle_test``),
2. IAAFT amplitude-adjusted surrogate (``iaaft_surrogate_test``),
3. degree-preserving rewire (``degree_preserving_rewire``),
4. causal-cutoff violation,

— into a single :class:`~physics_contracts.manifold.contracts.ComparisonReport`.
A physical descriptor "survives" only if its candidate statistic strictly beats
*every* control's null band. Two fail-closed disciplines are enforced:

* **Null failure downgrades the claim.** If any control is not beaten, the
  status can never be ``SURVIVED_NULLS``.
* **Synthetic data can never produce a real-data claim.** When the dataset
  fingerprint is missing / zero-hash / synthetic-tagged, the strongest status
  is ``ARTIFACT_SUSPECTED`` even if every control is beaten.

``n_null_draws`` is configurable and recorded so the statistical power behind
the verdict is auditable; a battery below the adequacy floor is rejected.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import numpy as np
from numpy.typing import NDArray

from core.kuramoto.falsification import SurrogateResult
from physics_contracts.manifold.contracts import (
    ComparisonReport,
    LicensedDataStatus,
    NullControl,
    canonical_digest,
    resolve_data_status,
)

__all__ = [
    "REQUIRED_CONTROLS",
    "PhysicsNegativeControlReport",
    "summarize_surrogate",
    "assemble_comparison_report",
]

# The four controls every physics descriptor must face (architecture doc §2 P5).
REQUIRED_CONTROLS: Final[tuple[str, ...]] = (
    "time_shuffle",
    "iaaft_surrogate",
    "degree_preserving_rewire",
    "causal_cutoff_violation",
)

# Statistical-adequacy floor for the null ensemble, mirroring
# instrument_validation.null_audit (_MIN_NULL_DRAWS). A battery with fewer draws
# cannot support a survival claim and is rejected fail-closed.
_MIN_NULL_DRAWS: Final[int] = 200


@dataclass(frozen=True, slots=True)
class PhysicsNegativeControlReport:
    """A :class:`ComparisonReport` plus the audit trail the battery recorded."""

    comparison: ComparisonReport
    n_null_draws: int
    data_status: LicensedDataStatus
    survived_all_controls: bool

    @property
    def report_digest(self) -> str:
        return canonical_digest(
            {
                "comparison": self.comparison.report_digest,
                "n_null_draws": self.n_null_draws,
                "data_status": self.data_status.value,
                "survived_all_controls": self.survived_all_controls,
            }
        )


def summarize_surrogate(result: SurrogateResult, *, quantile: float = 0.95) -> float:
    """Reduce a ``falsification.SurrogateResult`` to one null-band statistic.

    The control statistic is the upper ``quantile`` of the null distribution:
    the candidate must exceed this band to count as beating the control. This is
    the bridge from the existing surrogate engine to a :class:`NullControl`.
    """

    if not (0.0 < quantile < 1.0):
        raise ValueError(f"summarize_surrogate: quantile {quantile} must be in (0, 1)")
    null: NDArray[np.float64] = np.asarray(result.null_distribution, dtype=np.float64)
    if null.size == 0:
        raise ValueError("summarize_surrogate: empty null distribution (no draws to summarise)")
    return float(np.quantile(null, quantile))


def assemble_comparison_report(
    *,
    candidate_statistic: float,
    control_statistics: dict[str, float],
    n_null_draws: int,
    validity_domain: str,
    dataset_fingerprint: str | None,
) -> PhysicsNegativeControlReport:
    """Fold the four control statistics into one fail-closed comparison report.

    ``control_statistics`` must contain exactly the four :data:`REQUIRED_CONTROLS`
    keys (a missing control is itself a falsifier). The candidate "survives" only
    if it strictly beats every control's null band; synthetic / unavailable data
    caps the strongest attainable status at ``ARTIFACT_SUSPECTED``.
    """

    missing = [name for name in REQUIRED_CONTROLS if name not in control_statistics]
    if missing:
        raise ValueError(
            "ComparisonReport VIOLATED: negative-control battery is missing required controls "
            f"{missing}; all of {list(REQUIRED_CONTROLS)} must be present"
        )
    extra = [name for name in control_statistics if name not in REQUIRED_CONTROLS]
    if extra:
        raise ValueError(
            f"ComparisonReport VIOLATED: unknown negative controls {extra}; "
            f"only {list(REQUIRED_CONTROLS)} are admitted"
        )
    if n_null_draws < _MIN_NULL_DRAWS:
        raise ValueError(
            "ComparisonReport VIOLATED: n_null_draws "
            f"{n_null_draws} below the statistical-adequacy floor {_MIN_NULL_DRAWS}; "
            "a survival claim needs an adequate null ensemble"
        )

    null_controls = tuple(
        NullControl(name=name, statistic=control_statistics[name]) for name in REQUIRED_CONTROLS
    )
    survived = all(candidate_statistic > nc.statistic for nc in null_controls)
    data_status = resolve_data_status(dataset_fingerprint)

    # Fail-closed claim assignment:
    #   * a null failure can never yield SURVIVED_NULLS;
    #   * synthetic / unavailable data can never yield a real-data survival claim.
    if survived and data_status is LicensedDataStatus.AVAILABLE:
        claim_status = "SURVIVED_NULLS"
    elif survived:
        # Survived on synthetic data — honest downgrade, not a real-data claim.
        claim_status = "ARTIFACT_SUSPECTED"
    else:
        claim_status = "ARTIFACT_SUSPECTED"

    comparison = ComparisonReport(
        candidate_statistic=candidate_statistic,
        null_controls=null_controls,
        claim_status=claim_status,
        validity_domain=validity_domain,
    )
    return PhysicsNegativeControlReport(
        comparison=comparison,
        n_null_draws=n_null_draws,
        data_status=data_status,
        survived_all_controls=survived,
    )

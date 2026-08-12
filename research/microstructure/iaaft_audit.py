"""Fail-closed positive-control audit for the L2 Ricci IAAFT linear-spectral null.

PR #1240 wired the IAAFT surrogate null (Schreiber & Schmitz 1996) into
``run_killtest`` as an **advisory** report only. The code comment there states
the precondition for ever promoting it to a *gating* null:

    "promotion to a gating null requires the separate fail-closed
     positive-control audit (does it still recover a known edge?)."

This module is that audit. A null test is only fit to gate a binary verdict if
its operating characteristics as a decision rule (reject H0 iff ``p < alpha``)
are known and acceptable. We measure two of them, by running the *deployed*
``killtest._iaaft_pvalue`` (not a reimplementation) over many independent
synthetic replications:

* **Power (sensitivity)** — on a positive control where the signal predicts the
  target through a temporal alignment that IAAFT phase-randomisation destroys,
  the null must reject (``p < alpha``) reliably.  ``power`` = fraction rejected.
* **False-positive rate (specificity / calibration)** — on a negative control
  where an autocorrelated signal is *independent* of the target, the null must
  not reject more than the nominal level.  ``fpr`` = fraction rejected; for a
  calibrated null ``fpr ≈ alpha``.

Both controls preserve the strongly-autocorrelated regime (random walk) that an
IAAFT null is specifically meant to keep intact while destroying genuine
target alignment — i.e. the regime of the real cross-sectional Ricci signal.

Eligibility is **fail-closed**: the IAAFT null earns gating status only if
``power >= power_floor`` AND ``fpr <= fpr_ceiling`` AND enough replications ran
with finite results. Any degeneracy → ``eligible = False`` with a recorded
reason. The audit never mutates a published verdict; it only emits the evidence
that ``killtest`` consults via :func:`iaaft_is_gating_eligible`.

Determinism contract (INV-HPC1): same config → bit-identical verdict. Every
replication draws from a generator seeded as ``base_seed + replication_index``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from research.microstructure.killtest import SEED, _iaaft_pvalue, _pooled_ic

# Canonical audit configuration. These defaults define the *frozen* operating
# point at which the deployed null's power and FPR are certified. Changing them
# invalidates a previously committed verdict artifact (a new audit must run).
_DEFAULT_ALPHA: float = 0.05
_DEFAULT_POWER_FLOOR: float = 0.80
# nominal alpha plus a Monte-Carlo slack band: an exactly-calibrated null has
# FPR == alpha, but a finite replication count scatters the estimate. The slack
# keeps the audit from failing a correctly-calibrated null on sampling noise,
# while still rejecting a null that over-fires (FPR >> alpha).
_DEFAULT_FPR_CEILING: float = 0.10
_DEFAULT_REPLICATIONS: int = 40
_MIN_REPLICATIONS: int = 10
_DEFAULT_N_ROWS: int = 1_000
_DEFAULT_N_SYMBOLS: int = 5
_DEFAULT_TRIALS: int = 100
_DEFAULT_ITERS: int = 60
# positive-control edge strength: target = signal + noise_scale * N(0,1). Small
# enough to be a non-trivial detection problem, large enough that a powered null
# should recover it.
_DEFAULT_EDGE_NOISE: float = 0.5

# Schema version for the verdict artifact. Bump only on an incompatible change
# to the certified contract (fields removed / semantics changed).
AUDIT_SCHEMA_VERSION: int = 1


@dataclass(frozen=True)
class GatingAuditConfig:
    """Frozen knobs that define the operating point being certified."""

    alpha: float = _DEFAULT_ALPHA
    power_floor: float = _DEFAULT_POWER_FLOOR
    fpr_ceiling: float = _DEFAULT_FPR_CEILING
    n_replications: int = _DEFAULT_REPLICATIONS
    n_rows: int = _DEFAULT_N_ROWS
    n_symbols: int = _DEFAULT_N_SYMBOLS
    trials: int = _DEFAULT_TRIALS
    iters: int = _DEFAULT_ITERS
    edge_noise: float = _DEFAULT_EDGE_NOISE
    base_seed: int = SEED


@dataclass
class GatingAuditVerdict:
    """Operating characteristics of the IAAFT null and the gating decision."""

    eligible: bool
    reasons: list[str]
    power: float
    fpr: float
    alpha: float
    power_floor: float
    fpr_ceiling: float
    n_replications: int
    n_finite_positive: int
    n_finite_negative: int
    positive_pvalues: list[float]
    negative_pvalues: list[float]
    schema_version: int = AUDIT_SCHEMA_VERSION
    metadata: dict[str, Any] = field(default_factory=dict)


def _autocorrelated_walk(n: int, rng: np.random.Generator) -> NDArray[np.float64]:
    """Strongly autocorrelated 1-D series (random walk).

    This is the regime an IAAFT null must preserve while destroying any genuine
    row-wise alignment with the target — i.e. the regime of the real Ricci
    cross-sectional signal.
    """
    return np.asarray(rng.normal(0.0, 1.0, size=n).cumsum(), dtype=np.float64)


def _positive_control_pvalue(config: GatingAuditConfig, rng: np.random.Generator) -> float:
    """One positive-control replication → IAAFT p-value of a *genuine* edge.

    The target is a monotone-aligned, noisy copy of the signal, so the real
    predictive IC is driven by row-wise temporal alignment. IAAFT phase
    randomisation destroys that alignment while preserving the signal's power
    spectrum and amplitudes, so a powered null returns a small p.
    """
    signal = _autocorrelated_walk(config.n_rows, rng)
    noise = rng.normal(0.0, config.edge_noise, size=config.n_rows)
    target_1d = signal + noise
    target_panel = np.repeat(target_1d[:, None], config.n_symbols, axis=1)
    signal_panel = np.repeat(signal[:, None], config.n_symbols, axis=1)
    observed = _pooled_ic(signal_panel, target_panel)
    return _iaaft_pvalue(
        signal,
        target_panel,
        observed,
        config.n_symbols,
        trials=config.trials,
        iters=config.iters,
        seed=int(rng.integers(1, 2**31 - 1)),
    )


def _negative_control_pvalue(config: GatingAuditConfig, rng: np.random.Generator) -> float:
    """One negative-control replication → IAAFT p-value when signal ⟂ target.

    Signal and target are independent autocorrelated walks; any observed IC is a
    finite-sample coincidence. A calibrated null returns p ~ Uniform(0,1), so the
    rejection rate over replications estimates the false-positive rate.
    """
    signal = _autocorrelated_walk(config.n_rows, rng)
    target_1d = _autocorrelated_walk(config.n_rows, rng)
    target_panel = np.repeat(target_1d[:, None], config.n_symbols, axis=1)
    signal_panel = np.repeat(signal[:, None], config.n_symbols, axis=1)
    observed = _pooled_ic(signal_panel, target_panel)
    return _iaaft_pvalue(
        signal,
        target_panel,
        observed,
        config.n_symbols,
        trials=config.trials,
        iters=config.iters,
        seed=int(rng.integers(1, 2**31 - 1)),
    )


def run_iaaft_gating_audit(config: GatingAuditConfig | None = None) -> GatingAuditVerdict:
    """Run the positive/negative control battery and emit a gating verdict.

    Deterministic: replication ``i`` draws from ``default_rng(base_seed + i)``,
    independently for each control arm, so the verdict is bit-identical across
    runs with the same config.
    """
    cfg = config or GatingAuditConfig()

    pos_p: list[float] = []
    neg_p: list[float] = []
    for i in range(cfg.n_replications):
        pos_p.append(_positive_control_pvalue(cfg, np.random.default_rng(cfg.base_seed + i)))
        neg_p.append(
            _negative_control_pvalue(cfg, np.random.default_rng(cfg.base_seed + 10_000 + i))
        )

    pos_finite = [p for p in pos_p if np.isfinite(p)]
    neg_finite = [p for p in neg_p if np.isfinite(p)]

    reasons: list[str] = []

    if cfg.n_replications < _MIN_REPLICATIONS:
        reasons.append(
            f"n_replications={cfg.n_replications} < minimum {_MIN_REPLICATIONS} for a "
            "stable operating-characteristic estimate"
        )

    if not pos_finite or not neg_finite:
        # Fail-closed: cannot certify an instrument whose controls degenerated.
        reasons.append(
            f"degenerate controls: {len(pos_finite)} finite positive / "
            f"{len(neg_finite)} finite negative p-values"
        )
        power = float("nan")
        fpr = float("nan")
    else:
        power = float(np.mean([1.0 if p < cfg.alpha else 0.0 for p in pos_finite]))
        fpr = float(np.mean([1.0 if p < cfg.alpha else 0.0 for p in neg_finite]))
        if not np.isfinite(power) or power < cfg.power_floor:
            reasons.append(f"power={power:.3f} < floor={cfg.power_floor:.3f} (null blind to edges)")
        if not np.isfinite(fpr) or fpr > cfg.fpr_ceiling:
            reasons.append(f"fpr={fpr:.3f} > ceiling={cfg.fpr_ceiling:.3f} (null over-fires)")

    eligible = not reasons

    return GatingAuditVerdict(
        eligible=eligible,
        reasons=reasons,
        power=power if np.isfinite(power) else float("nan"),
        fpr=fpr if np.isfinite(fpr) else float("nan"),
        alpha=cfg.alpha,
        power_floor=cfg.power_floor,
        fpr_ceiling=cfg.fpr_ceiling,
        n_replications=cfg.n_replications,
        n_finite_positive=len(pos_finite),
        n_finite_negative=len(neg_finite),
        positive_pvalues=[float(p) for p in pos_p],
        negative_pvalues=[float(p) for p in neg_p],
        metadata={
            "null": "iaaft_linear_spectral",
            "reference": "Schreiber & Schmitz 1996, Phys. Rev. Lett. 77:635",
            "instrument": "research.microstructure.killtest._iaaft_pvalue",
            "n_rows": cfg.n_rows,
            "n_symbols": cfg.n_symbols,
            "trials": cfg.trials,
            "iters": cfg.iters,
            "edge_noise": cfg.edge_noise,
            "base_seed": cfg.base_seed,
        },
    )


def verdict_to_json(verdict: GatingAuditVerdict) -> str:
    """Stable, sorted JSON serialisation of a gating-audit verdict."""
    return json.dumps(asdict(verdict), indent=2, sort_keys=True)


def iaaft_is_gating_eligible(verdict_path: Path | str) -> bool:
    """Read a frozen audit artifact and return whether IAAFT may gate.

    Fail-closed: a missing, unreadable, malformed, schema-mismatched, or
    ``eligible=False`` artifact all return ``False``. ``killtest`` consults this
    so that promotion of the IAAFT null to a gating role is backed by a
    committed, reproducible audit rather than asserted in code.
    """
    path = Path(verdict_path)
    try:
        payload = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != AUDIT_SCHEMA_VERSION:
        return False
    return payload.get("eligible") is True

# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""BankLevelGate5Audit — allocator-side Gate-5-style recovery audit.

Per X-10R-1 PR #3 (epic #638), the allocator's positive controls
need a multi-metric recovery report — not just a single relative-L1
scalar. The X-10R reconstruction pipeline (PR #635) uses a
Gate-5 audit with four thresholds (spectral radius, top-k hub
jaccard, row/col L1) so a *partial* failure (one metric clipping
its threshold) is observable without losing the others.

This module brings the same discipline to the allocator side, but
adapted to the marginals domain (no spectral radius — the allocator
emits 1-D marginals, not a square coupling matrix):

    BankLevelRecoveryReport
        * total_relative_l1                    — Σ |gt - alloc| / Σ |gt|
        * top_k_bank_jaccard                   — top-k by strength
        * per_country_relative_l1_max          — worst-country L1
        * conservation_total_relative_error    — |Σgt - Σalloc| / Σgt
        * passed: bool — every threshold ≤ its bound

Default thresholds:
        total_relative_l1                    ≤ 0.20
        top_k_bank_jaccard (k = N//5)        ≥ 0.60
        per_country_relative_l1_max          ≤ 0.05
        conservation_total_relative_error    ≤ 1e-9

Rationale for k = N//5:
    The X-10R reconstruction uses k = N//10 because the network has
    N nodes and the systemic-hub set is sparse. The allocator emits
    N total bank-level marginals (where N = #banks ≪ #network edges)
    and the systemic-importance ranking is much sharper at the
    bank-level. k = N//5 keeps the test discriminating without
    over-fitting to the substrate.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Default thresholds — can be overridden in the audit call.
TOTAL_RELATIVE_L1_MAX_DEFAULT: float = 0.20
TOP_K_BANK_JACCARD_MIN_DEFAULT: float = 0.60
PER_COUNTRY_RELATIVE_L1_MAX_DEFAULT: float = 0.05
CONSERVATION_TOTAL_RELATIVE_ERROR_MAX_DEFAULT: float = 1e-9


@dataclass(frozen=True)
class BankLevelRecoveryReport:
    """Frozen Gate-5-style recovery report on bank-level marginals.

    Each metric is reported AND each threshold is checked; ``passed``
    is the conjunction. ``failure_reasons`` is a tuple of human-
    readable strings for the metrics that crossed their bound (if
    any) — the same shape the X-10R reconstruction's RecoveryReport
    uses.
    """

    total_relative_l1: float
    top_k_bank_jaccard: float
    per_country_relative_l1_max: float
    per_country_relative_l1_argmax: str  # which country was worst
    conservation_total_relative_error: float
    n_banks: int
    n_countries: int
    k_top: int
    passed: bool
    failure_reasons: tuple[str, ...]


def _top_k_jaccard(deg_true: np.ndarray, deg_recon: np.ndarray, *, k: int) -> float:
    """Strength-based top-k jaccard. Same shape as the X-10R version."""
    if k <= 0:
        return 0.0
    top_t = set(np.argsort(-deg_true)[:k].tolist())
    top_r = set(np.argsort(-deg_recon)[:k].tolist())
    union = top_t | top_r
    if not union:
        return 0.0
    return float(len(top_t & top_r) / len(union))


def audit_bank_level_recovery(
    *,
    ground_truth_s_in: np.ndarray,
    ground_truth_s_out: np.ndarray,
    allocated_s_in: np.ndarray,
    allocated_s_out: np.ndarray,
    bank_country_map: tuple[tuple[str, str], ...],
    k_top: int | None = None,
    total_relative_l1_max: float = TOTAL_RELATIVE_L1_MAX_DEFAULT,
    top_k_bank_jaccard_min: float = TOP_K_BANK_JACCARD_MIN_DEFAULT,
    per_country_relative_l1_max: float = PER_COUNTRY_RELATIVE_L1_MAX_DEFAULT,
    conservation_total_relative_error_max: float = (CONSERVATION_TOTAL_RELATIVE_ERROR_MAX_DEFAULT),
) -> BankLevelRecoveryReport:
    """Audit the allocator's bank-level marginal recovery.

    The four metrics together pin a substantive recovery contract:
      * total_relative_l1        — coarse aggregate match
      * top_k_bank_jaccard       — systemic-hub identification (the
                                    metric the downstream X-10R Gate 6
                                    inherits via spectral leading EV)
      * per_country_relative_l1_max — local distortion: a prior that
                                    matches in aggregate but is wildly
                                    wrong inside one country fails here
      * conservation_total_relative_error — bookkeeping: total mass
                                    must match to numerical tolerance
                                    (otherwise the allocator broke
                                    GATE_A1 conservation upstream)
    """
    gt_in = np.asarray(ground_truth_s_in, dtype=np.float64).ravel()
    gt_out = np.asarray(ground_truth_s_out, dtype=np.float64).ravel()
    al_in = np.asarray(allocated_s_in, dtype=np.float64).ravel()
    al_out = np.asarray(allocated_s_out, dtype=np.float64).ravel()
    n = gt_in.shape[0]
    if gt_out.shape != (n,) or al_in.shape != (n,) or al_out.shape != (n,):
        raise ValueError(
            "all four marginal vectors must share the same shape "
            f"(n,) where n = ground_truth_s_in.shape[0]={n}; got "
            f"gt_out={gt_out.shape}, al_in={al_in.shape}, al_out={al_out.shape}"
        )
    if len(bank_country_map) != n:
        raise ValueError(f"bank_country_map length {len(bank_country_map)} ≠ marginal length {n}")
    if not np.all(np.isfinite(gt_in)) or not np.all(np.isfinite(gt_out)):
        raise ValueError("ground-truth marginals must be finite")
    if not np.all(np.isfinite(al_in)) or not np.all(np.isfinite(al_out)):
        raise ValueError("allocated marginals must be finite")

    countries = sorted({c for _, c in bank_country_map})
    n_countries = len(countries)
    k = k_top if k_top is not None else max(1, n // 5)

    # Aggregate metrics over s_in (s_out audit follows the same shape).
    denom = float(np.abs(gt_in).sum())
    total_l1 = float(np.abs(gt_in - al_in).sum() / denom) if denom > 0 else 0.0

    # Bank importance by combined strength (same convention as the
    # X-10R reconstruction RecoveryReport).
    strength_true = (gt_in + gt_out).astype(np.float64)
    strength_recon = (al_in + al_out).astype(np.float64)
    jacc = _top_k_jaccard(strength_true, strength_recon, k=k)

    # Per-country relative L1.
    bank_to_idx = {b: i for i, (b, _) in enumerate(bank_country_map)}
    per_country: dict[str, float] = {}
    for country in countries:
        idxs = [bank_to_idx[b] for b, c in bank_country_map if c == country]
        if not idxs:
            continue
        gt_c = gt_in[idxs]
        al_c = al_in[idxs]
        d = float(np.abs(gt_c).sum())
        per_country[country] = float(np.abs(gt_c - al_c).sum() / d) if d > 0 else 0.0
    if per_country:
        worst_country = max(per_country, key=lambda c: per_country[c])
        per_country_l1_max = per_country[worst_country]
    else:
        worst_country = ""
        per_country_l1_max = 0.0

    # Conservation total (mass discrepancy in aggregate).
    total_gt = float(gt_in.sum())
    total_al = float(al_in.sum())
    cons_err = float(abs(total_gt - total_al) / total_gt) if total_gt > 0 else 0.0

    failures: list[str] = []
    if total_l1 > total_relative_l1_max:
        failures.append(f"total_relative_l1={total_l1:.4f} > {total_relative_l1_max}")
    if jacc < top_k_bank_jaccard_min:
        failures.append(f"top_k_bank_jaccard={jacc:.4f} < {top_k_bank_jaccard_min}")
    if per_country_l1_max > per_country_relative_l1_max:
        failures.append(
            f"per_country_relative_l1_max={per_country_l1_max:.4f} "
            f"({worst_country!r}) > {per_country_relative_l1_max}"
        )
    if cons_err > conservation_total_relative_error_max:
        failures.append(
            f"conservation_total_relative_error={cons_err:.6e} "
            f"> {conservation_total_relative_error_max}"
        )

    return BankLevelRecoveryReport(
        total_relative_l1=total_l1,
        top_k_bank_jaccard=jacc,
        per_country_relative_l1_max=per_country_l1_max,
        per_country_relative_l1_argmax=worst_country,
        conservation_total_relative_error=cons_err,
        n_banks=n,
        n_countries=n_countries,
        k_top=k,
        passed=not failures,
        failure_reasons=tuple(failures),
    )

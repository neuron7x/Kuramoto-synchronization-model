# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GATE_5 — reconstruction recovery audit (synthetic) +
domain-of-validity gate (real data).

Per Protocol X-10R:

    GATE_5  RECONSTRUCTION_RECOVERY    (positive_control.py)
        - on each synthetic ground-truth substrate:
          reconstruct from aggregated marginals, compare to truth:
            spectral_radius_recovery: |ρ_recon − ρ_true|/ρ_true ≤ 0.20
            top_k_hub_jaccard (k = N//10):                    ≥ 0.60
            row_sum_invariant_L1:           ≤ 0.05 × mean_strength
            col_sum_invariant_L1:           ≤ 0.05 × mean_strength

Any threshold violated → INVALID_RECONSTRUCTION. This is the
PRECONDITION for any real-data interpretation.

TWO PATHS — SYNTHETIC vs REAL  (FIX B2, INV-RECONSTRUCTION-2)
-------------------------------------------------------------
On synthetic ground truth ``audit_recovery`` measures literal
recovery against a known network and the verdict is GROUND_TRUTH_
RECOVERED / GROUND_TRUTH_NOT_RECOVERED.

On real data the bank-level (or country-aggregate) ground truth is
unobserved. Asking "did we recover the truth?" is therefore not a
well-posed question on real inputs. The strongest available gate
is **domain-of-validity**: do real input statistics fall inside
the regime where synthetic recovery has been demonstrated?
``check_domain_of_validity`` implements that gate. Its verdicts
live in a separate enum subset (WITHIN_/OUT_OF_VALIDATED_DOMAIN /
INSUFFICIENT_CERTIFICATE) and, by contract, the real-data path is
FORBIDDEN from emitting GROUND_TRUTH_RECOVERED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover — hint-only import to avoid cycle
    from research.reconstruction.positive_control import GroundTruthRecoveryCertificate

# Recovery thresholds — matched 1:1 to Protocol X-10R Gate 5.
RECOVERY_THRESHOLDS: dict[str, float] = {
    "spectral_radius_relative_error_max": 0.20,
    "top_k_hub_jaccard_min": 0.60,
    "row_sum_invariant_L1_relative_max": 0.05,
    "col_sum_invariant_L1_relative_max": 0.05,
}


# ---------------------------------------------------------------------------
# DOMAIN-OF-VALIDITY GATE  (real-data path; FIX B2, INV-RECONSTRUCTION-2)
# ---------------------------------------------------------------------------
#
# On real data, recovery is undefined (no ground truth). The strongest
# available gate is whether the real input statistics fall inside the
# regime where synthetic recovery has been demonstrated.
#
# The verdict surface is intentionally disjoint from the synthetic recovery
# verdict surface: a real-data run MUST emit one of
#   * WITHIN_VALIDATED_DOMAIN
#   * OUT_OF_VALIDATED_DOMAIN
#   * INSUFFICIENT_CERTIFICATE
# and is FORBIDDEN from emitting GROUND_TRUTH_RECOVERED. Conflating the two
# surfaces is the exact category error the X-10R protocol exists to prevent.


class DomainOfValidityStatus(Enum):
    WITHIN_VALIDATED_DOMAIN = "within_validated_domain"
    OUT_OF_VALIDATED_DOMAIN = "out_of_validated_domain"
    INSUFFICIENT_CERTIFICATE = "insufficient_certificate"


@dataclass(frozen=True)
class DomainCheck:
    status: DomainOfValidityStatus
    checks: dict[str, bool] = field(default_factory=dict)
    measured: dict[str, float] = field(default_factory=dict)
    certified_envelope: dict[str, tuple[float, float]] = field(default_factory=dict)
    out_of_range_dims: tuple[str, ...] = ()
    missing_dims: tuple[str, ...] = ()
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "checks": dict(self.checks),
            "measured": dict(self.measured),
            "certified_envelope": {k: list(v) for k, v in self.certified_envelope.items()},
            "out_of_range_dims": list(self.out_of_range_dims),
            "missing_dims": list(self.missing_dims),
            "notes": self.notes,
        }


def _gini(x: np.ndarray) -> float:
    """Gini coefficient on a non-negative 1-D vector.

    Returns 0 for a constant vector, a value in (0, 1) for unequal vectors,
    and is NaN-safe via filtering. NaN/Inf inputs raise ValueError.
    """
    arr = np.asarray(x, dtype=np.float64).ravel()
    if not np.all(np.isfinite(arr)):
        raise ValueError("Gini undefined on non-finite vector")
    if np.any(arr < 0):
        raise ValueError("Gini undefined on negative vector")
    n = arr.size
    if n == 0 or float(arr.sum()) == 0.0:
        return 0.0
    arr_s = np.sort(arr)
    idx = np.arange(1, n + 1, dtype=np.float64)
    return float((2.0 * (idx * arr_s).sum() - (n + 1) * arr_s.sum()) / (n * arr_s.sum()))


def _strength_pearson(s_out: np.ndarray, s_in: np.ndarray) -> float:
    """Pearson correlation between out-strength and in-strength.

    Used as a *crude* reciprocity prior: in real interbank data
    Pearson(s_out, s_in) is large and positive (a heavy borrower is
    typically also a heavy lender). Returns 0.0 when either vector
    has zero variance, which would otherwise be NaN.
    """
    a = np.asarray(s_out, dtype=np.float64).ravel()
    b = np.asarray(s_in, dtype=np.float64).ravel()
    if a.shape != b.shape:
        raise ValueError(f"shape mismatch: {a.shape} vs {b.shape}")
    if not (np.all(np.isfinite(a)) and np.all(np.isfinite(b))):
        raise ValueError("Pearson undefined on non-finite vector")
    if a.size < 2:
        return 0.0
    sa = float(a.std())
    sb = float(b.std())
    if sa == 0.0 or sb == 0.0:
        return 0.0
    return float(((a - a.mean()) * (b - b.mean())).mean() / (sa * sb))


def check_domain_of_validity(
    s_out_real: np.ndarray,
    s_in_real: np.ndarray,
    recovery_certificate: GroundTruthRecoveryCertificate,
    *,
    inferred_density: float | None = None,
    aggregation_ratio: float | None = None,
    require_dims: tuple[str, ...] = ("n_nodes", "density"),
) -> DomainCheck:
    """Real-data validation-domain gate (FIX B2 / INV-RECONSTRUCTION-2).

    Verifies that real inputs lie inside the regime where the supplied
    synthetic recovery certificate has demonstrated recovery. This is
    NOT a recovery test: there is no ground truth on real data, so
    "recovery" cannot be evaluated. The gate's verdict surface is
    deliberately disjoint from `audit_recovery`.

    Dimensions checked when their evidence is present in the certificate:

      * ``n_nodes``       — input size against tested_at_n_nodes envelope
      * ``density``       — caller-supplied inferred density against
                            tested_at_densities envelope
      * ``aggregation_ratio`` — caller-supplied if available

    Heterogeneity (Gini of strengths), Pearson(s_in, s_out), and
    network reciprocity (when carried by the certificate) are reported
    in `measured` / `certified_envelope` for transparency but are NOT
    gate dimensions:

      * `pearson_in_out` is a node-marginal balance measure; the
        certificate's `tested_at_reciprocity` (X-10R-2) is the
        substrate's *topological* reciprocity ratio. These are
        different observables; gating one against the other is a
        category error. Network reciprocity therefore appears in
        `certified_envelope` for provenance but does not drive the
        verdict.
      * `gini_s_*` is reported because heavy-tailed marginals are
        what the BIS path will see; it is not gated.

    Verdict semantics:
      * INSUFFICIENT_CERTIFICATE — the certificate is silent on every
        dimension the caller required (`require_dims`). Fail-closed:
        the gate refuses to certify a domain it has no evidence about.
      * OUT_OF_VALIDATED_DOMAIN — at least one *available* dimension
        falls outside the certified envelope.
      * WITHIN_VALIDATED_DOMAIN — every required dimension is present
        in the certificate and inside its envelope.
    """
    s_out = np.asarray(s_out_real, dtype=np.float64).ravel()
    s_in = np.asarray(s_in_real, dtype=np.float64).ravel()
    if s_out.shape != s_in.shape:
        raise ValueError(f"shape mismatch: s_out={s_out.shape}, s_in={s_in.shape}")
    if s_out.size < 2:
        raise ValueError(f"need at least 2 nodes; got n={s_out.size}")
    if not (np.all(np.isfinite(s_out)) and np.all(np.isfinite(s_in))):
        raise ValueError("s_out / s_in must be finite (no NaN/Inf)")

    envelope = recovery_certificate.evidence_envelope()

    measured: dict[str, float] = {
        "n_nodes": float(s_out.size),
        "gini_s_out": _gini(s_out),
        "gini_s_in": _gini(s_in),
        "pearson_in_out": _strength_pearson(s_out, s_in),
    }
    if inferred_density is not None:
        measured["density"] = float(inferred_density)
    if aggregation_ratio is not None:
        measured["aggregation_ratio"] = float(aggregation_ratio)

    checks: dict[str, bool] = {}
    out_of_range: list[str] = []
    missing: list[str] = []
    certified_envelope: dict[str, tuple[float, float]] = {}

    def _gate(dim: str, value: float | None) -> None:
        if dim not in envelope:
            missing.append(dim)
            return
        lo_raw, hi_raw = envelope[dim]
        lo, hi = float(lo_raw), float(hi_raw)
        certified_envelope[dim] = (lo, hi)
        if value is None:
            missing.append(dim)
            return
        ok = lo <= float(value) <= hi
        checks[dim] = ok
        if not ok:
            out_of_range.append(dim)

    _gate("n_nodes", measured["n_nodes"])
    _gate("density", measured.get("density"))
    # Reciprocity is provenance-only (see docstring): the certificate's
    # `tested_at_reciprocity` is topological while the only observable on
    # real marginals is Pearson(s_in, s_out). We surface the certified
    # envelope but do NOT gate on it. A caller that demands reciprocity
    # via `require_dims` still triggers INSUFFICIENT — the contract
    # honours their explicit ask, but the *default* path no longer
    # falsely gates a node-balance number against a topology number.
    if "reciprocity" in envelope:
        lo_raw, hi_raw = envelope["reciprocity"]
        certified_envelope["reciprocity"] = (float(lo_raw), float(hi_raw))
    if "reciprocity" in require_dims and "reciprocity" not in checks:
        missing.append("reciprocity")

    required_missing = [d for d in require_dims if d in missing]
    if required_missing == list(require_dims) and not checks:
        status = DomainOfValidityStatus.INSUFFICIENT_CERTIFICATE
        notes = (
            "certificate is silent on every required dimension "
            f"({list(require_dims)}); cannot certify domain"
        )
    elif required_missing:
        status = DomainOfValidityStatus.INSUFFICIENT_CERTIFICATE
        notes = f"certificate is silent on required dimension(s): {required_missing}"
    elif out_of_range:
        status = DomainOfValidityStatus.OUT_OF_VALIDATED_DOMAIN
        notes = f"out of certified envelope on: {out_of_range}"
    else:
        status = DomainOfValidityStatus.WITHIN_VALIDATED_DOMAIN
        notes = "real inputs fall inside the certified recovery envelope"

    return DomainCheck(
        status=status,
        checks=dict(checks),
        measured=dict(measured),
        certified_envelope=certified_envelope,
        out_of_range_dims=tuple(out_of_range),
        missing_dims=tuple(sorted(set(missing))),
        notes=notes,
    )


@dataclass(frozen=True)
class RecoveryReport:
    spectral_radius_true: float
    spectral_radius_recon: float
    spectral_radius_relative_error: float
    top_k_hub_jaccard: float
    row_sum_invariant_L1: float
    col_sum_invariant_L1: float
    mean_strength: float
    k_top: int
    passed: bool
    failure_reasons: tuple[str, ...]


def _spectral_radius(w: np.ndarray) -> float:
    """ρ(W) = max |eigenvalue|."""
    if w.size == 0 or not np.any(w):
        return 0.0
    eigs = np.linalg.eigvals(w.astype(np.float64))
    return float(np.max(np.abs(eigs)))


def _top_k_jaccard(deg_true: np.ndarray, deg_recon: np.ndarray, *, k: int) -> float:
    if k <= 0:
        return 0.0
    top_t = set(np.argsort(-deg_true)[:k].tolist())
    top_r = set(np.argsort(-deg_recon)[:k].tolist())
    union = top_t | top_r
    if not union:
        return 0.0
    return float(len(top_t & top_r) / len(union))


def audit_recovery(
    w_true: np.ndarray,
    w_recon: np.ndarray,
    *,
    k_top: int | None = None,
) -> RecoveryReport:
    """Compare reconstructed W against ground-truth W on Gate 5 metrics."""
    if w_true.shape != w_recon.shape or w_true.ndim != 2 or w_true.shape[0] != w_true.shape[1]:
        raise ValueError(
            f"w_true and w_recon must be matching square 2-D; got {w_true.shape} / {w_recon.shape}"
        )
    n = w_true.shape[0]
    k = k_top if k_top is not None else max(1, n // 10)
    rho_true = _spectral_radius(w_true)
    rho_recon = _spectral_radius(w_recon)
    rho_rel_err = abs(rho_recon - rho_true) / rho_true if rho_true > 0 else float("inf")
    s_out_true = w_true.sum(axis=1)
    s_out_recon = w_recon.sum(axis=1)
    s_in_true = w_true.sum(axis=0)
    s_in_recon = w_recon.sum(axis=0)
    # Hub definition: total strength s_out + s_in (Battiston-Caldarelli DebtRank
    # convention for weighted systemic networks). Binary degree is meaningless
    # in the bank-exposure setting where one $1B link is a bigger systemic
    # hub than fifty $1M links. The reconstruction is calibrated against
    # marginal strengths, so this is the observable that Gate 5 must check.
    strength_true = (s_out_true + s_in_true).astype(np.float64)
    strength_recon = (s_out_recon + s_in_recon).astype(np.float64)
    jacc = _top_k_jaccard(strength_true, strength_recon, k=k)
    mean_strength = float((s_out_true + s_in_true).mean() / 2.0)
    if mean_strength == 0:
        mean_strength = 1.0  # avoid div-by-zero
    row_l1 = float(np.abs(s_out_true - s_out_recon).sum() / n / mean_strength)
    col_l1 = float(np.abs(s_in_true - s_in_recon).sum() / n / mean_strength)
    failures: list[str] = []
    if rho_rel_err > RECOVERY_THRESHOLDS["spectral_radius_relative_error_max"]:
        failures.append(
            f"spectral_radius_relative_error={rho_rel_err:.3f} > "
            f"{RECOVERY_THRESHOLDS['spectral_radius_relative_error_max']}"
        )
    if jacc < RECOVERY_THRESHOLDS["top_k_hub_jaccard_min"]:
        failures.append(
            f"top_k_hub_jaccard={jacc:.3f} < {RECOVERY_THRESHOLDS['top_k_hub_jaccard_min']}"
        )
    if row_l1 > RECOVERY_THRESHOLDS["row_sum_invariant_L1_relative_max"]:
        failures.append(
            f"row_sum_invariant_L1={row_l1:.3f} > "
            f"{RECOVERY_THRESHOLDS['row_sum_invariant_L1_relative_max']}"
        )
    if col_l1 > RECOVERY_THRESHOLDS["col_sum_invariant_L1_relative_max"]:
        failures.append(
            f"col_sum_invariant_L1={col_l1:.3f} > "
            f"{RECOVERY_THRESHOLDS['col_sum_invariant_L1_relative_max']}"
        )
    return RecoveryReport(
        spectral_radius_true=rho_true,
        spectral_radius_recon=rho_recon,
        spectral_radius_relative_error=rho_rel_err,
        top_k_hub_jaccard=jacc,
        row_sum_invariant_L1=row_l1,
        col_sum_invariant_L1=col_l1,
        mean_strength=mean_strength,
        k_top=k,
        passed=not failures,
        failure_reasons=tuple(failures),
    )


def conservation_of_mass_passes(
    s_out: np.ndarray, s_in: np.ndarray, *, tol_rel: float = 1e-9
) -> bool:
    """GATE_2 — |Σs_in − Σs_out| / Σs_in < tol_rel."""
    s_out_arr = np.asarray(s_out, dtype=np.float64)
    s_in_arr = np.asarray(s_in, dtype=np.float64)
    sum_in = float(s_in_arr.sum())
    sum_out = float(s_out_arr.sum())
    if sum_in <= 0:
        return False
    return abs(sum_in - sum_out) / sum_in < tol_rel

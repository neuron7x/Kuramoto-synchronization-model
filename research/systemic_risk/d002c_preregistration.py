# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002C — Pre-registration validator + acceptance lock.

Rationale
=========
The D-002C Signal Amplification Sweep (issue #654) is a 216-cell
pre-committed falsification protocol. The pre-registration YAML
at ``docs/governance/D002C_PREREGISTRATION.yaml`` is the SINGLE
SOURCE OF TRUTH for:

  * acceptance rule and tier mapping
  * CI method (BCa bootstrap, locked) and α
  * direction-consistency rule
  * multiple-testing correction (Bonferroni on the cell-count
    locked in the YAML — DO NOT recompute at launch time)
  * falsifier text
  * substrate / metric / variance-reduction grid identity

This module:

  * parses + freezes that YAML into :class:`D002CPreregistration`
  * computes a content-addressed ``preregistration_sha`` over the
    raw file bytes so any subsequent edit is detectable
  * exposes :func:`validate_sweep_config` which the sweep runner
    MUST call before checkpoint creation. A mismatch (e.g. driver
    silently using ``percentile_bootstrap`` instead of the locked
    ``bca_bootstrap``) raises :class:`PreregistrationMismatch`
    listing every disagreement.

Strict scope
============
Validator / contract layer ONLY. NO sweep execution. NO claim
layer. NO threshold tuning. NO post-hoc relaxation. This module
is callable by ``research/systemic_risk/d002c_sweep_runner.py``
(C2.4) but emits no claim of its own — it only refuses to
proceed when the driver disagrees with the pre-registration.

The pre-registration is locked at the moment this PR merges
(per the anchor-commit clause inside the YAML). Any edit to the
YAML after this PR is a NEW pre-registration with a NEW sha — a
fresh contract, not a mutation of the old one.
"""

from __future__ import annotations

import enum
import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

# ---------------------------------------------------------------------------
# Schema version — bumped only on incompatible *contract* changes (renamed
# field, removed acceptance rule). Adding a new optional logged metric is
# NOT a schema bump.
# ---------------------------------------------------------------------------
PREREGISTRATION_SCHEMA_VERSION: Final[int] = 1


class CIMethod(enum.Enum):
    """CI estimator allowed in the D-002C contract.

    BCa is locked because:

    1. ``n_bootstrap = 16`` is small; percentile bootstrap is
       biased at small B with skewed estimators, and our
       signal estimator (mean difference of paired censored
       observations) IS skewed.
    2. CRN pairing yields strong correlation between signal
       and null; BCa's acceleration correction adapts to that
       skewness in a single coherent step.
    3. Normal CI assumes a Gaussian sampling distribution
       which we explicitly disclaim — Kuramoto onset times
       are heavy-tailed.
    """

    BCA_BOOTSTRAP = "bca_bootstrap"
    PERCENTILE_BOOTSTRAP = "percentile_bootstrap"
    NORMAL = "normal"


class MultipleTestingCorrection(enum.Enum):
    """Family-wise / FDR correction across the pre-registered cell grid."""

    BONFERRONI = "bonferroni"
    FDR_BH = "fdr_bh"
    NONE = "none"


class PreregistrationCorrupt(RuntimeError):
    """YAML missing/malformed/invariant-violating field."""


class PreregistrationMismatch(RuntimeError):
    """Sweep config disagrees with the locked pre-registration.

    The exception message lists every disagreement (not just the
    first) so a single re-launch fixes all of them. Fail-closed:
    the sweep runner MUST NOT proceed past this exception.
    """


# ---------------------------------------------------------------------------
# Frozen dataclass — content is immutable once load_and_lock returns.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class D002CPreregistration:
    """Immutable lock over the D-002C pre-registration YAML.

    Fields mirror the canonical YAML structure; derived fields
    (``effective_alpha_per_cell``) are computed in :func:`load_and_lock`
    from the primary fields so they cannot drift.
    """

    schema_version: int
    version: int
    issue: int
    follows: int
    tier_if_pass: str
    tier_if_fail: str
    acceptance_rule: str
    # Locked formal decisions
    ci_method: CIMethod
    ci_alpha: float
    signal_ci_ratio_threshold: float
    direction_consistency_min_seeds: int
    direction_stability_min_fraction: float
    multiple_testing_correction: MultipleTestingCorrection
    n_cells: int
    # Derived (Bonferroni: ci_alpha / n_cells; else ci_alpha)
    effective_alpha_per_cell: float
    # Sweep design (compared at validate_sweep_config time)
    n_seeds: int
    n_bootstrap: int
    N_grid: tuple[int, ...]
    lambda_grid: tuple[float, ...]
    substrate_ids: tuple[str, ...]
    metric_ids: tuple[str, ...]
    variance_reduction: tuple[str, ...]
    substrate_seed: int
    # Falsifier + forbidden tiers
    forbidden_outputs: tuple[str, ...]
    # Content-addressed identity
    preregistration_sha: str
    yaml_path: str = field(compare=False)

    # ---- invariants ---------------------------------------------------

    def __post_init__(self) -> None:
        if not (0.0 < self.ci_alpha < 1.0):
            raise PreregistrationCorrupt(f"ci_alpha must be in (0, 1); got {self.ci_alpha}")
        if not (
            math.isfinite(self.signal_ci_ratio_threshold) and self.signal_ci_ratio_threshold > 0.0
        ):
            raise PreregistrationCorrupt(
                f"signal_ci_ratio_threshold must be > 0; got {self.signal_ci_ratio_threshold}"
            )
        if self.direction_consistency_min_seeds < 1:
            raise PreregistrationCorrupt(
                "direction_consistency_min_seeds must be >= 1; got "
                f"{self.direction_consistency_min_seeds}"
            )
        if self.direction_consistency_min_seeds > self.n_seeds:
            raise PreregistrationCorrupt(
                "direction_consistency_min_seeds "
                f"({self.direction_consistency_min_seeds}) "
                f"exceeds n_seeds ({self.n_seeds})"
            )
        if not (0.0 < self.direction_stability_min_fraction <= 1.0):
            raise PreregistrationCorrupt(
                "direction_stability_min_fraction must be in (0, 1]; got "
                f"{self.direction_stability_min_fraction}"
            )
        if self.n_cells < 1:
            raise PreregistrationCorrupt(f"n_cells must be >= 1; got {self.n_cells}")
        # Bonferroni consistency: effective_alpha_per_cell must equal
        # ci_alpha / n_cells (Bonferroni) or ci_alpha (no correction)
        if self.multiple_testing_correction is MultipleTestingCorrection.BONFERRONI:
            expected = self.ci_alpha / float(self.n_cells)
        elif self.multiple_testing_correction is MultipleTestingCorrection.NONE:
            expected = self.ci_alpha
        else:
            # FDR_BH alpha-per-cell is observation-dependent (BH step-up
            # procedure), not a fixed value; sentinel is the family α.
            expected = self.ci_alpha
        if not math.isclose(expected, self.effective_alpha_per_cell, rel_tol=0.0, abs_tol=1e-15):
            raise PreregistrationCorrupt(
                "effective_alpha_per_cell drift: expected "
                f"{expected!r}, got {self.effective_alpha_per_cell!r}"
            )
        if self.n_seeds < 2:
            raise PreregistrationCorrupt(f"n_seeds must be >= 2; got {self.n_seeds}")
        if self.n_bootstrap < 2:
            raise PreregistrationCorrupt(f"n_bootstrap must be >= 2; got {self.n_bootstrap}")
        if not self.N_grid or any(N < 2 for N in self.N_grid):
            raise PreregistrationCorrupt(
                f"N_grid must be non-empty and every N >= 2; got {self.N_grid}"
            )
        if not self.lambda_grid or any(
            not math.isfinite(lam) or lam < 0.0 for lam in self.lambda_grid
        ):
            raise PreregistrationCorrupt(
                f"lambda_grid must be non-empty and every λ finite + >= 0; got {self.lambda_grid}"
            )
        if not self.substrate_ids:
            raise PreregistrationCorrupt("substrate_ids must be non-empty")
        if not self.metric_ids:
            raise PreregistrationCorrupt("metric_ids must be non-empty")
        if len(self.preregistration_sha) != 64 or not all(
            c in "0123456789abcdef" for c in self.preregistration_sha
        ):
            raise PreregistrationCorrupt(
                f"preregistration_sha must be a hex sha256; got {self.preregistration_sha!r}"
            )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _require(data: dict[str, Any], path: str, *keys: str) -> Any:
    """Walk nested keys; raise PreregistrationCorrupt with a precise path."""
    node: Any = data
    walked: list[str] = []
    for k in keys:
        walked.append(k)
        if not isinstance(node, dict) or k not in node:
            raise PreregistrationCorrupt(f"{path}: missing required key '{'.'.join(walked)}'")
        node = node[k]
    return node


def _canonical_rule_text(primary_cert_rule: dict[str, Any]) -> str:
    """Build a stable acceptance-rule string from the YAML requirements.

    The text is deterministic given the requirements list: we sort by
    requirement id and join with newlines. Driver code compares
    string-equal at validate_sweep_config time.
    """
    reqs = primary_cert_rule.get("requirements", [])
    if not isinstance(reqs, list) or not reqs:
        raise PreregistrationCorrupt(
            "acceptance.primary_certification_rule.requirements must be a non-empty list"
        )
    parts: list[str] = []
    for r in sorted(reqs, key=lambda x: str(x.get("id", ""))):
        if not isinstance(r, dict) or "id" not in r or "rule" not in r:
            raise PreregistrationCorrupt(
                f"each requirement must be a mapping with 'id' and 'rule'; got {r!r}"
            )
        parts.append(f"{r['id']}: {r['rule']}")
    return "\n".join(parts)


def _yaml_sha256(yaml_bytes: bytes) -> str:
    """Sha256 over raw file bytes. Git preserves byte content per-blob, so
    the same merged YAML always produces the same sha across check-outs.
    Any whitespace change (including trailing newline) yields a new sha;
    this is intentional — the file IS the contract.
    """
    return hashlib.sha256(yaml_bytes).hexdigest()


def load_and_lock(yaml_path: Path) -> D002CPreregistration:
    """Parse YAML, compute content-addressed sha, return frozen lock.

    Raises
    ------
    PreregistrationCorrupt
        If the YAML is malformed, missing required fields, or its
        contents violate the internal invariants.
    """
    if not yaml_path.is_file():
        raise PreregistrationCorrupt(f"pre-registration YAML not found: {yaml_path}")
    yaml_bytes = yaml_path.read_bytes()
    try:
        data: Any = yaml.safe_load(yaml_bytes.decode("utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - covered by test
        raise PreregistrationCorrupt(f"YAML parse failed: {exc}") from exc
    if not isinstance(data, dict):
        raise PreregistrationCorrupt("pre-registration YAML must be a top-level mapping")

    version = int(_require(data, str(yaml_path), "version"))
    issue = int(_require(data, str(yaml_path), "issue"))
    follows = int(_require(data, str(yaml_path), "follows"))

    primary = _require(data, str(yaml_path), "acceptance", "primary_certification_rule")
    if not isinstance(primary, dict):
        raise PreregistrationCorrupt("acceptance.primary_certification_rule must be a mapping")
    tier_if_pass = str(_require(primary, "acceptance.primary_certification_rule", "tier_if_pass"))
    tier_if_fail = str(_require(primary, "acceptance.primary_certification_rule", "tier_if_fail"))
    acceptance_rule = _canonical_rule_text(primary)

    formal = _require(data, str(yaml_path), "acceptance", "formal_decisions")
    if not isinstance(formal, dict):
        raise PreregistrationCorrupt("acceptance.formal_decisions must be a mapping")
    try:
        ci_method = CIMethod(str(_require(formal, "formal_decisions", "ci_method")))
    except ValueError as exc:
        raise PreregistrationCorrupt(f"unknown ci_method: {formal.get('ci_method')!r}") from exc
    ci_alpha = float(_require(formal, "formal_decisions", "ci_alpha"))
    signal_ci_ratio_threshold = float(
        _require(formal, "formal_decisions", "signal_ci_ratio_threshold")
    )
    direction_consistency_min_seeds = int(
        _require(formal, "formal_decisions", "direction_consistency_min_seeds")
    )
    direction_stability_min_fraction = float(
        _require(formal, "formal_decisions", "direction_stability_min_fraction")
    )
    mtc = _require(formal, "formal_decisions", "multiple_testing_correction")
    if not isinstance(mtc, dict):
        raise PreregistrationCorrupt(
            "formal_decisions.multiple_testing_correction must be a mapping"
        )
    try:
        mtc_method = MultipleTestingCorrection(
            str(_require(mtc, "multiple_testing_correction", "method"))
        )
    except ValueError as exc:
        raise PreregistrationCorrupt(
            f"unknown multiple_testing_correction.method: {mtc.get('method')!r}"
        ) from exc
    n_cells = int(_require(mtc, "multiple_testing_correction", "n_cells"))
    if mtc_method is MultipleTestingCorrection.BONFERRONI:
        effective_alpha_per_cell = ci_alpha / float(n_cells)
    else:
        effective_alpha_per_cell = ci_alpha
    lambda_grid_raw = _require(formal, "formal_decisions", "lambda_grid")
    if not isinstance(lambda_grid_raw, list) or not lambda_grid_raw:
        raise PreregistrationCorrupt("formal_decisions.lambda_grid must be a non-empty list")
    lambda_grid = tuple(float(x) for x in lambda_grid_raw)

    sweep = _require(data, str(yaml_path), "sweep")
    if not isinstance(sweep, dict):
        raise PreregistrationCorrupt("sweep must be a mapping")
    n_seeds = int(_require(sweep, "sweep", "n_seeds"))
    n_bootstrap = int(_require(sweep, "sweep", "n_bootstrap"))
    N_grid_raw = _require(sweep, "sweep", "N_grid")
    if not isinstance(N_grid_raw, list) or not N_grid_raw:
        raise PreregistrationCorrupt("sweep.N_grid must be a non-empty list")
    N_grid = tuple(int(x) for x in N_grid_raw)

    substrates_raw = _require(sweep, "sweep", "substrates")
    if not isinstance(substrates_raw, list) or not substrates_raw:
        raise PreregistrationCorrupt("sweep.substrates must be a non-empty list")
    substrate_ids: list[str] = []
    for s in substrates_raw:
        if not isinstance(s, dict) or "id" not in s:
            raise PreregistrationCorrupt(f"each sweep.substrates entry must carry 'id'; got {s!r}")
        substrate_ids.append(str(s["id"]))

    metrics_raw = _require(sweep, "sweep", "metrics")
    if not isinstance(metrics_raw, list) or not metrics_raw:
        raise PreregistrationCorrupt("sweep.metrics must be a non-empty list")
    metric_ids: list[str] = []
    for m in metrics_raw:
        if not isinstance(m, dict) or "id" not in m:
            raise PreregistrationCorrupt(f"each sweep.metrics entry must carry 'id'; got {m!r}")
        metric_ids.append(str(m["id"]))

    vred_raw = _require(sweep, "sweep", "variance_reduction")
    if not isinstance(vred_raw, list) or not vred_raw:
        raise PreregistrationCorrupt("sweep.variance_reduction must be a non-empty list")
    variance_reduction = tuple(str(v) for v in vred_raw)

    substrate_seed = int(_require(data, str(yaml_path), "reproducibility", "substrate_seed"))

    forbidden_raw = _require(data, str(yaml_path), "forbidden_outputs")
    if not isinstance(forbidden_raw, list):
        raise PreregistrationCorrupt("forbidden_outputs must be a list")
    forbidden_outputs = tuple(str(x) for x in forbidden_raw)

    sha = _yaml_sha256(yaml_bytes)

    return D002CPreregistration(
        schema_version=PREREGISTRATION_SCHEMA_VERSION,
        version=version,
        issue=issue,
        follows=follows,
        tier_if_pass=tier_if_pass,
        tier_if_fail=tier_if_fail,
        acceptance_rule=acceptance_rule,
        ci_method=ci_method,
        ci_alpha=ci_alpha,
        signal_ci_ratio_threshold=signal_ci_ratio_threshold,
        direction_consistency_min_seeds=direction_consistency_min_seeds,
        direction_stability_min_fraction=direction_stability_min_fraction,
        multiple_testing_correction=mtc_method,
        n_cells=n_cells,
        effective_alpha_per_cell=effective_alpha_per_cell,
        n_seeds=n_seeds,
        n_bootstrap=n_bootstrap,
        N_grid=N_grid,
        lambda_grid=lambda_grid,
        substrate_ids=tuple(substrate_ids),
        metric_ids=tuple(metric_ids),
        variance_reduction=variance_reduction,
        substrate_seed=substrate_seed,
        forbidden_outputs=forbidden_outputs,
        preregistration_sha=sha,
        yaml_path=str(yaml_path),
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


_EXPECTED_KEYS: Final[frozenset[str]] = frozenset(
    {
        "ci_method",
        "ci_alpha",
        "signal_ci_ratio_threshold",
        "direction_consistency_min_seeds",
        "direction_stability_min_fraction",
        "multiple_testing_correction",
        "n_seeds",
        "n_bootstrap",
        "N_grid",
        "lambda_grid",
        "substrate_ids",
        "metric_ids",
        "variance_reduction",
        "substrate_seed",
        "preregistration_sha",
    }
)


def validate_sweep_config(
    preregistration: D002CPreregistration,
    sweep_config: dict[str, Any],
) -> None:
    """Compare sweep_config to the locked pre-registration.

    Every disagreement is collected (not first-fail) so a single
    re-launch can fix all of them. Raises
    :class:`PreregistrationMismatch` if any disagreement is found.

    The sweep_config dict MUST carry every key in
    :data:`_EXPECTED_KEYS`; missing keys are themselves mismatches.

    ``preregistration_sha`` is the load-bearing check: if the
    driver's idea of the contract sha doesn't match the prereg
    object the driver was constructed against, the YAML on disk
    has been edited post-lock OR the driver was misconstructed —
    either way, refuse.
    """
    missing = _EXPECTED_KEYS - set(sweep_config.keys())
    mismatches: list[str] = []
    if missing:
        mismatches.append("sweep_config missing required keys: " + ", ".join(sorted(missing)))

    def _cmp(key: str, expected: Any) -> None:
        if key not in sweep_config:
            return  # already reported above
        got = sweep_config[key]
        if isinstance(expected, tuple):
            got_tuple = tuple(got) if isinstance(got, (list, tuple)) else got
            if got_tuple != expected:
                mismatches.append(f"{key}: expected {expected!r}, got {got_tuple!r}")
        elif isinstance(expected, float):
            if not (isinstance(got, (int, float)) and math.isfinite(float(got))):
                mismatches.append(f"{key}: expected float {expected!r}, got {got!r}")
                return
            if not math.isclose(float(got), expected, rel_tol=0.0, abs_tol=1e-12):
                mismatches.append(f"{key}: expected {expected!r}, got {got!r}")
        else:
            if got != expected:
                mismatches.append(f"{key}: expected {expected!r}, got {got!r}")

    _cmp("ci_method", preregistration.ci_method.value)
    _cmp("ci_alpha", preregistration.ci_alpha)
    _cmp("signal_ci_ratio_threshold", preregistration.signal_ci_ratio_threshold)
    _cmp(
        "direction_consistency_min_seeds",
        preregistration.direction_consistency_min_seeds,
    )
    _cmp(
        "direction_stability_min_fraction",
        preregistration.direction_stability_min_fraction,
    )
    _cmp(
        "multiple_testing_correction",
        preregistration.multiple_testing_correction.value,
    )
    _cmp("n_seeds", preregistration.n_seeds)
    _cmp("n_bootstrap", preregistration.n_bootstrap)
    _cmp("N_grid", preregistration.N_grid)
    _cmp("lambda_grid", preregistration.lambda_grid)
    _cmp("substrate_ids", preregistration.substrate_ids)
    _cmp("metric_ids", preregistration.metric_ids)
    _cmp("variance_reduction", preregistration.variance_reduction)
    _cmp("substrate_seed", preregistration.substrate_seed)
    _cmp("preregistration_sha", preregistration.preregistration_sha)

    if mismatches:
        joined = "\n".join(f"  - {m}" for m in mismatches)
        raise PreregistrationMismatch(
            f"sweep_config disagrees with pre-registration "
            f"sha={preregistration.preregistration_sha[:16]}…:\n{joined}"
        )


__all__ = [
    "PREREGISTRATION_SCHEMA_VERSION",
    "CIMethod",
    "MultipleTestingCorrection",
    "PreregistrationCorrupt",
    "PreregistrationMismatch",
    "D002CPreregistration",
    "load_and_lock",
    "validate_sweep_config",
]

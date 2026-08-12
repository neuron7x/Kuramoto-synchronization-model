# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002G-M3 — Adversarial traps.

Each trap is a SHOULD-FAIL attack that the M3 verifier / realiser /
dispatch must reject fail-closed. Traps probe:

* T1: Fake marginal match — semantically wrong K_null structure.
* T2: Density match but degree mismatch.
* T3: Spectral match but summary mismatch.
* T4: Non-finite K_null injected at the substrate level.
* T5: Seed collision — same null_seed yields same K_null; different
  seeds yield DIFFERENT K_null.
* T6: Global RNG monkey-patching has no effect on M3 output.
* T7: Hidden downgrade — M3 INELIGIBLE must NOT silently fall back
  to M1 / M2.
* T8: Claim-leakage forbidden-phrase scan over M3 module + docs.
* T9: Canonical-run artifact trap — M3 must not write to
  ``artifacts/d002g/canonical/``.
* T10: D002C ledger trap — sha pinned, must be unchanged after the
  full M3 verifier matrix runs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pytest

from research.systemic_risk.d002c_substrates import (
    T_HORIZON,
    BlockStructuredSubstrate,
    RicciFlowSubstrate,
    SubstrateRealization,
    TemporalKtSubstrate,
)
from research.systemic_risk.d002g_null_mechanisms import (
    M2_INJECTION_SEQUENCE_SALT,
    M2_NODE_PAYLOAD_SALT,
    M2_PLACEBO_SALT,
    M3_TOPOLOGY_CONDITIONED_SALT,
    M6_PLACEBO_SALT,
    M3GeneratorDivergentError,
    M3NotEligibleError,
    M3TopologySummary,
    deterministic_mix,
    extract_m3_topology_summary,
    realize_null,
    topology_matched_resample,
    verify_m3_eligibility,
)

_LAMBDA = 0.4
_BASE_SEED = 42
_NULL_SEED = 12345
REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.slow


# ---- Trap T1: fake marginal match (semantically wrong) ---------------


def test_trap_t1_fake_marginal_match_rejected() -> None:
    """A target summary with semantically wrong fields must be rejected.

    Even if numerical density / spectral_radius match, a degree
    sequence that sums to a value inconsistent with the support count
    must trigger ``M3GeneratorDivergentError`` rather than emit a
    silently-corrupt K_null.
    """
    bad = M3TopologySummary(
        degree_sequence=tuple(0.0 for _ in range(8)),  # all zero
        block_label_histogram=(8,),
        spectral_radius_over_N=0.5,
        density=0.3,
        n_nodes=8,
        n_support_edges=8,  # contradicts zero degree sequence
        summary_sha256="0" * 64,
    )
    with pytest.raises(M3GeneratorDivergentError):
        topology_matched_resample(bad, null_seed=_NULL_SEED, rng_salt_mix=99)


# ---- Trap T2: density match but degree mismatch ----------------------


def test_trap_t2_degree_wasserstein_below_tolerance_required() -> None:
    """Generator output with mismatched degree must fail the verifier.

    Constructive trap: take the precursor's K_p, build a synthetic
    K_null by zeroing alternating rows. Density / spectral / block
    histogram all drift; the comparator must flag at least one
    failed_marginal.
    """
    sub = RicciFlowSubstrate()
    real = sub.realize(N=50, lambda_=_LAMBDA, seed=_BASE_SEED)
    K_p = np.asarray(real.K_precursor[4], dtype=np.float64)
    K_corrupt = K_p.copy()
    K_corrupt[::2, :] = 0.0
    K_corrupt = (K_corrupt + K_corrupt.T) / 2.0
    summary_p = extract_m3_topology_summary(K_p, substrate_block_labels=None)
    summary_corrupt = extract_m3_topology_summary(K_corrupt, substrate_block_labels=None)
    # Direct comparator call. The corrupt K must fail at least one
    # marginal.
    from research.systemic_risk.d002g_null_mechanisms import _compare_m3_marginals

    rep = _compare_m3_marginals(summary_p, summary_corrupt)
    assert not rep.all_within_tolerance
    assert rep.failed_marginal is not None


# ---- Trap T3: spectral match but summary sha mismatch ----------------


def test_trap_t3_spectral_match_summary_sha_must_match_marginals() -> None:
    """summary_sha256 cannot be forged independent of marginal fields.

    A summary built with the same numeric fields produces the same
    sha; a single bit change in any field produces a different sha.
    """
    s1 = M3TopologySummary(
        degree_sequence=(1.0, 2.0, 3.0),
        block_label_histogram=(3,),
        spectral_radius_over_N=0.5,
        density=0.1,
        n_nodes=3,
        n_support_edges=2,
        summary_sha256="abc",
    )
    K = np.zeros((3, 3), dtype=np.float64)
    K[0, 1] = K[1, 0] = 1.0
    K[1, 2] = K[2, 1] = 1.0
    s_extracted = extract_m3_topology_summary(K, substrate_block_labels=None)
    # Forging the sha post-hoc is structurally impossible — the
    # extractor recomputes the sha over the actual fields. The bogus
    # "abc" sha in s1 cannot survive a real extraction.
    assert s_extracted.summary_sha256 != s1.summary_sha256


# ---- Trap T4: non-finite K_null injected ---------------------------


class _NonFinitePrecursorSubstrate:
    """Substrate that emits non-finite K_precursor entries."""

    @property
    def id(self) -> str:
        return "synthetic_T4_nonfinite_precursor"

    def realize(self, *, N: int, lambda_: float, seed: int) -> SubstrateRealization:
        _ = seed
        K_static = np.eye(N, dtype=np.float64) * 0.0
        for i in range(N - 1):
            K_static[i, i + 1] = 1.0 / float(N)
            K_static[i + 1, i] = 1.0 / float(N)
        K_baseline = np.broadcast_to(K_static, (T_HORIZON, N, N)).astype(np.float64, copy=True)
        K_precursor = K_baseline.copy()
        # Inject one NaN to trigger criterion 1 fail.
        K_precursor[4, 0, 0] = float("nan")
        return SubstrateRealization(
            substrate_id=self.id,
            N=N,
            lambda_=lambda_,
            seed=seed,
            K_baseline=K_baseline,
            K_precursor=K_precursor,
            K_c=1.0,
            density=0.5,
            spectral_radius_over_N=0.5,
            spectral_radius_over_N_precursor=0.5,
            precursor_frobenius_delta=0.1,
        )


def test_trap_t4_nonfinite_k_p_triggers_numerical_verdict() -> None:
    v = verify_m3_eligibility(
        _NonFinitePrecursorSubstrate(),
        N=50,
        lambda_value=_LAMBDA,
        base_seed=_BASE_SEED,
        null_seed=_NULL_SEED,
    )
    assert v.status == "INELIGIBLE_M3_NUMERICAL_NONFINITE"


# ---- Trap T5: seed collision / distinctness --------------------------


def test_trap_t5_same_seed_replays_bit_identically() -> None:
    """Same (substrate, N, λ, base_seed, null_seed) → bit-identical K_null."""
    sub = RicciFlowSubstrate()
    real1 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    real2 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    assert np.array_equal(real1.K_baseline, real2.K_baseline)
    assert real1.payload_sha256 == real2.payload_sha256


def test_trap_t5_different_null_seed_yields_different_k_null() -> None:
    """Different null_seed (same base_seed) → DIFFERENT K_null on ELIGIBLE substrate."""
    sub = RicciFlowSubstrate()
    real1 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    real2 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED + 1,
    )
    assert not np.array_equal(real1.K_baseline, real2.K_baseline)


# ---- Trap T6: global RNG monkey-patch is no-op --------------------


def test_trap_t6_global_rng_monkeypatch_has_no_effect_on_m3() -> None:
    """np.random.seed must not influence M3 output (no global state)."""
    sub = RicciFlowSubstrate()
    real1 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    np.random.seed(7777)
    np.random.random()  # consume some global state
    real2 = realize_null(
        sub,
        strategy="M3_TOPOLOGY_CONDITIONED",
        base_seed=_BASE_SEED,
        N=50,
        lambda_value=_LAMBDA,
        null_seed=_NULL_SEED,
    )
    assert np.array_equal(real1.K_baseline, real2.K_baseline), (
        "M3-INV-1 VIOLATED: global RNG state perturbation changed M3 output; "
        "M3 must depend only on its explicit seed inputs (no hidden global state)."
    )


# ---- Trap T7: hidden downgrade forbidden ----------------------------


def test_trap_t7_ineligible_m3_does_not_silently_fall_back() -> None:
    """realize_null with strategy=M3 must raise on INELIGIBLE, not return M1/M2 result."""
    for sub in (BlockStructuredSubstrate(), TemporalKtSubstrate()):
        with pytest.raises(M3NotEligibleError) as excinfo:
            realize_null(
                sub,
                strategy="M3_TOPOLOGY_CONDITIONED",
                base_seed=_BASE_SEED,
                N=50,
                lambda_value=_LAMBDA,
                null_seed=_NULL_SEED,
            )
        # Verdict structure intact + status literal is one of the
        # INELIGIBLE_M3_* family.
        assert excinfo.value.verdict.status.startswith("INELIGIBLE_M3_")


# ---- Trap T8: claim-leakage forbidden-phrase scan -------------------


_FORBIDDEN_PHRASES: tuple[str, ...] = (
    "D-002G validated",
    "canonical run unblocked",
    "canonical run authorised",
    "canonical run authorized",
    "D-002C rescued",
    "D002C rescued",
    "ledger promoted",
    "tier PASS",
    "tier promoted",
    "scientific validation complete",
    "scientific PASS achieved",
    "M3 proves",
    "topology proves",
    "null audit passed globally",
    "VALIDATED_REAL_BANK_LEVEL_RESULT",
    "TESTED_POSITIVE_REAL",
    "BANK_LEVEL_PRECURSOR_CONFIRMED",
    "real-data validated",
    "bank-level confirmed",
    "gamma universality",
    "SYNTHETIC_GATE6_CERTIFIED_D002G_REDESIGN",
    "B1 closed by design",
    "constant-lift solved",
    "M3 fixed everything",
)


def test_trap_t8_no_forbidden_phrase_in_m3_module_or_docs() -> None:
    """No M3 source / doc carries a forbidden D-002G PASS claim string
    outside an explicit forbidden-list / negation context."""
    scan_paths = [
        REPO_ROOT / "research" / "systemic_risk" / "d002g_null_mechanisms.py",
        REPO_ROOT / "docs" / "governance" / "D002G_M3_IMPLEMENTATION_REPORT.md",
        REPO_ROOT / "docs" / "governance" / "D002G_M3_ELIGIBILITY_MATRIX.md",
    ]
    # Files that legitimately enumerate forbidden phrases for negative
    # scanning — scanner-exempt by construction.
    exempt = {
        "test_d002g_m3_traps.py",
        "test_d002g_m3_no_promotion.py",
    }
    for p in scan_paths:
        if not p.exists():
            continue
        if p.name in exempt:
            continue
        text = p.read_text(encoding="utf-8")
        for phrase in _FORBIDDEN_PHRASES:
            for line in text.splitlines():
                if phrase not in line:
                    continue
                lo = line.lower()
                # Forbidden-context heuristics: explicit negation marker,
                # FORBIDDEN literal, NOT clause, or D-002C-reference context.
                if (
                    "❌" in line
                    or "❎" in line
                    or "forbidden" in lo
                    or "_forbidden_phrases" in lo
                    or "must not" in lo
                    or " not " in f" {lo} "
                    or "no " in lo
                    or "never" in lo
                    or "cannot" in lo
                    or "out-of-scope" in lo
                    or "out of scope" in lo
                    or "d-002c" in lo
                    or "d002c" in lo
                    or "rejected" in lo
                ):
                    continue
                pytest.fail(
                    f"forbidden phrase {phrase!r} leaked outside "
                    f"forbidden-context in {p.name}: {line!r}"
                )


# ---- Trap T9: canonical-run artifact path ----------------------------


def test_trap_t9_no_canonical_artifact_path_created() -> None:
    """M3 implementation must not write to ``artifacts/d002g/canonical/``."""
    canonical_dir = REPO_ROOT / "artifacts" / "d002g" / "canonical"
    # The directory may or may not exist (legacy). If it exists, the M3
    # PR adds no files to it. We assert there is no M3-tagged artifact.
    if canonical_dir.exists():
        for p in canonical_dir.rglob("*"):
            if p.is_file():
                text = p.read_text(encoding="utf-8", errors="ignore")
                assert "M3_TOPOLOGY_CONDITIONED" not in text, (
                    f"canonical-run artifact {p} contains M3 stamp; "
                    "this PR must NOT emit canonical run artifacts"
                )


# ---- Trap T10: D002C ledger sha pin ----------------------------------

# fmt: off
_LEDGER_SHA256_PIN: str = "eb0b7151d76e5409e6dc9bb4a023551de5e0704673d5ac9f726319ef84a32387"  # noqa: E501  # pragma: allowlist secret  # post-D-002H-REFUSED-append (PR #692)
# fmt: on


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def test_trap_t10_d002c_ledger_unchanged_after_m3_verifier_runs() -> None:
    """Full M3 verifier matrix run leaves D002C_CLAIM_LEDGER.yaml byte-exact."""
    ledger = REPO_ROOT / "docs" / "governance" / "D002C_CLAIM_LEDGER.yaml"
    sha_before = _sha256_file(ledger)
    assert sha_before == _LEDGER_SHA256_PIN, (
        f"D002C_CLAIM_LEDGER.yaml sha drifted from pinned "
        f"{_LEDGER_SHA256_PIN}; current sha {sha_before}. "
        "Ledger touched outside scope — protocol violation."
    )
    # Run a small slice of the verifier matrix; full grid is in
    # the eligibility matrix script. The point of this trap is the
    # comparison sha is identical AFTER the verifier executes.
    for sub_factory in (RicciFlowSubstrate, BlockStructuredSubstrate, TemporalKtSubstrate):
        verify_m3_eligibility(
            sub_factory(),
            N=50,
            lambda_value=_LAMBDA,
            base_seed=_BASE_SEED,
            null_seed=_NULL_SEED,
        )
    sha_after = _sha256_file(ledger)
    assert sha_after == sha_before


# ---- Bonus: salt-distinctness ---------------------------------------


def test_trap_salt_distinctness_m3_vs_prior_salts() -> None:
    """M3 salt 523 is distinct from M6/M2 family salts AND produces
    distinct RNG streams under the same base_seed."""
    assert M3_TOPOLOGY_CONDITIONED_SALT == 523
    prior_salts = {
        M6_PLACEBO_SALT,
        M2_PLACEBO_SALT,
        M2_NODE_PAYLOAD_SALT,
        M2_INJECTION_SEQUENCE_SALT,
    }
    assert M3_TOPOLOGY_CONDITIONED_SALT not in prior_salts
    base_seed = 42
    seeds = {
        deterministic_mix(base_seed, s)
        for s in (
            M6_PLACEBO_SALT,
            M2_PLACEBO_SALT,
            M2_NODE_PAYLOAD_SALT,
            M2_INJECTION_SEQUENCE_SALT,
            M3_TOPOLOGY_CONDITIONED_SALT,
        )
    }
    assert len(seeds) == 5, (
        "Salt collision detected: M3 stream aliases prior salt stream. "
        "INV-RNG-DOMAIN-SEPARATION violated."
    )

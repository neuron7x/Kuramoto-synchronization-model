# SPDX-License-Identifier: MIT
"""Construct-validity guards for CTC-FALSIFY-001 L2.

The eight self-audit fixes are enforced here as executable invariants, not
prose: standardized residual estimand, jointly-matched surrogate, in-situ
positive control, no kill pre-data, symmetric terminal thresholds, SSOT.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from research.ctc_falsify import config as l1
from research.ctc_falsify.generative import draw_n_plus
from research.ctc_falsify.l2 import config_l2 as cfg
from research.ctc_falsify.l2.gates_l2 import L2SelfValidation, decide_l2, run_self_validation
from research.ctc_falsify.l2.residual import standardized_residual
from research.ctc_falsify.l2.run import run
from research.ctc_falsify.l2.surrogate import build_joint_surrogate

# Heavy: 24 seeds x 4 conditions x 200 surrogates x PLV. Runs in the
# python-heavy-tests gate, NOT the 20-min python-fast-tests cap
# (pre-registered constants are NOT reduced — that would be a #199 rescue).
pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def selfval() -> L2SelfValidation:
    return run_self_validation()


@pytest.fixture(scope="module")
def result() -> dict[str, object]:
    return run()


def test_result_validates_against_schema(result: dict[str, object]) -> None:
    schema = json.loads(cfg.SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_schema_enum_is_single_source() -> None:
    schema = json.loads(cfg.SCHEMA_PATH.read_text())
    assert tuple(schema["properties"]["verdict"]["enum"]) == cfg.ALL_VERDICTS


def test_pre_data_verdict_is_fail_closed_inadmissible(result: dict[str, object]) -> None:
    assert str(result["verdict"]).startswith("INADMISSIBLE")
    assert result["real_dataset_bound"] is False
    assert result["verdict"] in cfg.ALL_VERDICTS


def test_no_kill_or_survival_reachable_pre_data(selfval: L2SelfValidation) -> None:
    """No KILLED/SURVIVED while pre-data — even if the data flag is forced."""
    for flag in (False, True):
        v = decide_l2(selfval, real_dataset_bound=flag)
        assert v not in (cfg.VERDICT_KILLED_SCOPED, cfg.VERDICT_SURVIVED_INITIAL)
        assert v.startswith("INADMISSIBLE")


def test_c3_path_unreachable_only_when_estimator_admissible() -> None:
    """The C3 (real-data) branch raises NotImplemented ONLY after the
    estimator passes self-validation — it is gated behind admissibility."""
    passing = L2SelfValidation(
        surrogate_all_matched=True,
        mean_nplus_residual_z=cfg.NPLUS_RESIDUAL_MIN_Z + 1.0,
        max_confound_residual_z=0.0,
        nplus_recovered=True,
        confounds_not_flagged=True,
        n_validation_seeds=cfg.N_VALIDATION_SEEDS,
        worst_rate_rel_err=0.0,
        worst_power_rel_err=0.0,
    )
    assert decide_l2(passing, real_dataset_bound=False) == cfg.VERDICT_INADMISSIBLE_NO_PAIRED_DATA
    with pytest.raises(NotImplementedError):
        decide_l2(passing, real_dataset_bound=True)


def test_joint_surrogate_matches_rate_and_power() -> None:
    """Fix #2: surrogate must match BOTH rate and power within tolerance,
    and must destroy the true phase channel (residual collapses on its own
    surrogate)."""
    sig = draw_n_plus(l1.SEED)
    batch = build_joint_surrogate(sig, l1.SEED)
    assert batch.rate_rel_err <= cfg.RATE_MATCH_TOL
    assert batch.power_rel_err <= cfg.SNR_MATCH_TOL
    assert batch.surrogate_b.shape == (cfg.N_SURROGATE, sig.sig_b.shape[0])


def test_reference_estimator_is_blind_and_fails_closed(
    selfval: L2SelfValidation, result: dict[str, object]
) -> None:
    """Honest reference state (no post-hoc tuning to escape it): the v1
    phase-randomization residual estimator does NOT clear its own
    pre-registered positive-control gate, so the verdict is the fail-closed
    INADMISSIBLE_NPLUS_INSITU_BLIND. A non-blind estimator is the open
    problem that must be solved BEFORE C3 binds any real data."""
    assert selfval.surrogate_all_matched is True
    blind = (
        selfval.mean_nplus_residual_z < cfg.NPLUS_RESIDUAL_MIN_Z
        or selfval.max_confound_residual_z > cfg.CONFOUND_RESIDUAL_MAX_Z
    )
    assert blind, "estimator unexpectedly admissible — re-pre-register before claiming recovery"
    assert result["verdict"] == cfg.VERDICT_INADMISSIBLE_NPLUS_INSITU_BLIND
    # standardized residual is finite and well-formed regardless
    r = standardized_residual(draw_n_plus(l1.SEED), l1.SEED)
    assert r.matched is True
    assert r.surrogate_std > 0.0


def test_blind_estimator_gate_precedes_data(selfval: L2SelfValidation) -> None:
    blind = L2SelfValidation(
        surrogate_all_matched=True,
        mean_nplus_residual_z=0.0,
        max_confound_residual_z=0.0,
        nplus_recovered=False,
        confounds_not_flagged=True,
        n_validation_seeds=selfval.n_validation_seeds,
        worst_rate_rel_err=0.0,
        worst_power_rel_err=0.0,
    )
    assert decide_l2(blind) == cfg.VERDICT_INADMISSIBLE_NPLUS_INSITU_BLIND


def test_surrogate_mismatch_gate_is_first(selfval: L2SelfValidation) -> None:
    mismatch = L2SelfValidation(
        surrogate_all_matched=False,
        mean_nplus_residual_z=99.0,
        max_confound_residual_z=0.0,
        nplus_recovered=True,
        confounds_not_flagged=True,
        n_validation_seeds=selfval.n_validation_seeds,
        worst_rate_rel_err=1.0,
        worst_power_rel_err=1.0,
    )
    assert decide_l2(mismatch) == cfg.VERDICT_INADMISSIBLE_SURROGATE_MISMATCH


def test_symmetric_terminal_thresholds() -> None:
    """Fix #8: KILLED and SURVIVED use the SAME alpha and the SAME delta."""
    assert cfg.SYMMETRIC_ALPHA == cfg.HOLM_ALPHA
    assert cfg.SYMMETRIC_DELTA == cfg.PRIMARY_ENDPOINT_DELTA


def test_repro_hash_binds_verdict(result: dict[str, object]) -> None:
    import hashlib

    payload = {
        "verdict": "SURVIVED_INITIAL",
        "config_hash": result["config_hash"],
        "self_validation": result["self_validation"],
    }
    mutated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert mutated != result["repro_hash"]


def test_config_is_single_source() -> None:
    import research.ctc_falsify.l2.config_l2 as ssot
    import research.ctc_falsify.l2.run as run_mod

    for name in ("Z_GATE", "N_SURROGATE", "NPLUS_RESIDUAL_MIN_Z", "MIN_SESSIONS"):
        assert not hasattr(run_mod, name), f"{name} duplicated outside config_l2"
    assert ssot is cfg

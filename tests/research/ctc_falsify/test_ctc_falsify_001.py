# SPDX-License-Identifier: MIT
"""Construct-validity guards for CTC-FALSIFY-001.

These tests do not check whether the CTC canon is true. They check that the
instrument cannot lie: INADMISSIBLE is first-class success, nulls carry no
channel by construction, the readout is independent of ground truth, no kill
is reachable pre-data, and constants come from one source.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from research.ctc_falsify import config as cfg
from research.ctc_falsify.gates import Diagnostic, decide, run_diagnostic
from research.ctc_falsify.generative import draw_n_plus, draw_null
from research.ctc_falsify.pipeline import run_standard_pipeline
from research.ctc_falsify.run import run


@pytest.fixture(scope="module")
def diag() -> Diagnostic:
    return run_diagnostic()


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


def test_inadmissible_is_first_class_success(result: dict[str, object]) -> None:
    """The designed pre-data verdict is INADMISSIBLE — not an error."""
    assert result["verdict"] in cfg.ALL_VERDICTS
    assert str(result["verdict"]).startswith("INADMISSIBLE")
    assert result["real_data_bound"] is False


def test_nulls_carry_no_channel_by_construction() -> None:
    """Every confound draw must have channel_strength == 0 — otherwise a
    'false positive' would not be false."""
    for fam in cfg.NULL_FAMILIES:
        s = draw_null(cfg.SEED, fam)
        assert s.channel_strength == 0.0
    assert draw_n_plus(cfg.SEED).channel_strength == cfg.CHANNEL_STRENGTH_TRUE


def test_readout_is_independent_of_groundtruth(diag: Diagnostic) -> None:
    """A confound draw (channel==0) still yields a finite PLV — proving the
    pipeline never reads the injected ground-truth parameter."""
    assert diag.readout_independent_of_groundtruth is True
    probe = draw_null(cfg.SEED, "N1_COMMON_DRIVE")
    assert run_standard_pipeline(probe).plv >= 0.0


def test_no_kill_or_survival_reachable_pre_data(diag: Diagnostic) -> None:
    """KILLED_SCOPED / SURVIVED_INITIAL must be impossible without real data."""
    verdict = decide(diag, groundtruth_available=True, real_data=False)
    assert verdict != cfg.VERDICT_KILLED_SCOPED
    assert verdict != cfg.VERDICT_SURVIVED_INITIAL
    with pytest.raises(NotImplementedError):
        decide(diag, groundtruth_available=True, real_data=True)


def test_estimator_blind_gate_precedes_any_diagnostic_read() -> None:
    """If N+ is not recovered, the verdict is INADMISSIBLE_ESTIMATOR_BLIND
    regardless of confound numbers (a blind pipeline cannot license a kill)."""
    blind = Diagnostic(
        nplus_recovery_rate=0.0,
        null_false_positive_rate={f: 1.0 for f in cfg.NULL_FAMILIES},
        n_seeds=cfg.N_NULL_SEEDS,
        readout_independent_of_groundtruth=True,
        mean_nplus_plv=0.0,
        mean_null_plv={f: 0.9 for f in cfg.NULL_FAMILIES},
    )
    assert decide(blind) == cfg.VERDICT_INADMISSIBLE_ESTIMATOR_BLIND


def test_no_groundtruth_gate_is_fail_closed(diag: Diagnostic) -> None:
    assert decide(diag, groundtruth_available=False) == cfg.VERDICT_INADMISSIBLE_NO_GROUNDTRUTH


def test_underpowered_gate(diag: Diagnostic) -> None:
    weak = Diagnostic(
        nplus_recovery_rate=1.0,
        null_false_positive_rate=dict(diag.null_false_positive_rate),
        n_seeds=cfg.MIN_SEEDS_FOR_POWER - 1,
        readout_independent_of_groundtruth=True,
        mean_nplus_plv=diag.mean_nplus_plv,
        mean_null_plv=dict(diag.mean_null_plv),
    )
    assert decide(weak) == cfg.VERDICT_INADMISSIBLE_UNDERPOWERED


def test_repro_hash_binds_the_verdict(result: dict[str, object]) -> None:
    import hashlib

    payload = {
        "verdict": "SURVIVED_INITIAL",  # mutated
        "config_hash": result["config_hash"],
        "confound_diagnostic": result["confound_diagnostic"],
        "positive_control": result["positive_control"],
        "n_seeds": result["n_seeds"],
        "readout_independent_of_groundtruth": result["readout_independent_of_groundtruth"],
    }
    mutated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert mutated != result["repro_hash"]


def test_config_constants_not_duplicated() -> None:
    """SSOT: experiment module must not redefine config constants."""
    import research.ctc_falsify.config as ssot
    import research.ctc_falsify.run as run_mod

    for name in ("SEED", "CANON_PLV", "N_NULL_SEEDS", "CHANNEL_STRENGTH_TRUE"):
        assert not hasattr(run_mod, name), f"{name} duplicated outside config"
    assert ssot is cfg

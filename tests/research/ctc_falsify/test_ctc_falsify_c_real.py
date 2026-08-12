# SPDX-License-Identifier: MIT
"""C-real prereg construct-validity guards (fast lane).

Enforces: fail-closed pre-data verdict, the gate is a pure function of
the admissibility booleans, no KILLED/SURVIVED reachable without a bound
dataset + an INDEPENDENT routing label + P-replication + power, schema
and SSOT integrity. No data is touched.
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from research.ctc_falsify.c_real import config_c_real as cr
from research.ctc_falsify.c_real.gate import decide
from research.ctc_falsify.c_real.run import run


def test_schema_validates_and_enum_is_single_source() -> None:
    schema = json.loads(cr.SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    result = run()
    Draft202012Validator(schema).validate(result)
    assert tuple(schema["properties"]["verdict"]["enum"]) == cr.ALL_VERDICTS


def test_pre_data_verdict_is_fail_closed() -> None:
    r = run()
    assert r["verdict"] == cr.VERDICT_NO_PAIRED_DATA
    assert r["dataset_bound"] is False
    assert r["estimator"] == "c5_full_gamma_cross_spectral_discriminant"


def test_gate_ordering_is_fail_closed() -> None:
    assert decide(dataset_bound=False) == cr.VERDICT_NO_PAIRED_DATA
    assert decide(dataset_bound=True, independent_label=False) == cr.VERDICT_NO_INDEPENDENT_LABEL
    assert (
        decide(dataset_bound=True, independent_label=True, p_replicates=False)
        == cr.VERDICT_DATASET_UNSUITABLE
    )
    assert (
        decide(
            dataset_bound=True,
            independent_label=True,
            p_replicates=True,
            powered=False,
        )
        == cr.VERDICT_UNDERPOWERED
    )


def test_no_terminal_verdict_without_full_admissibility() -> None:
    """KILLED/SURVIVED need the conjunction; missing oos_auc raises."""
    with pytest.raises(NotImplementedError):
        decide(
            dataset_bound=True,
            independent_label=True,
            p_replicates=True,
            powered=True,
            oos_auc=None,
        )


def test_terminal_branches_match_pre_stated_forecast() -> None:
    full = dict(dataset_bound=True, independent_label=True, p_replicates=True, powered=True)
    assert decide(**full, oos_auc=cr.AUC_SUPPORT_MIN) == cr.VERDICT_SURVIVED_INITIAL
    assert decide(**full, oos_auc=cr.AUC_CHANCE_HI) == cr.VERDICT_KILLED_SCOPED
    with pytest.raises(NotImplementedError):  # inconclusive band, no forced call
        decide(**full, oos_auc=(cr.AUC_CHANCE_HI + cr.AUC_SUPPORT_MIN) / 2.0)


def test_scalar_estimands_are_rejected_by_pre_registration() -> None:
    """C5 settled it: the pre-committed estimator is the full
    cross-spectral discriminant, never the blind scalar estimands."""
    assert "scalar" not in cr.ESTIMATOR
    assert cr.ESTIMATOR.startswith("c5_full_gamma_cross_spectral")


def test_repro_hash_binds_verdict() -> None:
    import hashlib

    r = run()
    mutated = hashlib.sha256(
        json.dumps(
            {
                "verdict": "SURVIVED_INITIAL",
                "config_hash": r["config_hash"],
                "dataset_bound": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert mutated != r["repro_hash"]

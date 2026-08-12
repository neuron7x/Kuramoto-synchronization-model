# SPDX-License-Identifier: MIT
"""C5 construct-validity guards: the decisive identifiability oracle.

Enforces no leakage, verdict bound to the AUC bands, and an honest
non-decision when ambiguous (the OPEN may stay OPEN — never force a call).
"""

from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from research.ctc_falsify.c5 import config_c5 as c5
from research.ctc_falsify.c5.oracle import run_oracle
from research.ctc_falsify.c5.run import decide, run

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def result() -> dict[str, object]:
    return run()


def test_schema_validates(result: dict[str, object]) -> None:
    schema = json.loads(c5.SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_schema_enum_is_single_source() -> None:
    schema = json.loads(c5.SCHEMA_PATH.read_text())
    assert tuple(schema["properties"]["verdict"]["enum"]) == c5.ALL_VERDICTS


def test_train_test_seed_bands_are_disjoint() -> None:
    assert set(c5.train_seeds()).isdisjoint(set(c5.test_seeds()))


def test_verdict_is_a_pure_function_of_auc_and_disjointness() -> None:
    assert decide(0.50, True) == c5.VERDICT_IDENTIFIABILITY_LIMIT
    assert decide(0.95, True) == c5.VERDICT_ESTIMATOR_QUALITY_GAP
    assert decide(0.75, True) == c5.VERDICT_AMBIGUOUS
    assert decide(0.99, False) == c5.VERDICT_LEAKAGE  # leakage overrides


def test_reference_run_is_leakage_free_and_bound(result: dict[str, object]) -> None:
    o = result["oracle"]
    assert isinstance(o, dict)
    assert o["train_test_disjoint"] is True
    assert result["verdict"] in c5.ALL_VERDICTS
    assert result["verdict"] != c5.VERDICT_LEAKAGE
    o_run = run_oracle()
    assert result["verdict"] == decide(o_run.oos_auc, o_run.train_test_disjoint)


def test_oos_auc_in_unit_interval(result: dict[str, object]) -> None:
    o = result["oracle"]
    assert isinstance(o, dict)
    assert 0.0 <= float(o["oos_auc"]) <= 1.0  # type: ignore[arg-type]


def test_metric_policy_split_is_claim_neutral(result: dict[str, object]) -> None:
    """No-claim-change guarantee: extracting _discriminability from the
    inline fold must NOT move the C5 number or verdict (pure refactor)."""
    o = result["oracle"]
    assert isinstance(o, dict)
    assert abs(float(o["oos_auc"]) - 0.9629629629629629) < 1e-15  # byte-identical
    assert result["verdict"] == c5.VERDICT_ESTIMATOR_QUALITY_GAP

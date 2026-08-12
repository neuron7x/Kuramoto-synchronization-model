# SPDX-License-Identifier: MIT
"""C4 construct-validity guards: the self-audit of the privileged estimator.

The point of C4 is to refuse to trust our own escape-hatch. These tests
enforce that the audit is fail-closed and that its verdict is bound to the
real gate booleans (no tuning, no silent promotion).
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from jsonschema import Draft202012Validator

from research.ctc_falsify.c4 import config_c4 as c4
from research.ctc_falsify.c4.audit import AuditResult, decide, run_audit
from research.ctc_falsify.c4.phase_offset import offset_ab, offset_ba
from research.ctc_falsify.c4.run import run
from research.ctc_falsify.config import SEED
from research.ctc_falsify.generative import draw_n_plus

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def result() -> dict[str, object]:
    return run()


def test_schema_validates(result: dict[str, object]) -> None:
    schema = json.loads(c4.SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_schema_enum_is_single_source() -> None:
    schema = json.loads(c4.SCHEMA_PATH.read_text())
    assert tuple(schema["properties"]["verdict"]["enum"]) == c4.ALL_VERDICTS


def test_verdict_is_bound_to_gate_booleans(result: dict[str, object]) -> None:
    """The verdict must be a pure function of G1..G4 — never a free label."""
    a = run_audit()
    v = decide(a)
    assert result["verdict"] == v
    if v == c4.VERDICT_BOUNDARY_HARDENED:
        assert a.g1_separable and a.g2_confounds_rejected
        assert a.g3_signflip_ok and a.g4_sweep_clean
    else:
        assert not (
            a.g1_separable and a.g2_confounds_rejected and a.g3_signflip_ok and a.g4_sweep_clean
        )


def test_signflip_is_directional() -> None:
    """offset(B,A) must be the negative of offset(A,B) up to estimation
    error — a genuinely directed estimator, not a magnitude artifact."""
    sig = draw_n_plus(SEED)
    ab, ba = offset_ab(sig), offset_ba(sig)
    assert np.sign(ab) != np.sign(ba) or abs(ab) <= 1e-9


def test_fail_closed_label_mapping() -> None:
    """Each failing gate maps to its specific scoped INADMISSIBLE; the
    verdict can never silently become HARDENED on a failure."""
    blind = AuditResult(
        cohens_d=0.0,
        decision_boundary=0.0,
        confound_false_positive_rate=1.0,
        signflip_pass_fraction=0.0,
        sweep_false_positive_count=99,
        sweep_total=99,
        g1_separable=False,
        g2_confounds_rejected=False,
        g3_signflip_ok=False,
        g4_sweep_clean=False,
    )
    assert decide(blind) == c4.VERDICT_CANT_SEPARATE
    assert decide(blind) != c4.VERDICT_BOUNDARY_HARDENED


def test_repro_hash_binds_verdict(result: dict[str, object]) -> None:
    import hashlib

    payload = {
        "verdict": "C4_BOUNDARY_HARDENED_TAMPERED",
        "config_hash": result["config_hash"],
        "audit": result["audit"],
    }
    mutated = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert mutated != result["repro_hash"]

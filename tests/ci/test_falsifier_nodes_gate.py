"""Teeth for the falsifier-node gate: a fake test_id must NOT resolve; a real one must."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "cfn", Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check_falsifier_nodes.py"
)
cfn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cfn)


def test_fake_node_does_not_resolve():
    ok, why = cfn._resolves(
        "tests/unit/physics/test_T11_dopamine_algebraic.py::test_TOTALLY_FAKE_zzz"
    )
    assert ok is False and "rc=" in why


def test_missing_file_does_not_resolve():
    ok, why = cfn._resolves("tests/does_not_exist_zzz.py::test_x")
    assert ok is False and why == "file missing"


def test_real_node_resolves():
    ok, _ = cfn._resolves(
        "tests/unit/physics/test_T11_dopamine_algebraic.py::test_td_error_is_linear_in_reward"
    )
    assert ok is True


# NOTE: whole-registry greenness (cfn.main() == 0) is enforced by the
# `claim-falsifier-nodes` CI job, which runs the gate STANDALONE. It is
# deliberately NOT asserted here: main() shells 23 nested `pytest --collect-only`
# subprocesses, and running that from inside a pytest session makes the children
# inherit the parent's config/plugins, spuriously erroring a node. The three
# tests above prove the mechanism has teeth (fake/missing -> RED, real -> GREEN),
# which is the actual hole this gate closes.

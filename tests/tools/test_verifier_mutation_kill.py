# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G1 — the verifiers themselves are mutation-tested (the recursion closes).

Each verification tool ships one committed falsifier. A single witness does not
prove the tool's decision predicate is load-bearing — a dead predicate would still
pass its one falsifier. This harness mutates the CORE predicate of every verifier
and asserts the verdict flips: a surviving mutation would be dead code, an
untested branch in the verifier-of-verifiers. Zero survivors here means the
verifiers are defect-sensitive at their core, not just at one point.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path
from types import ModuleType
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]


def _load(source: str, name: str) -> ModuleType:
    # Write the (possibly mutated) source next to the real tool so its imports and
    # sibling-tool loads resolve, then import it by path — no exec of a string.
    with tempfile.NamedTemporaryFile(
        "w", suffix=".py", dir=str(ROOT / "tools"), delete=False, encoding="utf-8"
    ) as handle:
        handle.write(source)
        tmp = Path(handle.name)
    try:
        spec = importlib.util.spec_from_file_location(f"{name}_{tmp.stem}", tmp)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        tmp.unlink(missing_ok=True)


def _mutant(tool_rel: str, old: str, new: str, name: str) -> ModuleType:
    source = (ROOT / tool_rel).read_text(encoding="utf-8")
    assert old in source, f"mutation target absent in {tool_rel}: {old!r}"
    return _load(source.replace(old, new, 1), name)


def _original(tool_rel: str, name: str) -> ModuleType:
    return _load((ROOT / tool_rel).read_text(encoding="utf-8"), name)


def _assert_killed(tool_rel: str, old: str, new: str, name: str, probe: Callable[[Any], object]) -> None:
    base = probe(_original(tool_rel, name))
    mutated = probe(_mutant(tool_rel, old, new, name))
    assert base != mutated, (
        f"MUTATION SURVIVED in {tool_rel}: {old!r}->{new!r} did not change the "
        f"verdict ({base!r}); the predicate is dead / untested."
    )


def test_apex_conjunction_predicate_is_load_bearing() -> None:
    # act ⇔ H1∧H2∧H3∧H4 ; mutate ∧->∨ ; a single-False input must change the gate.
    _assert_killed(
        "tools/audit_no_ungrounded_act.py",
        "h1 and h2 and h3 and h4",
        "h1 or h2 or h3 or h4",
        "audit_no_ungrounded_act",
        lambda m: m.act_admissible(h1=True, h2=True, h3=True, h4=False),
    )


def test_aggregator_all_predicate_is_load_bearing(tmp_path: Path) -> None:
    # build_verdict uses all(passed); mutate all->any ; one failing input flips it.
    def _probe(module: ModuleType) -> object:
        for spec in module.INPUTS:
            if spec["tier"] != "substrate":
                continue
            p = tmp_path / spec["path"]
            p.parent.mkdir(parents=True, exist_ok=True)
            verdict = "FAIL" if spec["name"] == "concurrency_matrix" else "PASS"
            p.write_text(json.dumps({"schema": module._SCHEMA_IDS[spec["name"]], "verdict": verdict}))
        return module.build_verdict(tmp_path, release=False)["verdict"]

    _assert_killed(
        "tools/audit_final_inference_verdict.py",
        'all(e["passed"] for e in entries)',
        'any(e["passed"] for e in entries)',
        "audit_final_inference_verdict",
        _probe,
    )


def test_lyapunov_hurwitz_predicate_is_load_bearing() -> None:
    # Mutate the Hurwitz test (real part < 0) to (> 0): all-negative eigenvalues fail it.
    _assert_killed(
        "tools/audit_opponency_lyapunov.py",
        "eigenvalues.real < 0.0",
        "eigenvalues.real > 0.0",
        "audit_opponency_lyapunov",
        lambda m: m.build_certificate()["gate"],
    )


def test_kuramoto_transition_predicate_is_load_bearing() -> None:
    # Mutate the phase-transition gap test (>=) to (<=): a real 0.74 gap now fails.
    _assert_killed(
        "tools/audit_kuramoto_synchrony.py",
        "(r_high - r_low) >= _TRANSITION_GAP",
        "(r_high - r_low) <= _TRANSITION_GAP",
        "audit_kuramoto_synchrony",
        lambda m: m.build_certificate()["gate"],
    )


def test_homeostasis_gate_conjunction_is_load_bearing() -> None:
    # Mutate the No-Ungrounded-Act gate ∧->∨ ; a below-threshold coherence flips GO.
    _assert_killed(
        "tools/audit_homeostasis_contract.py",
        "allostatic_bounded and params_admissible and coherence >= r_min",
        "allostatic_bounded or params_admissible and coherence >= r_min",
        "audit_homeostasis_contract",
        lambda m: m.no_ungrounded_act(
            allostatic_bounded=True, params_admissible=False, coherence=1.0, r_min=0.9
        ),
    )

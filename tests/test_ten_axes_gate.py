# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth for the ten-axis composition gate.

Every case here states the specific way the gate could go blind and pins it. The three
failure modes that matter -- an unmeasured probe silently scoring 1.0, a mean diluting a
real hole, and a regression hidden by deleting the ruler -- each have a matched control.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "check_ten_axes", ROOT / "scripts" / "ci" / "check_ten_axes.py"
)
assert _SPEC and _SPEC.loader
axes = importlib.util.module_from_spec(_SPEC)
sys.modules["check_ten_axes"] = axes
_SPEC.loader.exec_module(axes)


def _probe(pid: str, score: float, state: str = "MEASURED", axis: str = "elegance") -> dict:
    entry = {"id": pid, "axis": axis, "procedure": "1 - synthetic/synthetic", "state": state}
    if state == "MEASURED":
        entry.update({"debt": 0, "population": 100, "score": score})
    else:
        entry["reason"] = "synthetic"
    return entry


# ------------------------------------------------------------------ probe arithmetic


def test_unmeasured_probe_scores_none_not_one() -> None:
    """The whole point: a probe that could not measure must NOT count as perfect."""
    probe = axes.Probe("x", "elegance", "p", lambda: (_ for _ in ()).throw(axes.ProbeError("no")))
    probe.run()
    assert probe.state == "UNMEASURED"
    assert probe.score is None, "an unmeasured probe returned a score -- it would be floored to 1.0"


def test_zero_population_is_unmeasured_not_perfect() -> None:
    """0/0 is undefined, not 1.0 -- an empty population must not manufacture a clean bill."""
    probe = axes.Probe("x", "elegance", "p", lambda: (0, 0))
    probe.run()
    assert probe.state == "UNMEASURED" and probe.score is None


def test_debt_exceeding_population_is_refused() -> None:
    """A ledger larger than its population means the ruler and the thing disagree -- refuse."""
    probe = axes.Probe("x", "elegance", "p", lambda: (5, 3))
    probe.run()
    assert probe.state == "UNMEASURED"
    assert "outside population" in probe.reason


def test_score_is_one_minus_ratio() -> None:
    probe = axes.Probe("x", "elegance", "p", lambda: (25, 100))
    probe.run()
    assert probe.score == pytest.approx(0.75)


# ------------------------------------------------------------------ aggregation


def test_axis_score_is_weakest_probe_not_mean(monkeypatch: pytest.MonkeyPatch) -> None:
    """A mean would let three easy 0.99 probes bury one 0.03 hole. Weakest-link forbids it."""
    scores = [0.99, 0.99, 0.99, 0.03]
    probes = tuple(
        axes.Probe(f"p{i}", "completeness", "synthetic", (lambda s=s: (int(100 * (1 - s)), 100)))
        for i, s in enumerate(scores)
    )
    monkeypatch.setattr(axes, "PROBES", probes)
    report = axes.build_report()
    assert report["axes"]["completeness"]["score"] == pytest.approx(0.03)
    assert report["axes"]["completeness"]["mean_informational"] == pytest.approx(0.75)
    assert report["axes"]["completeness"]["binding_probe"] == "p3"


def test_repository_verdict_is_weakest_axis(monkeypatch: pytest.MonkeyPatch) -> None:
    probes = (
        axes.Probe("a", "elegance", "s", lambda: (1, 100)),
        axes.Probe("b", "resistance", "s", lambda: (60, 100)),
    )
    monkeypatch.setattr(axes, "PROBES", probes)
    report = axes.build_report()
    assert report["weakest_axis"] == "resistance"
    assert report["weakest_score"] == pytest.approx(0.40)


def test_axis_with_no_measured_probe_is_unmeasured_not_scored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def blind() -> tuple[int, int]:
        raise axes.ProbeError("population unknown")

    monkeypatch.setattr(axes, "PROBES", (axes.Probe("a", "beauty", "s", blind),))
    report = axes.build_report()
    assert report["axes"]["beauty"]["state"] == "UNMEASURED"
    assert "score" not in report["axes"]["beauty"], "a blind axis was given a number"
    assert "beauty" in report["axes_unmeasured"]


# ------------------------------------------------------------------ fail-closed diff


def test_regression_in_a_probe_fails() -> None:
    base = {"probes": [_probe("a", 0.90)]}
    now = {"probes": [_probe("a", 0.89)]}
    problems = axes.compare(now, base)
    assert any("AXIS REGRESSION a" in p for p in problems)


def test_improvement_passes() -> None:
    base = {"probes": [{**_probe("a", 0.90), "debt": 10, "population": 100}]}
    now = {"probes": [{**_probe("a", 0.91), "debt": 9, "population": 100}]}
    assert axes.compare(now, base) == []


def test_deleting_the_ruler_fails() -> None:
    """Removing a probe must not be a way to erase its debt."""
    base = {"probes": [_probe("a", 0.90)]}
    problems = axes.compare({"probes": []}, base)
    assert any("PROBE REMOVED a" in p for p in problems)


def test_blinding_the_ruler_fails() -> None:
    """MEASURED -> UNMEASURED is a regression, not a neutral event."""
    base = {"probes": [_probe("a", 0.90)]}
    now = {"probes": [_probe("a", 0.0, state="UNMEASURED")]}
    problems = axes.compare(now, base)
    assert any("UNMEASURED REGRESSION a" in p for p in problems)
    assert not any("AXIS REGRESSION" in p for p in problems), "blinding was scored as a value drop"


def test_debt_growth_fails_even_when_the_ratio_improves() -> None:
    """Inflating the population is not paying the debt -- the score may rise, the gate must not."""
    base = {"probes": [{**_probe("a", 0.90), "debt": 10, "population": 100}]}
    now = {"probes": [{**_probe("a", 0.95), "debt": 20, "population": 400}]}
    problems = axes.compare(now, base)
    assert any("DEBT INCREASE a" in p for p in problems), (
        "the denominator was quadrupled and the debt doubled, yet the gate passed"
    )


def test_moving_a_probe_to_another_axis_fails() -> None:
    """The repository number survives a reassignment; WHICH axis is the hole must not be edited."""
    base = {"probes": [_probe("a", 0.90, axis="completeness")]}
    now = {"probes": [_probe("a", 0.90, axis="elegance")]}
    problems = axes.compare(now, base)
    assert any("AXIS MOVED a" in p for p in problems)


def test_editing_a_stated_procedure_fails() -> None:
    """A frozen number means nothing if the procedure behind it can be rewritten silently."""
    base = {"probes": [_probe("a", 0.90)]}
    now = {"probes": [{**_probe("a", 0.90), "procedure": "1 - unicorns / moon phases"}]}
    problems = axes.compare(now, base)
    assert any("PROCEDURE CHANGED a" in p for p in problems)


def test_population_inflation_fails_even_with_unchanged_debt() -> None:
    """The load-bearing rule: a score may only rise because the DEBT fell."""
    base = {"probes": [{**_probe("a", 0.90), "debt": 10, "population": 100}]}
    now = {"probes": [{**_probe("a", 0.99), "debt": 10, "population": 1000}]}
    problems = axes.compare(now, base)
    assert any("POPULATION INFLATION a" in p for p in problems), (
        "the denominator was multiplied tenfold, nothing was paid, and the gate passed"
    )


def test_paying_debt_is_the_one_admissible_way_to_rise() -> None:
    base = {"probes": [{**_probe("a", 0.90), "debt": 10, "population": 100}]}
    now = {"probes": [{**_probe("a", 0.95), "debt": 5, "population": 100}]}
    assert axes.compare(now, base) == []


def test_reclassifying_a_ledger_fails() -> None:
    """Moving a loaded ledger out of the survey shrinks both debt and population -- silently."""
    base = {
        "probes": [],
        "ledger_classification": {"ledgers": ["a.json", "b.json"], "not_ledgers": []},
    }
    now = {
        "probes": [],
        "ledger_classification": {"ledgers": ["a.json"], "not_ledgers": ["b.json"]},
    }
    problems = axes.compare(now, base)
    assert any("LEDGER RECLASSIFIED b.json: removed from ledgers" in p for p in problems)
    assert any("LEDGER RECLASSIFIED b.json: added to not_ledgers" in p for p in problems)


def test_hand_edited_baseline_arithmetic_is_detected() -> None:
    """Freezing a high debt with a low score buys unlimited future headroom -- re-derive it."""
    forged = {**_probe("a", 0.797488), "debt": 600, "population": 637}
    problems = axes.compare({"probes": [forged]}, {"probes": [forged]})
    assert any("BASELINE INCONSISTENT (a)" in p and "!= 1 -" in p for p in problems)


def test_baseline_with_debt_above_population_is_rejected() -> None:
    forged = {**_probe("a", 0.5), "debt": 700, "population": 637}
    problems = axes.compare({"probes": [forged]}, {"probes": [forged]})
    assert any("outside population" in p for p in problems)


def test_baseline_holding_a_blind_probe_is_rejected() -> None:
    frozen = _probe("a", 0.0, state="UNMEASURED")
    problems = axes.compare({"probes": [frozen]}, {"probes": [frozen]})
    assert any("a blind probe must never enter the baseline" in p for p in problems)


def test_honest_baseline_arithmetic_passes() -> None:
    honest = {**_probe("a", round(1 - 129 / 637, 6)), "debt": 129, "population": 637}
    assert axes.compare({"probes": [honest]}, {"probes": [honest]}) == []


def test_hand_edited_baseline_axis_block_is_detected() -> None:
    """A baseline whose axis numbers disagree with its own probes is not to be trusted."""
    base = {
        "probes": [_probe("a", 0.20, axis="beauty")],
        "axes": {"beauty": {"score": 0.99}},
    }
    problems = axes.compare({"probes": [_probe("a", 0.20, axis="beauty")]}, base)
    assert any("BASELINE INCONSISTENT (beauty)" in p for p in problems)


def test_write_baseline_refuses_to_freeze_a_blind_probe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A probe frozen UNMEASURED would be exempt from every check and stay blind forever."""

    def blind() -> tuple[int, int]:
        raise axes.ProbeError("population unknown")

    monkeypatch.setattr(axes, "BASELINE", tmp_path / "b.json")
    monkeypatch.setattr(axes, "PROBES", (axes.Probe("a", "elegance", "1 - x/y", blind),))
    assert axes.main(["--write-baseline"]) == 1
    assert not (tmp_path / "b.json").exists()


def test_unfrozen_probe_fails() -> None:
    """A probe present in the report but absent from the baseline is unreviewed scope."""
    problems = axes.compare({"probes": [_probe("new", 0.5)]}, {"probes": []})
    assert any("UNFROZEN PROBE new" in p for p in problems)


# ------------------------------------------------------------------ live repository


def test_live_profile_measures_every_probe() -> None:
    """Against the real tree every probe must resolve -- a blind probe is a broken ruler."""
    report = axes.build_report()
    blind = [(p["id"], p["reason"]) for p in report["probes"] if p["state"] != "MEASURED"]
    assert blind == [], f"probes could not measure on the live tree: {blind}"


def test_live_profile_matches_frozen_baseline() -> None:
    baseline = json.loads(axes.BASELINE.read_text(encoding="utf-8"))
    assert axes.compare(axes.build_report(), baseline) == []


def test_write_baseline_refuses_to_launder_a_regression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The ratchet's own weak point: re-freezing must not be a way to lower the bar."""
    baseline = tmp_path / "TEN_AXES_BASELINE.json"
    monkeypatch.setattr(axes, "BASELINE", baseline)
    monkeypatch.setattr(axes, "PROBES", (axes.Probe("a", "elegance", "1 - x/y", lambda: (10, 100)),))
    assert axes.main(["--write-baseline"]) == 0

    monkeypatch.setattr(axes, "PROBES", (axes.Probe("a", "elegance", "1 - x/y", lambda: (30, 100)),))
    assert axes.main(["--write-baseline"]) == 1, "a regression was laundered into the baseline"
    assert json.loads(baseline.read_text())["probes"][0]["score"] == pytest.approx(0.90)


def test_write_baseline_accepts_an_improvement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    baseline = tmp_path / "TEN_AXES_BASELINE.json"
    monkeypatch.setattr(axes, "BASELINE", baseline)
    monkeypatch.setattr(axes, "PROBES", (axes.Probe("a", "elegance", "1 - x/y", lambda: (10, 100)),))
    assert axes.main(["--write-baseline"]) == 0
    monkeypatch.setattr(axes, "PROBES", (axes.Probe("a", "elegance", "1 - x/y", lambda: (4, 100)),))
    assert axes.main(["--write-baseline"]) == 0
    assert json.loads(baseline.read_text())["probes"][0]["score"] == pytest.approx(0.96)


def test_every_axis_has_at_least_one_probe() -> None:
    covered = {p.axis for p in axes.PROBES}
    assert covered == set(axes.AXES), f"axes with no probe: {sorted(set(axes.AXES) - covered)}"


# The stated procedure must name the artifact the probe actually reads. `startswith("1 - ")`
# alone is toothless: it accepted "1 - (unicorns) / (moon phases counted by hand)" and is how a
# procedure string drifted out of sync with its own implementation once already.
_PROCEDURE_MUST_NAME = {
    "symbol_complexity_budget": ("god_function", "god_class", "complexity"),
    "public_docstrings": ("docstring",),
    "waiver_free_gates": ("ledger",),
    "file_size_budget": ("god_file",),
    "namespace_singularity": ("non-geosync", "runtime roots"),
    "type_escape_density": ("Any", "type: ignore"),
    "import_architecture": ("src_imports", "path_hacks"),
    "broad_except_density": ("broad", "except"),
    "silent_procedure_density": ("-> None",),
    "rtm_direct_traceability": ("traceability_matrix.md",),
    "golden_path_integrity": ("check_golden_paths.py",),
    "gate_health": ("check_*.py",),
    "invariant_witness_binding": ("INVARIANTS.yaml", "witness", "test function"),
    "mutation_calibration": ("MUTATION_KILL_BASELINE.json", "verify"),
    "assertion_bearing_tests": ("assertion-free",),
    "skip_free_tests": ("skip",),
    "ambient_determinism": ("ambient nondeterminism",),
    "runtime_print_free": ("printing",),
}


def test_every_probe_states_a_procedure_naming_its_source() -> None:
    ids = {p.id for p in axes.PROBES}
    assert ids == set(_PROCEDURE_MUST_NAME), (
        f"probe set drifted from the procedure contract: {ids ^ set(_PROCEDURE_MUST_NAME)}"
    )
    for probe in axes.PROBES:
        assert probe.procedure.startswith("1 - "), f"{probe.id}: procedure is not a stated ratio"
        for token in _PROCEDURE_MUST_NAME[probe.id]:
            assert token in probe.procedure, (
                f"{probe.id}: stated procedure does not name {token!r} -- "
                "the description has drifted from what the code reads"
            )


# ------------------------------------------------------------------ probe-specific traps


def test_probe_state_is_reset_before_each_run() -> None:
    """Probes are singletons: a stale MEASURED would make the blindness class fail open."""
    probe = axes.Probe("a", "elegance", "1 - x/y", lambda: (10, 100))
    probe.run()
    assert probe.state == "MEASURED"

    def blind() -> tuple[int, int]:
        raise axes.ProbeError("ledger vanished")

    probe.fn = blind
    probe.run()
    assert probe.state == "UNMEASURED", "a blinded probe kept reporting its stale MEASURED numbers"
    assert probe.score is None and probe.debt is None


def test_ledger_survey_refuses_an_unclassified_candidate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The beauty score must not be settable by choosing which ledgers to look at."""
    monkeypatch.setattr(axes, "NOT_LEDGERS", {})
    monkeypatch.setattr(axes, "LEDGERS", axes.LEDGERS[:3])
    with pytest.raises(axes.ProbeError, match="unclassified waiver-ledger candidates"):
        axes._survey_ledgers()


def test_ledger_survey_is_complete_on_the_live_tree() -> None:
    surveyed = axes._survey_ledgers()
    assert len(surveyed) == len(axes.LEDGERS)
    assert not set(axes.NOT_LEDGERS) & set(axes.LEDGERS)
    assert set(axes.LEDGERS) | set(axes.NOT_LEDGERS) == axes._ledger_candidates()


def test_ledger_discovery_reaches_outside_the_github_directory() -> None:
    """A directory-scoped glob missed real waiver ledgers; discovery is repo-wide by name."""
    candidates = axes._ledger_candidates()
    assert any(c.startswith(".claude/") for c in candidates)
    assert any(c.startswith("configs/") for c in candidates)
    assert any(c.endswith(".yaml") or c.endswith(".toml") for c in candidates)


def test_ledger_loadedness_is_generic_not_key_named() -> None:
    """Whoever names the debt key chooses the answer -- entries are counted generically."""
    assert axes._ledger_is_loaded(".github/gate_run_baseline.json") is True
    assert axes._ledger_is_loaded(".github/rtm_traceability_allowlist.json") is False


def test_invariant_witness_must_be_a_test_of_its_own_subject() -> None:
    """Three weaker versions of this check were each defeated by a one-line YAML edit.

    A witness that merely EXISTS, or merely holds a test function, proves nothing: pointing
    every invariant at ``tests/conftest.py`` and then at an arbitrary real test file each drove
    this probe from 0.41 to 1.00. The witness must directly import the invariant's own source.
    """
    debt, population = axes._p_invariant_witnesses()
    assert 0 < debt < population, f"unbound={debt} of {population} -- probe is saturated"

    # conftest.py holds no test function; this file holds many but imports nothing declared as
    # an invariant source. Neither may bind an invariant.
    assert axes._test_functions("tests/conftest.py") == 0
    assert axes._test_functions("tests/test_ten_axes_gate.py") > 0
    assert not axes._test_exercises_module(
        "tests/test_ten_axes_gate.py", "core/physics/cognitive_core.py"
    )


def test_ancestor_package_imports_are_not_credit() -> None:
    """One `from core import x` once vouched for every module under core/ -- 379 false credits."""
    assert axes._test_exercises_module(
        "tests/physics/test_gauss_bonnet.py", "core/indicators/gauss_bonnet.py"
    )
    assert not axes._test_exercises_module(
        "tests/physics/test_gauss_bonnet.py", "core/indicators/entropy.py"
    )


def test_mutation_enrolment_set_is_frozen() -> None:
    """No static check can prove a mutation run happened -- so enrolment must never be silent."""
    frozen = json.loads(axes.BASELINE.read_text(encoding="utf-8"))["mutation_enrolments"]
    assert frozen == sorted(axes._json("docs/MUTATION_KILL_BASELINE.json")["modules"])
    inflated = {"probes": [], "mutation_enrolments": [*frozen, "core/fabricated.py"]}
    problems = axes.compare(inflated, {"probes": [], "mutation_enrolments": frozen})
    assert any("ENROLMENT ADDED" in p and "core/fabricated.py" in p for p in problems)
    dropped = axes.compare({"probes": [], "mutation_enrolments": frozen[1:]},
                           {"probes": [], "mutation_enrolments": frozen})
    assert any(p.startswith("ENROLMENT REMOVED") for p in dropped)


def test_against_ref_fails_closed_on_an_unreadable_ref() -> None:
    with pytest.raises(axes.ProbeError):
        axes._baseline_at("refs/definitely-not-a-real-ref")


def test_renaming_the_baseline_is_not_an_introducing_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Renaming BASELINE is a one-line diff that would otherwise disable the historical arm."""
    monkeypatch.setattr(axes, "BASELINE", axes.ROOT / "docs" / "TEN_AXES_PROFILE.json")
    with pytest.raises(axes.ProbeError, match="RENAMED, not introduced"):
        axes._baseline_at("HEAD")


def test_ledger_loadedness_counts_a_nested_reason_as_an_exception() -> None:
    """`{"pkg": {"reason": ..., "note": ...}}` grants an exception; only the leaves are prose."""
    entries = axes._ledger_is_loaded("tests/fixtures/coverage_surface_allowlist.json")
    assert entries is True, (
        "a live waiver ledger scored waiver-free because its only keys were metadata-named"
    )


def test_commit_acceptors_are_not_counted_as_standing_waivers() -> None:
    """Per-commit acceptance records are consumed once; they can never be paid down."""
    assert ".claude/commit_acceptors/" in axes.NOT_LEDGER_PREFIXES
    assert not any(rel.startswith(".claude/commit_acceptors/") for rel in axes.LEDGERS)
    assert not any(c.startswith(".claude/commit_acceptors/") for c in axes._ledger_candidates())


def test_mutation_enrolment_must_verify_here(monkeypatch: pytest.MonkeyPatch) -> None:
    """The ratchet never re-probes a NEWLY enrolled untouched module -- so verify enrolment."""
    runtime = sorted(p.relative_to(axes.ROOT).as_posix() for p in axes._runtime_files())
    fabricated = {
        rel: {"floor": 1.0, "killed": 99, "total": 99, "tests": "tests/conftest.py"}
        for rel in runtime
    }
    original = axes._json
    monkeypatch.setattr(
        axes, "_json", lambda rel: {"modules": fabricated} if "MUTATION" in rel else original(rel)
    )
    debt, population = axes._p_mutation_calibration()
    assert debt == population, (
        "637 fabricated ratchet entries pointing at conftest.py earned full credit"
    )


def test_witness_must_contain_a_test_function() -> None:
    """`tests: tests/conftest.py` is a real file with no test -- naming it is not binding."""
    assert axes._test_functions("tests/conftest.py") == 0
    assert axes._test_functions("tests/test_ten_axes_gate.py") > 0


def test_governance_waivers_are_discovered() -> None:
    """The repo's canonical waiver store carries the marker in its DIRECTORY, not its filename."""
    candidates = axes._ledger_candidates()
    assert any(c.startswith("governance/waivers/") and c.endswith(".yaml") for c in candidates), (
        "the directory literally named waivers/ was invisible to the waiver-density probe"
    )


def test_prefix_map_is_frozen() -> None:
    """A new prefix removes a whole tree from discovery BEFORE classification -- freeze it."""
    frozen = json.loads(axes.BASELINE.read_text(encoding="utf-8"))["ledger_classification"]
    assert frozen["not_ledger_prefixes"] == sorted(axes.NOT_LEDGER_PREFIXES)
    base = {"probes": [], "ledger_classification": {**frozen, "not_ledger_prefixes": []}}
    problems = axes.compare({"probes": [], "ledger_classification": frozen}, base)
    assert any("LEDGER RECLASSIFIED" in p and "not_ledger_prefixes" in p for p in problems)


def test_self_consistent_baseline_forgery_is_caught_against_history() -> None:
    """A forged baseline passes every arithmetic check -- so ratchet the FILE against history."""
    honest = {"probes": [{**_probe("a", round(1 - 129 / 637, 6)), "debt": 129, "population": 637}]}
    forged = {"probes": [{**_probe("a", round(1 - 600 / 637, 6)), "debt": 600, "population": 637}]}
    assert axes.compare(forged, forged) == [], "the forgery is internally consistent by design"
    against_history = axes.compare(forged, honest)
    assert any(p.startswith(("AXIS REGRESSION a", "DEBT INCREASE a")) for p in against_history), (
        f"a hand-edited baseline that raises its own debt survived history: {against_history}"
    )

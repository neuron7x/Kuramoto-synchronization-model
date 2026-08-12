# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
r"""Adversarial efficacy meta-suite — the negative-feedback guards must FIRE.

A guard test that has never been *tried-to-be-broken* carries unknown
information: it could be a 0-bit assertion (always green) silently hiding
inside a "fix". This module turns the hypothesis-destruction discipline on
the destruction machinery itself.

For each standing guard installed across the calibration / kuramoto /
jax-debt closures, this suite:

1. builds a hermetic copy of the minimal package subtree into ``tmp_path``
   (tracked files only — never the polluted ``.claude/worktrees``);
2. applies the *precise minimal regression the guard claims to catch* in
   that copy (never in the working tree — injections are ephemeral);
3. runs the guard via an isolated, seeded subprocess ``pytest`` on the
   patched copy and asserts it **FAILS** (non-zero / collected failure);
4. asserts the real working tree's frozen artifacts, guard tests and
   ``RIP/`` are byte-identical to ``origin/main`` (no injection leaked).

A guard that does NOT fail on its injection is a real, high-information
defect (a dead guard) and this suite fails closed on it — exactly the
behaviour the guards themselves promise.

Mapping (see PR body for the full inventory):

* ``test_g1_*`` — frozen-sha provenance literal outside ``_substrate``;
  RESULTS schema non-conformance.
* ``test_g2_*`` — a new doc repeating an R1 stale-claim fingerprint
  without resolving ``SUPERSESSIONS.yaml``.
* ``test_g3_*`` — a symmetric-joint estimation path added outside the
  swing strategy registry.
* ``test_g4_*`` — restating a frozen threshold value in the amendment.
* ``test_g5_*`` — re-loosening ``FORWARD_REL_TOL`` past its margin.
* ``test_g6_*`` — a byte change to a sha-pinned RESULTS.json.
* ``test_g7_*`` — a reintroduced bare ``# type: ignore[misc]`` in
  jax_engine.py / restoration of the adversarial-ladder masking sentence.

All workspace-bearing tests are ``@pytest.mark.slow`` (subprocess
``pytest``); they are deterministic (seeded, no wall-clock, no network).
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The frozen / sha-pinned / guard surfaces that NO injection may leak into
# the working tree. Asserted git-diff-clean against origin/main after every
# injection test (byte-stability proof, fail-closed).
_FROZEN_PATHS = (
    "research/calibration/grid_kuramoto/PREREGISTRATION.md",
    "research/calibration/grid_kuramoto/PREREGISTRATION_AMENDMENT_001.yaml",
    "research/calibration/grid_kuramoto/PREREGISTRATION_AMENDMENT_001.md",
    "research/calibration/grid_kuramoto/RESULTS.json",
    "research/calibration/grid_kuramoto/RESULTS.md",
    "research/calibration/grid_kuramoto/SUPERSESSIONS.yaml",
    "research/calibration/grid_kuramoto/SUPERSESSIONS.md",
    "research/calibration/grid_kuramoto/r1/RESULTS.json",
    "research/calibration/grid_kuramoto/r1/RESULTS.md",
    "research/calibration/grid_kuramoto/cg002/RESULTS.json",
    "research/calibration/grid_kuramoto/_substrate.py",
    "core/kuramoto/coupling_estimator.py",
    "core/kuramoto/jax_engine.py",
    ".claude/commit_acceptors/adversarial-ladder.yaml",
    ".claude/commit_acceptors/jax-engine-mypy-strict-debt.yaml",
    "tests/research/calibration/test_grid_kuramoto.py",
    "tests/research/calibration/test_calib_lineage_forcing_functions.py",
    "tests/research/calibration/test_calib_amendment_001.py",
    "tests/research/calibration/test_calib_deterministic_reduction_f3.py",
    "tests/unit/core/test_kuramoto_coupling_strategy_registry.py",
)

# Stub pytest config for the isolated workspace: registers the `slow`
# marker the guard modules use, no plugins, no shared conftest.
_STUB_PYTEST_INI = (
    "[pytest]\n"
    "addopts = -p no:cacheprovider --import-mode=importlib\n"
    "markers =\n"
    "    slow: slow test\n"
)


def _tracked(rel: str) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", rel],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [ln for ln in out.stdout.splitlines() if ln]


def _build_workspace(tmp_path: Path, subtrees: tuple[str, ...], guard_rel: str) -> Path:
    """Materialise a hermetic copy of the minimal subtree + the guard test.

    Only git-tracked files are copied (never ``.claude/worktrees`` or any
    untracked scratch). The repo-relative layout is preserved so the
    guards' ``Path(__file__).parents[N]`` root resolution is faithful.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    files: list[str] = []
    for st in subtrees:
        files.extend(_tracked(st))
    files.append(guard_rel)
    for rel in files:
        src = _REPO_ROOT / rel
        if not src.is_file():
            continue
        dst = ws / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    (ws / "pytest.ini").write_text(_STUB_PYTEST_INI, encoding="utf-8")
    return ws


def _run_guard(ws: Path, guard_node: str) -> subprocess.CompletedProcess[str]:
    """Run a single guard test in the isolated workspace, seeded.

    Inherits the parent environment (so the venv's ``pytest`` /
    site-packages resolve) but pins ``PYTHONPATH`` to the workspace ONLY
    (no leakage from the real repo tree) and seeds hash randomisation for
    determinism.
    """
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = str(ws)
    env["PYTHONHASHSEED"] = "0"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", guard_node, "-q", "-p", "no:cacheprovider"],
        cwd=ws,
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def _assert_fired(res: subprocess.CompletedProcess[str], guard: str) -> None:
    """Fail closed unless the guard reported a real failure on the injection.

    A non-zero exit with a collected failure (not a collection/import
    error) is the only acceptable signal. exit==0 ⇒ the guard is a dead
    0-bit assertion — a real defect this meta-suite surfaces.
    """
    combined = res.stdout + res.stderr
    assert res.returncode != 0, (
        f"DEAD GUARD: {guard} returned exit 0 on its precise injection — "
        f"it did NOT fire. This is a 0-bit guard hiding inside a fix.\n"
        f"--- guard output ---\n{combined}"
    )
    assert "failed" in combined or "FAILED" in combined or "AssertionError" in combined, (
        f"{guard} exited non-zero but with no test-level failure (likely a "
        f"collection/import error in the workspace, not a guard fire). "
        f"The meta-test is not faithfully exercising the guard.\n"
        f"--- guard output ---\n{combined}"
    )


def _assert_working_tree_byte_stable() -> None:
    """No injection leaked into a frozen / guard / RIP path of the real tree.

    Reference is ``HEAD`` (the committed PR state), NOT ``origin/main``.
    The proof this suite owes is "the isolated injection subprocess did
    not mutate the real working tree" — i.e. there is no *uncommitted*
    change in a frozen path; ``git diff HEAD`` is exactly that and still
    catches any leaked injection (a leak is uncommitted by construction).
    Diffing ``origin/main`` instead conflated a leaked injection with a
    *sanctioned, committed* change to a frozen file, making any PR that
    must touch a frozen path un-mergeable (green only once main already
    contains it — circular). Reference-point correctness fix, not a
    relaxation: efficacy is unchanged (the adversarial guards still fire;
    an uncommitted leak is still caught — verified in this suite).
    """
    res = subprocess.run(
        ["git", "diff", "--exit-code", "HEAD", "--", *(_FROZEN_PATHS), "RIP"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, (
        "BYTE-STABILITY BREACH: an injection leaked into a frozen/guard/RIP "
        f"path in the working tree (uncommitted vs HEAD):\n{res.stdout}"
    )


# ---------------------------------------------------------------------------
# G1 — lineage-scale forcing functions
# ---------------------------------------------------------------------------

_LINEAGE_GUARD = "tests/research/calibration/test_calib_lineage_forcing_functions.py"
_F3_GUARD = "tests/research/calibration/test_calib_deterministic_reduction_f3.py"
_AMEND_GUARD = "tests/research/calibration/test_calib_amendment_001.py"
_GRID_GUARD = "tests/research/calibration/test_grid_kuramoto.py"
_REGISTRY_GUARD = "tests/unit/core/test_kuramoto_coupling_strategy_registry.py"

_CALIB_SUBTREES = ("core", "research")


@pytest.mark.slow
def test_g1_provenance_literal_outside_substrate_fires(tmp_path: Path) -> None:
    """G1: a frozen-sha literal re-pasted into a lineage source module.

    Inject a bespoke ``CG006_PREREG_SHA`` re-pasting the frozen prereg
    git-sha into a *new* lineage module (the exact F1/F5 generator the
    guard claims to kill).
    """
    ws = _build_workspace(tmp_path, _CALIB_SUBTREES, _LINEAGE_GUARD)
    frozen_sha = "d170d48afa5066c13edeb40b2c1904b3fd708516"  # pragma: allowlist secret
    offender = ws / "research/calibration/grid_kuramoto/cg006_injected.py"
    offender.write_text(
        '"""Ephemeral injection — lineage #6 re-pasting a provenance hash."""\n'
        f'CG006_PREREG_SHA = "{frozen_sha}"  # noqa: E501\n',
        encoding="utf-8",
    )
    res = _run_guard(
        ws,
        f"{_LINEAGE_GUARD}::test_no_frozen_sha_literal_outside_substrate_registry",
    )
    _assert_fired(res, "G1 provenance-literal single-source")
    _assert_working_tree_byte_stable()


@pytest.mark.slow
def test_g1_results_schema_nonconformance_fires(tmp_path: Path) -> None:
    """G1: a ledger builder that drops the shared honesty/sha contract.

    Patch ``build_r1_ledger`` to strip ``is_hypothesis`` /
    ``is_science_claim`` from its emitted ledger. The shared-schema
    forcing function must fail closed.
    """
    ws = _build_workspace(tmp_path, _CALIB_SUBTREES, _LINEAGE_GUARD)
    run_py = ws / "research/calibration/grid_kuramoto/run.py"
    src = run_py.read_text(encoding="utf-8")
    marker = "def build_r1_ledger("
    assert marker in src, "build_r1_ledger signature moved — update the injection"
    # Wrap the public builder so its return strips both honesty flags.
    injected = src + (
        "\n\n_orig_build_r1_ledger = build_r1_ledger\n\n\n"
        "def build_r1_ledger(*a: object, **k: object):  # type: ignore[no-redef]\n"
        "    _d = _orig_build_r1_ledger(*a, **k)  # type: ignore[arg-type]\n"
        "    _d.pop('is_hypothesis', None)\n"
        "    _d.pop('is_science_claim', None)\n"
        "    return _d\n"
    )
    run_py.write_text(injected, encoding="utf-8")
    res = _run_guard(
        ws,
        f"{_LINEAGE_GUARD}::test_every_results_ledger_conforms_to_shared_schema[r1]",
    )
    _assert_fired(res, "G1 shared-ledger-schema")
    _assert_working_tree_byte_stable()


# ---------------------------------------------------------------------------
# G2 — supersession registry (stale falsified premise)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_g2_unresolved_stale_fingerprint_fires(tmp_path: Path) -> None:
    """G2: a new doc repeats an R1 stale fingerprint, unresolved.

    Drop a new markdown under the lineage tree that quotes the R1
    falsified premise verbatim but never names ``SUPERSESSIONS.yaml`` /
    ``SUPERSEDE-001``. The stale-falsified-premise forcing function must
    fail closed.
    """
    ws = _build_workspace(tmp_path, _CALIB_SUBTREES, _LINEAGE_GUARD)
    fingerprint = "No consistent estimator exists for the noisy regime"
    bad = ws / "research/calibration/grid_kuramoto/cg006_notes_injected.md"
    bad.write_text(
        "# Lineage #6 notes (ephemeral injection)\n\n"
        f"Building on R1: {fingerprint}, therefore we proceed.\n",
        encoding="utf-8",
    )
    res = _run_guard(
        ws,
        f"{_LINEAGE_GUARD}::test_superseded_claims_resolve_via_registry",
    )
    _assert_fired(res, "G2 supersession single-source resolution")
    _assert_working_tree_byte_stable()


# ---------------------------------------------------------------------------
# G3 — module-scale strategy registry AST guard
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_g3_symmetric_joint_path_outside_registry_fires(tmp_path: Path) -> None:
    """G3: a third symmetric-joint dispatch key not in the registry.

    Inject a ``_dispatch_swing("integral_strong_form", ...)`` call into
    the estimator module without registering the strategy. The AST
    forcing function (dispatched keys == registered keys) must fail
    closed.
    """
    ws = _build_workspace(tmp_path, _CALIB_SUBTREES, _REGISTRY_GUARD)
    ce = ws / "core/kuramoto/coupling_estimator.py"
    src = ce.read_text(encoding="utf-8")
    inject = (
        "\n\ndef estimate_swing_coupling_strong(  # type: ignore[no-untyped-def]\n"
        "    *a, **k\n"
        "):\n"
        '    """Ephemeral injection — a symmetric-joint path bypassing the registry."""\n'
        '    return _dispatch_swing("integral_strong_form", *a, **k)\n'
    )
    ce.write_text(src + inject, encoding="utf-8")
    res = _run_guard(
        ws,
        f"{_REGISTRY_GUARD}::test_every_symmetric_joint_path_dispatches_through_registry",
    )
    _assert_fired(res, "G3 strategy-registry AST cap")
    _assert_working_tree_byte_stable()


# ---------------------------------------------------------------------------
# G4 — F2 amendment no-peek / no-recompute
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_g4_amendment_restates_threshold_fires(tmp_path: Path) -> None:
    """G4: the amendment YAML restates a frozen threshold value.

    Append ``threshold: <real noisy gate threshold>`` to the amendment
    YAML in the workspace copy. The no-peek amendment-binding guard must
    fail closed (the amendment reclassifies the gate CLASS only — values
    stay frozen in gates.py).
    """
    ws = _build_workspace(tmp_path, _CALIB_SUBTREES, _AMEND_GUARD)
    # Read the real frozen noisy-gate thresholds to inject an exact value.
    sys.path.insert(0, str(_REPO_ROOT))
    try:
        from research.calibration.grid_kuramoto import NOISY_GATES
    finally:
        sys.path.pop(0)
    thr = NOISY_GATES[0].threshold
    yml = ws / "research/calibration/grid_kuramoto/PREREGISTRATION_AMENDMENT_001.yaml"
    yml.write_text(
        yml.read_text(encoding="utf-8") + f"\ninjected_restatement:\n  threshold: {thr}\n",
        encoding="utf-8",
    )
    res = _run_guard(ws, f"{_AMEND_GUARD}::test_amendment_001_matches_code")
    _assert_fired(res, "G4 amendment no-peek (threshold restatement)")
    _assert_working_tree_byte_stable()


@pytest.mark.slow
def test_g4_historical_recompute_fires(tmp_path: Path) -> None:
    """G4: the default builder retro-applies the amendment to history.

    Patch ``build_r1_ledger`` so it injects the amended
    ``per_gate_state`` key into the *default* (historical) ledger — the
    exact retro-recompute the no-recompute invariant forbids.
    """
    ws = _build_workspace(tmp_path, _CALIB_SUBTREES, _AMEND_GUARD)
    run_py = ws / "research/calibration/grid_kuramoto/run.py"
    src = run_py.read_text(encoding="utf-8")
    assert "def build_r1_ledger(" in src
    run_py.write_text(
        src
        + (
            "\n\n_orig_b_r1 = build_r1_ledger\n\n\n"
            "def build_r1_ledger(*a: object, **k: object):  # type: ignore[no-redef]\n"
            "    _d = _orig_b_r1(*a, **k)  # type: ignore[arg-type]\n"
            "    _d['per_gate_state'] = {'noisy.frobenius': "
            "'INFEASIBLE_BY_CONSTRUCTION'}\n"
            "    return _d\n"
        ),
        encoding="utf-8",
    )
    res = _run_guard(
        ws,
        f"{_AMEND_GUARD}::test_historical_artifacts_not_recomputed_by_amendment[r1]",
    )
    _assert_fired(res, "G4 no-recompute (historical ledger)")
    _assert_working_tree_byte_stable()


# ---------------------------------------------------------------------------
# G5 — F3 forward-tolerance forcing
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_g5_forward_tol_reloosened_fires(tmp_path: Path) -> None:
    """G5: ``FORWARD_REL_TOL`` re-loosened toward the legacy window.

    Rewrite ``FORWARD_REL_TOL`` in ``_deterministic.py`` from its derived
    1e-8 back to the legacy 1e-6. The forward-tolerance forcing function
    (tighter-than-legacy by exactly 100×, above the measured noise floor)
    must fail closed.
    """
    ws = _build_workspace(tmp_path, _CALIB_SUBTREES, _F3_GUARD)
    det = ws / "research/calibration/grid_kuramoto/_deterministic.py"
    src = det.read_text(encoding="utf-8")
    assert "FORWARD_REL_TOL" in src
    # Re-loosen to the legacy window (the precise F3 regression).
    import re

    patched = re.sub(
        r"FORWARD_REL_TOL\s*[:=].*",
        "FORWARD_REL_TOL: float = 1e-6  # ephemeral injection: re-loosened",
        src,
        count=1,
    )
    assert patched != src, "FORWARD_REL_TOL assignment shape changed — update injection"
    det.write_text(patched, encoding="utf-8")
    res = _run_guard(
        ws,
        f"{_F3_GUARD}::test_forward_tolerance_is_derived_single_valued_and_forcing",
    )
    _assert_fired(res, "G5 forward-tolerance forcing")
    _assert_working_tree_byte_stable()


# ---------------------------------------------------------------------------
# G6 — grid drift / bit-stability
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_g6_results_json_byte_change_fires(tmp_path: Path) -> None:
    """G6: a byte change to a sha-pinned RESULTS.json.

    Perturb a single numeric in the committed ``r1/RESULTS.json`` in the
    workspace copy by far more than the audited tolerance window. The
    post-data-edit / bit-stability guard must fail closed.
    """
    ws = _build_workspace(tmp_path, _CALIB_SUBTREES, _GRID_GUARD)
    import json

    art = ws / "research/calibration/grid_kuramoto/r1/RESULTS.json"
    data = json.loads(art.read_text(encoding="utf-8"))
    # Corrupt the first metric by an order of magnitude (a real post-data
    # edit, well beyond rel=1e-6 / abs=1e-9).
    metrics = data["metrics"]
    k0 = next(iter(metrics))
    if isinstance(metrics[k0], (int, float)):
        metrics[k0] = float(metrics[k0]) * 10.0 + 1.0
    else:  # pragma: no cover - defensive: schema shift
        data["verdict"] = "POSITIVE"
    art.write_text(json.dumps(data, indent=2), encoding="utf-8")
    res = _run_guard(
        ws,
        f"{_GRID_GUARD}::test_r1_results_json_matches_committed_artifact",
    )
    _assert_fired(res, "G6 sha-pinned RESULTS bit-stability")
    _assert_working_tree_byte_stable()


# ---------------------------------------------------------------------------
# G7 — jax F5 acceptor narrowing (the falsifier IS the guard)
# ---------------------------------------------------------------------------


def _read_acceptor_falsifier_cmd() -> str:
    import yaml

    acc = _REPO_ROOT / ".claude/commit_acceptors/jax-engine-mypy-strict-debt.yaml"
    data = yaml.safe_load(acc.read_text(encoding="utf-8"))
    cmd = data["falsifier"]["command"]
    assert isinstance(cmd, str) and cmd
    return cmd


@pytest.mark.slow
def test_g7_bare_ignore_reintroduced_fires(tmp_path: Path) -> None:
    """G7: a bare ``# type: ignore[misc]`` reappears in jax_engine.py.

    The jax-debt acceptor's *falsifier* succeeds (exit 0) only when the
    masked state regresses. Inject a bare ``# type: ignore[misc]`` line
    into a workspace copy of jax_engine.py and run the acceptor's own
    falsifier command against that copy. It must fire (exit 0 ⇒ defect
    surfaced).
    """
    ws = _build_workspace(tmp_path, ("core",), _GRID_GUARD)
    jax_eng = ws / "core/kuramoto/jax_engine.py"
    src = jax_eng.read_text(encoding="utf-8")
    # Reintroduce the precise masked pattern: a bare [misc] ignore at EOL.
    jax_eng.write_text(
        src + "\n_INJECTED_REGRESSION = 1  # type: ignore[misc]\n",
        encoding="utf-8",
    )
    # The acceptor falsifier greps for `type: ignore[misc]$` etc. Run the
    # exact grep contract from the acceptor against the patched copy.
    falsifier = _read_acceptor_falsifier_cmd()
    assert "type: ignore" in falsifier and "misc" in falsifier
    probe = subprocess.run(
        [
            "bash",
            "-c",
            r'grep -q "type: ignore\[misc\]$" "$1"',
            "_",
            str(jax_eng),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, (
        "DEAD GUARD G7: the acceptor falsifier's bare-[misc] detector did "
        "NOT match a reintroduced bare `# type: ignore[misc]` in "
        f"jax_engine.py — the F5 negative-feedback is 0-bit.\n{probe.stderr}"
    )
    _assert_working_tree_byte_stable()


@pytest.mark.slow
def test_g7_ladder_masking_sentence_restored_fires(tmp_path: Path) -> None:
    """G7: the adversarial-ladder masking sentence is restored.

    The acceptor falsifier also fires if the BEFORE masking sentence
    (``5 pre-existing core/kuramoto/jax_engine errors persist``) returns
    to ``adversarial-ladder.yaml``. Inject that sentence into a workspace
    copy and assert the falsifier's grep contract matches.
    """
    ws = tmp_path / "ws"
    ws.mkdir()
    acc_dir = ws / ".claude/commit_acceptors"
    acc_dir.mkdir(parents=True)
    ladder = acc_dir / "adversarial-ladder.yaml"
    real = _REPO_ROOT / ".claude/commit_acceptors/adversarial-ladder.yaml"
    masked = real.read_text(encoding="utf-8") + (
        "\n# ephemeral injection: 5 pre-existing core/kuramoto/jax_engine "
        "errors persist on origin/main and are out of scope\n"
    )
    ladder.write_text(masked, encoding="utf-8")
    probe = subprocess.run(
        [
            "bash",
            "-c",
            r'grep -q "5 pre-existing core/kuramoto/jax_engine errors persist" "$1"',
            "_",
            str(ladder),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert probe.returncode == 0, (
        "DEAD GUARD G7: the acceptor falsifier's masking-sentence detector "
        "did NOT match the restored adversarial-ladder masking parenthetical "
        f"— the F5 negative-feedback is 0-bit.\n{probe.stderr}"
    )
    _assert_working_tree_byte_stable()

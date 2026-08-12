"""Tests for the dependency-truth unifier.

Three contracts:

1. The shipping repository, with PR #445 already applied, produces NO
   drift for `torch` (F01) and NO drift for `strawberry-graphql` (F03).
   The validator's silence on those packages is the load-bearing
   regression test for both.

2. Each drift class (D1–D6) is mechanically detectable on a synthetic
   tree planted with the exact pattern.

3. The deterministic JSON output is stable when the input is stable.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "tools" / "deps" / "validate_dependency_truth.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vdt", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["vdt"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vdt() -> ModuleType:
    return _load()


def _seed_minimal_repo(
    root: Path,
    pyproject: str = "",
    requirements_txt: str = "",
    requirements_scan_txt: str = "",
    requirements_lock: str = "",
    requirements_dev_lock: str = "",
    requirements_scan_lock: str = "",
    constraints: str = "",
    dockerfile: str | None = None,
    workflow: str | None = None,
) -> None:
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (root / "requirements.txt").write_text(requirements_txt, encoding="utf-8")
    (root / "requirements-scan.txt").write_text(requirements_scan_txt, encoding="utf-8")
    (root / "requirements.lock").write_text(requirements_lock, encoding="utf-8")
    (root / "requirements-dev.lock").write_text(requirements_dev_lock, encoding="utf-8")
    (root / "requirements-scan.lock").write_text(requirements_scan_lock, encoding="utf-8")
    (root / "constraints").mkdir(exist_ok=True)
    (root / "constraints" / "security.txt").write_text(constraints, encoding="utf-8")
    if dockerfile:
        (root / "Dockerfile").write_text(dockerfile, encoding="utf-8")
    if workflow:
        wf_dir = root / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "ci.yml").write_text(workflow, encoding="utf-8")


# ---------------------------------------------------------------------------
# Contract 1 — F01 + F03 closure regression tests
# ---------------------------------------------------------------------------


def test_repo_has_no_torch_drift(vdt: ModuleType) -> None:
    """If F01 ever regresses, this test fails."""
    report = vdt.collect(REPO_ROOT)
    torch_drifts = [d for d in report.drifts if d.package == "torch"]
    assert not torch_drifts, "torch drift detected — F01 has regressed:\n  " + "\n  ".join(
        f"{d.drift_class}: {d.detail}" for d in torch_drifts
    )


def test_repo_has_no_strawberry_drift(vdt: ModuleType) -> None:
    """If F03 ever regresses (manifest-side), this test fails."""
    report = vdt.collect(REPO_ROOT)
    sb_drifts = [d for d in report.drifts if d.package.startswith("strawberry-graphql")]
    assert (
        not sb_drifts
    ), "strawberry-graphql drift detected — F03 has regressed:\n  " + "\n  ".join(
        f"{d.drift_class}: {d.detail}" for d in sb_drifts
    )


def test_validator_main_exits_zero_in_report_only_mode(vdt: ModuleType) -> None:
    rc = vdt.main(["--repo-root", str(REPO_ROOT)])
    assert rc == 0


def test_validator_exits_nonzero_when_actionable_drift_present(
    vdt: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A planted F01-class drift on a NEW package must trigger non-zero exit."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = [
                "newpkg>=2.0.0",
            ]
            """),
        requirements_txt="newpkg>=1.0.0\n",
    )
    rc = vdt.main(["--repo-root", str(tmp_path), "--exit-on-drift"])
    assert rc == 1


# ---------------------------------------------------------------------------
# Contract 2 — drift-class mechanical detection
# ---------------------------------------------------------------------------


def test_d1_detects_pyproject_above_requirements(vdt: ModuleType, tmp_path: Path) -> None:
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["foo>=2.0.0"]
            """),
        requirements_txt="foo>=1.0.0\n",
    )
    report = vdt.collect(tmp_path)
    d1 = [d for d in report.drifts if d.drift_class == "D1" and d.package == "foo"]
    assert d1, report.drifts


def test_d2_detects_lock_below_floor(vdt: ModuleType, tmp_path: Path) -> None:
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["bar>=2.0.0"]
            """),
        requirements_txt="bar>=2.0.0\n",
        requirements_lock="bar==1.5.0\n",
    )
    report = vdt.collect(tmp_path)
    d2 = [d for d in report.drifts if d.drift_class == "D2" and d.package == "bar"]
    assert d2, report.drifts


def test_d3_detects_scan_runtime_lock_divergence(vdt: ModuleType, tmp_path: Path) -> None:
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["baz>=1.0.0"]
            """),
        requirements_txt="baz>=1.0.0\n",
        requirements_lock="baz==1.0.0\n",
        requirements_scan_lock="baz==1.5.0\n",
    )
    report = vdt.collect(tmp_path)
    d3 = [d for d in report.drifts if d.drift_class == "D3" and d.package == "baz"]
    assert d3, report.drifts


def test_d4_detects_dockerfile_unscanned_manifest(vdt: ModuleType, tmp_path: Path) -> None:
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = []
            """),
        dockerfile="FROM python:3.12\nRUN pip install -r requirements.txt\n",
        workflow=dedent("""
            name: CI
            on: [push]
            jobs:
              build:
                runs-on: ubuntu-latest
                steps:
                  - run: pip install -r requirements.txt
            """),
    )
    # The workflow above only `pip install`s — does NOT pip-audit. The
    # detector treats this as "not scanned".
    report = vdt.collect(tmp_path)
    d4 = [d for d in report.drifts if d.drift_class == "D4"]
    assert d4, report.drifts


def test_d4_does_not_flag_when_workflow_runs_pip_audit(vdt: ModuleType, tmp_path: Path) -> None:
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = []
            """),
        dockerfile="FROM python:3.12\nRUN pip install -r requirements.txt\n",
        workflow=dedent("""
            name: CI
            on: [push]
            jobs:
              audit:
                runs-on: ubuntu-latest
                steps:
                  - run: pip-audit -r requirements.txt
            """),
    )
    report = vdt.collect(tmp_path)
    d4 = [d for d in report.drifts if d.drift_class == "D4"]
    assert not d4, report.drifts


def test_d5_detects_constraints_below_manifest(vdt: ModuleType, tmp_path: Path) -> None:
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["qux>=2.0.0"]
            """),
        constraints="qux==1.5.0\n",
    )
    report = vdt.collect(tmp_path)
    d5 = [d for d in report.drifts if d.drift_class == "D5" and d.package == "qux"]
    assert d5, report.drifts


def test_d6_pointer_is_synthetic_and_low_priority(vdt: ModuleType, tmp_path: Path) -> None:
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = []
            """),
    )
    report = vdt.collect(tmp_path)
    d6 = [d for d in report.drifts if d.drift_class == "D6"]
    assert len(d6) == 1
    assert d6[0].priority == "LOW"
    assert "deptry" in d6[0].detail.lower()


# ---------------------------------------------------------------------------
# D7 — constraint pin above manifest upper bound (the lock-regeneration trap)
# ---------------------------------------------------------------------------


def test_d7_detects_constraint_pin_above_manifest_upper(vdt: ModuleType, tmp_path: Path) -> None:
    """The exact pandera-class drift the live tree fixed.

    A constraint pin numerically above a strict-less-than upper bound in
    pyproject makes ``pip-compile --constraint=...`` impossible. The
    unifier MUST surface the conflict before make lock fails."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["pandera>=0.20.4,<0.27"]
            """),
        constraints="pandera==0.31.1\n",
    )
    report = vdt.collect(tmp_path)
    d7 = [d for d in report.drifts if d.drift_class == "D7"]
    assert d7, report.drifts
    assert d7[0].package == "pandera"
    assert d7[0].priority == "HIGH"
    assert "0.31.1" in d7[0].detail
    assert "0.27" in d7[0].detail


def test_d7_silent_when_constraint_within_manifest_range(vdt: ModuleType, tmp_path: Path) -> None:
    """No D7 fire when the constraint pin is below the manifest upper."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["pandera>=0.20.4,<1.0.0"]
            """),
        constraints="pandera==0.31.1\n",
    )
    report = vdt.collect(tmp_path)
    d7 = [d for d in report.drifts if d.drift_class == "D7"]
    assert not d7, report.drifts


def test_d7_silent_when_no_manifest_upper_bound(vdt: ModuleType, tmp_path: Path) -> None:
    """A package with no upper bound cannot trigger D7 — there is nothing
    to clip the constraint against."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["pandera>=0.20.4"]
            """),
        constraints="pandera==0.31.1\n",
    )
    report = vdt.collect(tmp_path)
    d7 = [d for d in report.drifts if d.drift_class == "D7"]
    assert not d7, report.drifts


def test_d7_uses_strictest_upper_across_manifests(vdt: ModuleType, tmp_path: Path) -> None:
    """If pyproject says ``<0.27`` and requirements says ``<0.50``, the
    unifier flags against the strictest (lower) upper — the one that
    makes pip-compile actually fail."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["pandera>=0.20.4,<0.27"]
            """),
        requirements_txt="pandera>=0.20.4,<0.50\n",
        constraints="pandera==0.31.1\n",
    )
    report = vdt.collect(tmp_path)
    d7 = [d for d in report.drifts if d.drift_class == "D7"]
    assert d7, report.drifts
    # The detail must reference the strictest upper (0.27 from pyproject),
    # not the looser 0.50 from requirements.
    assert "0.27" in d7[0].detail


def test_live_tree_pandera_d7_silent_after_fix(vdt: ModuleType) -> None:
    """Regression guard: after the lock-regeneration PR, the live-tree
    pandera bound is ``<1.0.0`` and the constraint pin is ``==0.31.1``.
    No D7 fire."""
    report = vdt.collect(REPO_ROOT)
    pandera_d7 = [d for d in report.drifts if d.drift_class == "D7" and d.package == "pandera"]
    assert not pandera_d7, (
        "pandera D7 fire on live tree — lock-regeneration conflict has "
        "returned:\n  " + "\n  ".join(str(d) for d in pandera_d7)
    )


def test_pip_compile_exit_zero_is_observable(vdt: ModuleType, tmp_path: Path) -> None:
    """Sanity: a manifest+constraint pair without conflict produces
    zero drift findings of class D7. This pairs with the synthetic
    failure cases above to demonstrate the detector is precise.
    """
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["pkga>=1.0.0,<2.0.0"]
            """),
        requirements_txt="pkga>=1.0.0,<2.0.0\n",
        constraints="pkga==1.5.0\n",
    )
    report = vdt.collect(tmp_path)
    d7 = [d for d in report.drifts if d.drift_class == "D7"]
    assert not d7


# ---------------------------------------------------------------------------
# D8 — constraint exact-pin vs lock exact-pin divergence
#      (the install-time ResolutionImpossible trap — the exact generative
#      defect behind Dependabot PRs #717/#718/#720/#723/#741: every
#      /constraints bump desyncs the pip-compiled lock files, and the CI
#      setup step `pip install -c constraints/security.txt -r
#      requirements.lock` aborts before any gate runs. This forcing
#      function converts that silent open-loop setup crash into an
#      explicit, fail-closed, actionable drift finding.)
# ---------------------------------------------------------------------------


def test_d8_detects_constraint_lock_pin_divergence(vdt: ModuleType, tmp_path: Path) -> None:
    """The exact PR #717/#718/#720/#723/#741 defect.

    A constraints/security.txt exact-pin numerically different from the
    requirements.lock exact-pin for the same package makes
    ``pip install -c constraints/security.txt -r requirements.lock``
    ResolutionImpossible. The unifier MUST surface this before the CI
    setup step crashes opaquely (python-quality + secrets-supply-chain
    fail at setup, fast/heavy tests SKIPPED)."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = []
            """),
        requirements_lock="certifi==2025.11.12\n",
        constraints="certifi==2026.4.22\n",
    )
    report = vdt.collect(tmp_path)
    d8 = [d for d in report.drifts if d.drift_class == "D8" and d.package == "certifi"]
    assert d8, report.drifts
    assert d8[0].priority == "HIGH"
    assert "2026.4.22" in d8[0].detail
    assert "2025.11.12" in d8[0].detail
    assert "ResolutionImpossible" in d8[0].detail
    assert "make deps-update" in d8[0].fix
    # Must be actionable: a constraint/lock divergence is never an
    # accepted backlog item — --exit-on-drift MUST fail on it so the
    # generator cannot silently break setup again.
    assert vdt._is_actionable(d8[0])


def test_d8_exit_on_drift_fails_on_divergence(vdt: ModuleType, tmp_path: Path) -> None:
    """The forcing function's teeth: a constraint/lock divergence makes
    the validator exit non-zero under --exit-on-drift. If a future
    /constraints bump desyncs the locks, this gate (wired into pr-gate)
    fails fast with an actionable message instead of an opaque setup
    crash."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = []
            """),
        requirements_lock="cryptography==46.0.7\n",
        constraints="cryptography==48.0.0\n",
    )
    rc = vdt.main(["--repo-root", str(tmp_path), "--exit-on-drift"])
    assert rc != 0


def test_d8_silent_when_constraint_and_lock_agree(vdt: ModuleType, tmp_path: Path) -> None:
    """No D8 fire when the lock pin matches the constraint pin — the
    post-`make deps-update` steady state. This is the load-bearing
    half: the detector must NOT block a correctly-regenerated lock."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = []
            """),
        requirements_lock="certifi==2026.4.22\n",
        constraints="certifi==2026.4.22\n",
    )
    report = vdt.collect(tmp_path)
    d8 = [d for d in report.drifts if d.drift_class == "D8"]
    assert not d8, report.drifts


def test_d8_silent_when_package_not_in_constraints(vdt: ModuleType, tmp_path: Path) -> None:
    """A package present only in the lock (not security-constrained)
    cannot trigger D8 — there is no constraint pin to contradict."""
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = []
            """),
        requirements_lock="numpy==2.1.0\n",
        constraints="certifi==2026.4.22\n",
    )
    report = vdt.collect(tmp_path)
    d8 = [d for d in report.drifts if d.drift_class == "D8"]
    assert not d8, report.drifts


def test_live_tree_has_no_d8_divergence(vdt: ModuleType) -> None:
    """Regression guard: the shipping tree's constraints/security.txt
    pins must agree with every requirements*.lock pin for the same
    package. A D8 fire here means a /constraints bump landed without a
    lock regeneration — the setup-breaking divergence is back."""
    report = vdt.collect(REPO_ROOT)
    d8 = [d for d in report.drifts if d.drift_class == "D8"]
    assert not d8, (
        "D8 fire on live tree — a constraints/security.txt pin disagrees "
        "with a lock pin; `pip install -c constraints -r lock` will be "
        "ResolutionImpossible. Run `make deps-update` and commit the "
        "regenerated locks:\n  " + "\n  ".join(str(d) for d in d8)
    )


# ---------------------------------------------------------------------------
# Contract 3 — deterministic output
# ---------------------------------------------------------------------------


def test_collect_is_deterministic(vdt: ModuleType, tmp_path: Path) -> None:
    _seed_minimal_repo(
        tmp_path,
        pyproject=dedent("""
            [project]
            name = "fake"
            version = "0.0.0"
            dependencies = ["foo>=2.0.0", "bar>=3.0.0"]
            """),
        requirements_txt="foo>=1.0.0\nbar>=2.0.0\n",
    )
    a = vdt.collect(tmp_path).to_dict()
    b = vdt.collect(tmp_path).to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

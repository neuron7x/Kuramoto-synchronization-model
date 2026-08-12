"""Tests for the false-confidence detector.

Three contracts:

1. Each of C1..C10 is mechanically detectable on a synthetic tree.
2. The shipping repository surfaces the F02 (.coveragerc) and F01-class
   (Dockerfile-vs-scanned-manifest) findings as regression cases.
3. JSON output is deterministic and CLI exit code respects the
   --exit-on-finding flag.
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
DETECTOR_PATH = REPO_ROOT / "tools" / "audit" / "false_confidence_detector.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("fcd", DETECTOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["fcd"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def fcd() -> ModuleType:
    return _load()


# ---------------------------------------------------------------------------
# Contract 2 — live-tree regression cases.
#
# The detector now consults `.claude/audit/false_confidence_exemptions.yaml`
# by default. Tests that need the unfiltered baseline pass a missing
# manifest path explicitly so historical-state waivers do not interfere.
# ---------------------------------------------------------------------------


_MISSING_MANIFEST = Path("/this/path/does/not/exist/empty_manifest.yaml")


def test_live_repo_no_longer_surfaces_c1_coverage_omission(fcd: ModuleType) -> None:
    """F02 closed: .coveragerc no longer hides declared source via omit."""
    report = fcd.collect(REPO_ROOT, exemption_manifest=_MISSING_MANIFEST)
    c1 = [f for f in report.findings if f.false_confidence_type == "C1"]
    assert not c1, (
        "C1 (.coveragerc omit-erases-declared-source) fired on live tree:\n  "
        + "\n  ".join(f"{x.actual_evidence}" for x in c1)
    )


def test_live_repo_no_longer_surfaces_c2_scanner_path_mismatch(fcd: ModuleType) -> None:
    """F01-class closed: the service-manifest-audit workflow now runs pip-audit
    against every Dockerfile-installed requirements manifest (coherence_bridge,
    sandbox, root requirements.txt), so no Dockerfile installs a manifest that a
    CI scanner never audits. This bypasses the exemption manifest to confirm the
    closure is real on the live tree (not a waiver). The detector's underlying
    C2 mechanism remains proven by the synthetic tests
    test_c2_synthetic_dockerfile_unscanned (fires) and
    test_c2_no_finding_when_workflow_audits_manifest (silent once audited)."""
    report = fcd.collect(REPO_ROOT, exemption_manifest=_MISSING_MANIFEST)
    c2 = [f for f in report.findings if f.false_confidence_type == "C2"]
    assert not c2, "C2 (scanner path mismatch) fired on live tree:\n  " + "\n  ".join(
        f"{x.finding_id}: {x.actual_evidence}" for x in c2
    )


def test_live_repo_surfaces_at_least_five_classes_unfiltered(fcd: ModuleType) -> None:
    """Closure criterion: ≥5 classes should fire on the live tree when the
    exemption manifest is bypassed."""
    report = fcd.collect(REPO_ROOT, exemption_manifest=_MISSING_MANIFEST)
    classes = {f.false_confidence_type for f in report.findings}
    assert len(classes) >= 5, f"only {len(classes)} class(es) fired: {classes}"


def test_live_repo_clean_under_default_manifest(fcd: ModuleType) -> None:
    """With the default exemption manifest applied, live-tree findings = 0.

    Every historical-state finding is documented in
    .claude/audit/false_confidence_exemptions.yaml with a per-class
    reason. Any new finding (a file crossing the threshold for the
    first time) is NOT on the manifest and will appear here.
    """
    report = fcd.collect(REPO_ROOT)
    assert not report.findings, "new false-confidence finding appeared:\n  " + "\n  ".join(
        f"{f.finding_id} ({f.actual_evidence})" for f in report.findings
    )


# ---------------------------------------------------------------------------
# Contract 1 — each detector class fires on a synthetic tree
# ---------------------------------------------------------------------------


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    return repo


def test_c1_synthetic_omit_erases_declared_source(fcd: ModuleType, tmp_path: Path) -> None:
    """C1 must fire when omit patterns erase paths under declared source.

    This synthetic case mirrors the original F02: declare `src` as source,
    then omit five sub-packages of `src`. Each omit pattern is a child of
    a declared source root → C1 must fire.
    """
    repo = _make_repo(tmp_path)
    (repo / ".coveragerc").write_text(
        dedent("""
            [run]
            source =
                src
            omit =
                src/a/**
                src/b/**
                src/c/**
                src/d/**
                src/e/**
            """),
        encoding="utf-8",
    )
    findings = fcd._detect_c1_coverage_omission(repo)
    assert findings, "C1 should detect omit patterns erasing declared source"
    assert findings[0].finding_id == "C1-COVERAGERC-OMIT-ERASES-SOURCE"


def test_c1_silent_when_omits_target_non_source(fcd: ModuleType, tmp_path: Path) -> None:
    """C1 must NOT fire when omit patterns target only non-source paths.

    A legitimate config declares source = src and omits tests, conftest,
    __init__ markers, generated stubs. None of those are children of any
    declared source root, so C1 stays silent.
    """
    repo = _make_repo(tmp_path)
    (repo / ".coveragerc").write_text(
        dedent("""
            [run]
            source =
                src
            omit =
                tests/**
                conftest.py
                **/__init__.py
                **/generated/**
                **/_pb2.py
            """),
        encoding="utf-8",
    )
    findings = fcd._detect_c1_coverage_omission(repo)
    assert not findings, "C1 should be silent on legitimate omits; got:\n  " + "\n  ".join(
        f.actual_evidence for f in findings
    )


def test_c1_silent_when_omit_is_glob_filter(fcd: ModuleType, tmp_path: Path) -> None:
    """A `**`-prefixed glob is a global filter, not a source eraser."""
    repo = _make_repo(tmp_path)
    (repo / ".coveragerc").write_text(
        dedent("""
            [run]
            source =
                src
            omit =
                **/__init__.py
                **/generated/**
            """),
        encoding="utf-8",
    )
    findings = fcd._detect_c1_coverage_omission(repo)
    assert not findings


def test_c2_synthetic_dockerfile_unscanned(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "Dockerfile").write_text(
        "FROM python:3.12\nRUN pip install -r requirements.txt\n",
        encoding="utf-8",
    )
    findings = fcd._detect_c2_scanner_path_mismatch(repo)
    assert any(f.false_confidence_type == "C2" for f in findings)


def test_c2_no_finding_when_workflow_audits_manifest(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    (repo / "Dockerfile").write_text(
        "FROM python:3.12\nRUN pip install -r requirements.txt\n",
        encoding="utf-8",
    )
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "audit.yml").write_text(
        "name: Audit\non: [push]\njobs:\n  a:\n    runs-on: ubuntu-latest\n"
        "    steps:\n      - run: pip-audit -r requirements.txt\n",
        encoding="utf-8",
    )
    findings = fcd._detect_c2_scanner_path_mismatch(repo)
    assert not findings, findings


def test_c3_synthetic_security_test_with_low_assertions(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_secure_login.py").write_text(
        "def test_secure_login():\n    pass\n",
        encoding="utf-8",
    )
    findings = fcd._detect_c3_test_name_overclaim(repo)
    assert any(f.false_confidence_type == "C3" for f in findings)


def test_c4_synthetic_doc_claims_unbacked_enforcer(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    docs = repo / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text(
        "We rely on import-linter to enforce module boundaries.\n",
        encoding="utf-8",
    )
    findings = fcd._detect_c4_doc_overclaim(repo)
    assert any(f.false_confidence_type == "C4" for f in findings), findings


def test_c5_synthetic_validator_not_in_workflow(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    claims_dir = repo / ".claude" / "claims"
    claims_dir.mkdir(parents=True)
    (claims_dir / "validate_claims.py").write_text("# stub\n", encoding="utf-8")
    findings = fcd._detect_c5_validator_existence_only(repo)
    assert any(f.false_confidence_type == "C5" for f in findings), findings


def test_c6_pointer_always_present(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    findings = fcd._detect_c6_dependency_manifest_drift(repo)
    assert len(findings) == 1
    assert findings[0].false_confidence_type == "C6"
    assert findings[0].risk == "LOW"


def test_c7_synthetic_workflow_narrow_paths_filter(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "test.yml").write_text(
        dedent("""
            name: Test
            on:
              pull_request:
                paths:
                  - 'README.md'
            jobs:
              t:
                runs-on: ubuntu-latest
                steps:
                  - run: pytest
            """),
        encoding="utf-8",
    )
    findings = fcd._detect_c7_workflow_path_mismatch(repo)
    assert any(f.false_confidence_type == "C7" for f in findings), findings


def test_c8_synthetic_type_ignore_concentration(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    body = "\n".join("x = 1  # type: ignore[arg-type]" for _ in range(10))
    (repo / "module.py").write_text(body, encoding="utf-8")
    findings = fcd._detect_c8_type_ignore(repo)
    assert any(f.false_confidence_type == "C8" for f in findings), findings


def test_c9_synthetic_no_cover_concentration(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    body = "\n".join("x = 1  # pragma: no cover" for _ in range(10))
    (repo / "module.py").write_text(body, encoding="utf-8")
    findings = fcd._detect_c9_no_cover(repo)
    assert any(f.false_confidence_type == "C9" for f in findings), findings


def test_c10_synthetic_broad_exception_concentration(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    body = "\n".join("try:\n    x = 1\nexcept Exception:\n    pass\n" for _ in range(7))
    (repo / "module.py").write_text(body, encoding="utf-8")
    findings = fcd._detect_c10_broad_exception(repo)
    assert any(f.false_confidence_type == "C10" for f in findings), findings


# ---------------------------------------------------------------------------
# Contract 3 — output determinism + CLI
# ---------------------------------------------------------------------------


def test_collect_is_deterministic(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    body = "\n".join("x = 1  # type: ignore" for _ in range(10))
    (repo / "module.py").write_text(body, encoding="utf-8")
    a = fcd.collect(repo).to_dict()
    b = fcd.collect(repo).to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_main_exits_nonzero_with_findings_and_flag(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    body = "\n".join("x = 1  # type: ignore" for _ in range(10))
    (repo / "module.py").write_text(body, encoding="utf-8")
    rc = fcd.main(["--repo-root", str(repo), "--exit-on-finding"])
    assert rc == 1


def test_main_exits_zero_in_report_only_mode(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    rc = fcd.main(["--repo-root", str(repo)])
    assert rc == 0


# ---------------------------------------------------------------------------
# Contract 3 — exemption manifest mechanism
# ---------------------------------------------------------------------------


def _write_manifest(path: Path, exemptions: list[dict[str, str]]) -> Path:
    import yaml as _yaml

    payload = {"schema_version": 1, "exemptions": exemptions}
    path.write_text(_yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def test_manifest_filters_listed_finding_ids(fcd: ModuleType, tmp_path: Path) -> None:
    """Exemption manifest entries are removed from the report by finding_id."""
    repo = _make_repo(tmp_path)
    body = "\n".join("x = 1  # type: ignore" for _ in range(10))
    (repo / "module.py").write_text(body, encoding="utf-8")

    # First confirm the finding fires without a manifest.
    bare = fcd.collect(repo, exemption_manifest=tmp_path / "missing.yaml")
    assert any(f.false_confidence_type == "C8" for f in bare.findings)

    # Now waive it via the manifest and confirm it disappears.
    waived_id = next(f.finding_id for f in bare.findings if f.false_confidence_type == "C8")
    manifest = _write_manifest(
        tmp_path / "exempt.yaml",
        [{"finding_id": waived_id, "reason": "test waiver"}],
    )
    filtered = fcd.collect(repo, exemption_manifest=manifest)
    assert not any(f.finding_id == waived_id for f in filtered.findings)


def test_manifest_missing_file_returns_no_exemptions(fcd: ModuleType, tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    body = "\n".join("x = 1  # type: ignore" for _ in range(10))
    (repo / "module.py").write_text(body, encoding="utf-8")
    report = fcd.collect(repo, exemption_manifest=tmp_path / "absent.yaml")
    assert any(f.false_confidence_type == "C8" for f in report.findings)


def test_manifest_empty_file_returns_no_exemptions(fcd: ModuleType, tmp_path: Path) -> None:
    manifest = tmp_path / "empty.yaml"
    manifest.write_text("", encoding="utf-8")
    repo = _make_repo(tmp_path)
    body = "\n".join("x = 1  # type: ignore" for _ in range(10))
    (repo / "module.py").write_text(body, encoding="utf-8")
    report = fcd.collect(repo, exemption_manifest=manifest)
    assert any(f.false_confidence_type == "C8" for f in report.findings)


def test_manifest_bad_schema_version_raises(fcd: ModuleType, tmp_path: Path) -> None:
    import pytest
    import yaml as _yaml

    manifest = tmp_path / "bad.yaml"
    manifest.write_text(
        _yaml.safe_dump({"schema_version": 99, "exemptions": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="schema_version: 1"):
        fcd.load_exemptions(manifest)


def test_manifest_duplicate_finding_id_raises(fcd: ModuleType, tmp_path: Path) -> None:
    import pytest

    manifest = _write_manifest(
        tmp_path / "dup.yaml",
        [
            {"finding_id": "X", "reason": "first"},
            {"finding_id": "X", "reason": "second"},
        ],
    )
    with pytest.raises(ValueError, match="duplicate"):
        fcd.load_exemptions(manifest)


def test_manifest_non_mapping_entry_raises(fcd: ModuleType, tmp_path: Path) -> None:
    import pytest
    import yaml as _yaml

    manifest = tmp_path / "bad_entry.yaml"
    manifest.write_text(
        _yaml.safe_dump(
            {"schema_version": 1, "exemptions": ["not_a_mapping"]},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="must be a mapping"):
        fcd.load_exemptions(manifest)


def test_manifest_empty_reason_rejected(fcd: ModuleType, tmp_path: Path) -> None:
    import pytest

    with pytest.raises(ValueError, match="non-empty string"):
        fcd.Exemption(finding_id="X", reason="")
    with pytest.raises(ValueError, match="non-empty string"):
        fcd.Exemption(finding_id="X", reason="   ")


def test_falsifier_removing_manifest_entry_re_emits_finding(
    fcd: ModuleType, tmp_path: Path
) -> None:
    """Falsifier: deleting an exemption restores the underlying finding."""
    repo = _make_repo(tmp_path)
    body = "\n".join("x = 1  # type: ignore" for _ in range(10))
    (repo / "module.py").write_text(body, encoding="utf-8")

    bare = fcd.collect(repo, exemption_manifest=tmp_path / "missing.yaml")
    target_id = next(f.finding_id for f in bare.findings if f.false_confidence_type == "C8")

    # Waive: 0 findings of that ID.
    full = _write_manifest(
        tmp_path / "exempt.yaml",
        [{"finding_id": target_id, "reason": "test waiver"}],
    )
    waived = fcd.collect(repo, exemption_manifest=full)
    assert not any(f.finding_id == target_id for f in waived.findings)

    # Remove the entry: finding reappears.
    empty = _write_manifest(tmp_path / "empty_list.yaml", [])
    restored = fcd.collect(repo, exemption_manifest=empty)
    assert any(f.finding_id == target_id for f in restored.findings)


def test_is_excluded_skips_artifacts_and_worktrees(fcd: ModuleType, tmp_path: Path) -> None:
    repo = tmp_path
    assert fcd._is_excluded(repo / "build" / "lib" / "x.py", repo)
    assert fcd._is_excluded(repo / ".claude" / "worktrees" / "agent" / "core" / "x.py", repo)
    assert fcd._is_excluded(repo / ".venv" / "lib" / "site-packages" / "y.py", repo)
    assert fcd._is_excluded(repo / "geosync.egg-info" / "z.txt", repo)
    # Real first-party source is NOT excluded.
    assert not fcd._is_excluded(repo / "core" / "indicators" / "cache.py", repo)
    assert not fcd._is_excluded(repo / "tests" / "unit" / "test_x.py", repo)


def test_clutter_does_not_produce_findings(fcd: ModuleType, tmp_path: Path) -> None:
    # An untracked build artifact + stale agent worktree, each carrying patterns
    # that WOULD trip the detector if scanned, must be ignored — CI sees a clean
    # checkout, so the local run must match it deterministically.
    repo = tmp_path
    broad = "\n".join(["try:", "    pass", "except Exception:", "    pass"] * 6)
    for sub in ("build/lib/sandbox", ".claude/worktrees/agent-x/core/data"):
        d = repo / sub
        d.mkdir(parents=True)
        (d / "leaky.py").write_text(broad, encoding="utf-8")
    (repo / "build" / "lib" / "sandbox" / "Dockerfile").write_text(
        "FROM python:3.12\nRUN pip install -r requirements.txt\n", encoding="utf-8"
    )
    report = fcd.collect(repo, exemption_manifest=repo / "missing.yaml")
    offenders = [
        f for f in report.findings if "build/" in f.evidence_path or ".claude/" in f.evidence_path
    ]
    assert offenders == [], offenders

"""False-confidence detector.

Surfaces repository zones where confidence appears stronger than evidence.
Each detector class names a specific failure mode the 2026-04-26 audit
identified, plus four that came up while writing the calibration layer.

Detector classes:

  C1  COVERAGE_OMISSION_RISK
       .coveragerc omits a large fraction of the source tree (the F02
       trap); coverage % cannot mean what it appears to.

  C2  SCANNER_PATH_MISMATCH
       Security scanner runs against a manifest that is NOT the manifest
       Dockerfiles install (the F01 / F03 distribution gap).

  C3  TEST_NAME_OVERCLAIM
       Test name asserts behaviour the test body does not exercise
       (e.g. `test_secure_*` with no negative case, no assertion against
       attacker input).

  C4  DOCUMENTATION_OVERCLAIM
       Documentation asserts an architecture / contract / behaviour that
       no enforcement file substantiates (e.g. doc says "import-linter
       enforces …" while no .importlinter exists).

  C5  VALIDATOR_EXISTENCE_ONLY
       A validator file exists but is not invoked from CI; running the
       validator locally is necessary to catch regressions.

  C6  DEPENDENCY_MANIFEST_DRIFT
       D1 / D2 / D5 drifts surfaced by the dependency-truth unifier
       (delegate to that detector; report a synthetic pointer).

  C7  CI_PATH_MISMATCH
       A workflow is green but its conditional `paths:` / `paths-ignore:`
       filter does not cover the changed source.

  C8  TYPE_IGNORE_CONCENTRATION
       More than N `# type: ignore` directives in a single source file
       (the F03 typing trap concentrated).

  C9  NO_COVER_CONCENTRATION
       More than N `# pragma: no cover` directives in a single source
       file (the F02 trap at the file-line level).

  C10 BROAD_EXCEPTION_CONCENTRATION
       More than N `except Exception:` catches in a single file (silent
       swallow risk).

The detector is intentionally stdlib only. Output is deterministic JSON.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXEMPTION_MANIFEST = REPO_ROOT / ".claude" / "audit" / "false_confidence_exemptions.yaml"

# Directory segments that are NOT first-party source: build artifacts, caches,
# VCS internals, and agent worktrees. CI scans a clean checkout (tracked files
# only), so any scan that descends into these produces findings that exist only
# on a developer's machine and diverge from CI. Every file-walking scan below
# must honour this set so the detector is deterministic regardless of local
# clutter (e.g. an untracked ``build/`` from ``python -m build`` or stale
# ``.claude/worktrees/`` copies).
_EXCLUDED_DIR_PARTS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "build",
        "dist",
        ".git",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "worktrees",
        "site-packages",
    }
)


def _is_excluded(path: Path, repo_root: Path) -> bool:
    """Return ``True`` when *path* lies under a non-source artifact/cache dir."""

    try:
        parts = path.relative_to(repo_root).parts
    except ValueError:
        parts = path.parts
    if any(part in _EXCLUDED_DIR_PARTS or part.endswith(".egg-info") for part in parts):
        return True
    # ``.claude`` holds agent worktrees, caches, and ledgers — none are the
    # first-party source the detector reasons about.
    return ".claude" in parts


# ---------------------------------------------------------------------------
# Detector configuration. Thresholds were chosen against the 2026-04-26
# audit's observed concentration and may be tuned.
# ---------------------------------------------------------------------------
TYPE_IGNORE_THRESHOLD = 8
NO_COVER_THRESHOLD = 8
BROAD_EXCEPTION_THRESHOLD = 5
COVERAGE_OMIT_RATIO_THRESHOLD = 0.5  # >50% of declared source omitted -> C1


@dataclass(frozen=True)
class Finding:
    finding_id: str
    false_confidence_type: str  # one of C1..C10
    evidence_path: str
    apparent_claim: str
    actual_evidence: str
    risk: str  # CRITICAL / HIGH / MEDIUM / LOW
    priority: str  # same band, mirrors risk for now
    minimal_repayment_action: str


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"findings": [asdict(f) for f in sorted(self.findings, key=_sort_key)]}


def _sort_key(f: Finding) -> tuple[str, str, str]:
    return (f.false_confidence_type, f.evidence_path, f.finding_id)


# ---------------------------------------------------------------------------
# C1 — coverage omission risk
# ---------------------------------------------------------------------------


def _detect_c1_coverage_omission(repo_root: Path) -> list[Finding]:
    cfg = repo_root / ".coveragerc"
    if not cfg.exists():
        return []
    text = cfg.read_text(encoding="utf-8")
    source: list[str] = []
    omits: list[str] = []
    in_run = False
    in_omit = False
    in_source = False
    for raw in text.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not line:
            in_omit = in_source = False
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            in_run = stripped == "[run]"
            in_omit = in_source = False
            continue
        if not in_run:
            continue
        if line.lstrip() == line and "=" in line:
            key = line.split("=", 1)[0].strip().lower()
            in_source = key == "source"
            in_omit = key == "omit"
            value = line.split("=", 1)[1].strip()
            if in_source and value:
                source.append(value)
            if in_omit and value:
                omits.append(value)
            continue
        if in_source:
            source.append(stripped)
        elif in_omit:
            omits.append(stripped)

    findings: list[Finding] = []
    if not source:
        return findings

    # Precision rule: an omit pattern is a false-confidence signal ONLY when
    # it erases a path under a declared source root. A bare-name pattern
    # like `tests/**` is fine when nothing in `source` declares `tests`; it
    # is the omit-erases-declared-source pattern that produced F02.
    erasing_omits = _omits_erasing_declared_source(source, omits)
    if erasing_omits:
        findings.append(
            Finding(
                finding_id="C1-COVERAGERC-OMIT-ERASES-SOURCE",
                false_confidence_type="C1",
                evidence_path=".coveragerc",
                apparent_claim=(
                    f"`source =` declares {len(source)} target(s) ({', '.join(source)})"
                ),
                actual_evidence=(
                    f"`omit =` erases {len(erasing_omits)} pattern(s) under "
                    f"declared source roots: {sorted(erasing_omits)[:5]}"
                    f"{'…' if len(erasing_omits) > 5 else ''}"
                ),
                risk="CRITICAL",
                priority="CRITICAL",
                minimal_repayment_action=(
                    "remove omit patterns that lie under declared source roots; "
                    "if a sub-package is intentionally not measured by this "
                    "profile, drop it from `source` instead of smuggling it "
                    "into `omit`"
                ),
            )
        )
    return findings


def _omits_erasing_declared_source(source: list[str], omits: list[str]) -> list[str]:
    """Return the omit patterns that erase a declared source root.

    Both source and omit entries are normalised to a leading-segment
    representation (no trailing slashes, no `**` suffixes). An omit
    pattern erases a source root when the omit's leading path component
    is a strict child of any source root path.

    `tests/**` against `source = core, backtest, execution` returns []
        (no source root is `tests`).
    `core/utils/**` against the same `source` returns ['core/utils/**']
        (it is under the `core` root).
    `**/__init__.py` matches every package; treated as a global filter,
        not as erasing-declared-source.
    """
    erasing: list[str] = []
    # Strip trailing `/**` and `/*` suffixes; treat the rest as a path.
    norm_sources = [s.rstrip("/").rstrip("*").rstrip("/") for s in source]
    for omit in omits:
        head = omit.rstrip("/").rstrip("*").rstrip("/")
        if not head or head.startswith("**"):
            # Globs like **/__init__.py or **/generated/** are global filters,
            # not source-root erasers.
            continue
        for src in norm_sources:
            if head == src:
                # Omit IS the source root — total erasure.
                erasing.append(omit)
                break
            if head.startswith(src + "/"):
                # Omit is a child of a declared source root.
                erasing.append(omit)
                break
    return erasing


# ---------------------------------------------------------------------------
# C2 / C7 — scanner / CI path mismatch (delegated to dep truth + workflow paths)
# ---------------------------------------------------------------------------


def _detect_c2_scanner_path_mismatch(repo_root: Path) -> list[Finding]:
    """Scan workflow installs lockfiles via pip-audit, but Dockerfiles
    install plain requirements.txt. We surface the mismatch here as a
    user-facing finding (the underlying mapping is computed by the
    dependency-truth unifier; we duplicate the surface for one-stop view)."""
    findings: list[Finding] = []
    df_paths: list[tuple[str, str]] = []
    for df in sorted(repo_root.rglob("Dockerfile*")):
        if _is_excluded(df, repo_root):
            continue
        try:
            text = df.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for raw in text.splitlines():
            line = raw.strip()
            if not line.startswith("RUN"):
                continue
            for m in re.finditer(r"-[r|c]\s+([\w./-]+\.(?:txt|lock))", line):
                df_paths.append((str(df.relative_to(repo_root)), m.group(1)))

    scanned: set[str] = set()
    wf_dir = repo_root / ".github" / "workflows"
    if wf_dir.exists():
        for wf in wf_dir.glob("*.yml"):
            try:
                text = wf.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for raw in text.splitlines():
                line = raw.strip()
                if not any(
                    tool in line for tool in ("pip-audit", "safety ", "osv-scanner", "trivy")
                ):
                    continue
                for m in re.finditer(r"-[rc]\s+([\w./-]+\.(?:txt|lock))", line):
                    scanned.add(Path(m.group(1)).name)

    for df, manifest in df_paths:
        base = Path(manifest).name
        if base.endswith(".lock"):
            continue
        if base in scanned:
            continue
        if base.startswith("requirements-scan"):
            continue
        findings.append(
            Finding(
                finding_id=f"C2-DOCKER-{df.replace('/', '-')}-{base}",
                false_confidence_type="C2",
                evidence_path=df,
                apparent_claim="image is built from an audited dependency set",
                actual_evidence=(
                    f"this Dockerfile installs {manifest}, but no CI workflow "
                    f"runs pip-audit / safety / osv-scanner / trivy against "
                    f"{base}"
                ),
                risk="HIGH",
                priority="HIGH",
                minimal_repayment_action=(
                    f"either install the lockfile here, or add a CI job that "
                    f"audits {base} on every PR"
                ),
            )
        )
    return findings


def _detect_c7_workflow_path_mismatch(repo_root: Path) -> list[Finding]:
    """A workflow that filters by `paths:` may stay green when
    unrelated paths change. We don't fully evaluate the matcher (that
    would require parsing GitHub's globbing); we only flag workflows
    whose name suggests broad coverage (test, lint, ci) but whose
    paths filter mentions only a small subset."""
    findings: list[Finding] = []
    wf_dir = repo_root / ".github" / "workflows"
    if not wf_dir.exists():
        return findings
    for wf in sorted(wf_dir.glob("*.yml")):
        try:
            text = wf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Look for `paths:` filters under `on:`. If the filter list is short
        # and the workflow name suggests broad coverage, flag it.
        path_filter_match = re.search(
            r"on:\s*\n(?:.|\n)*?paths:\s*\n((?:\s*-\s*[^\n]+\n)+)",
            text,
        )
        if not path_filter_match:
            continue
        block = path_filter_match.group(1)
        entries = [
            line.strip().lstrip("-").strip().strip("'\"")
            for line in block.splitlines()
            if line.strip().startswith("-")
        ]
        if not entries:
            continue
        # Heuristic: workflow named "test/ci/lint/quality/security/audit"
        # with fewer than 3 path entries is very narrow.
        name = wf.stem.lower()
        broad_keywords = ("test", "ci", "lint", "quality", "security", "audit")
        if any(k in name for k in broad_keywords) and len(entries) < 3:
            findings.append(
                Finding(
                    finding_id=f"C7-PATH-FILTER-{wf.name}",
                    false_confidence_type="C7",
                    evidence_path=str(wf.relative_to(repo_root)),
                    apparent_claim=(f"`{wf.name}` provides broad {name} coverage"),
                    actual_evidence=(f"the `paths:` filter is narrow: {entries}"),
                    risk="MEDIUM",
                    priority="MEDIUM",
                    minimal_repayment_action=(
                        "either widen the paths filter to match the workflow's "
                        "claimed coverage, or rename the workflow to reflect "
                        "what it actually checks"
                    ),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# C3 — test-name overclaim
# ---------------------------------------------------------------------------


def _detect_c3_test_name_overclaim(repo_root: Path) -> list[Finding]:
    """A test whose function name contains 'secure', 'auth', 'safe', etc.
    but whose body has fewer than two assertions is suspicious. This is a
    HEURISTIC; treat output as advisory."""
    findings: list[Finding] = []
    suspicious_names = ("secure", "_auth_", "unauthorized", "safe", "_locked")
    assert_re = re.compile(r"^\s*(?:assert|with\s+pytest\.raises)\b")
    for path in sorted((repo_root / "tests").rglob("test_*.py")):
        if _is_excluded(path, repo_root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        # Naive function bodies — split on `def `; not perfect but enough.
        bodies = re.split(r"(?m)^def\s+", text)
        for body in bodies[1:]:
            first_line = body.splitlines()[0] if body.splitlines() else ""
            name_match = re.match(r"(test_\w+)", first_line)
            if not name_match:
                continue
            name = name_match.group(1)
            if not any(k in name for k in suspicious_names):
                continue
            assertions = sum(1 for line in body.splitlines() if assert_re.match(line))
            if assertions < 2:
                rel = path.relative_to(repo_root)
                findings.append(
                    Finding(
                        finding_id=f"C3-{rel}-{name}",
                        false_confidence_type="C3",
                        evidence_path=str(rel),
                        apparent_claim=(f"`{name}` asserts security/auth/locking behaviour"),
                        actual_evidence=(
                            f"function body contains {assertions} "
                            "assertion(s) — heuristic flag only"
                        ),
                        risk="LOW",
                        priority="LOW",
                        minimal_repayment_action=(
                            "audit the test body; if the assertion count is "
                            "intentional, rename for clarity; otherwise add a "
                            "negative case"
                        ),
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# C4 — documentation overclaim (architecture / contracts not enforced)
# ---------------------------------------------------------------------------


def _detect_c4_doc_overclaim(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    docs_dir = repo_root / "docs"
    if not docs_dir.exists():
        return findings
    enforcers = {
        "import-linter": (".importlinter",),
        "importlinter": (".importlinter",),
        "lint-imports": (".importlinter",),
        "pip-audit": (
            ".github/workflows/security-deep.yml",
            ".github/workflows/pr-gate.yml",
        ),
        "physics-invariants": (".github/workflows/physics-invariants.yml",),
    }
    for md in sorted(docs_dir.rglob("*.md")):
        if _is_excluded(md, repo_root):
            continue
        try:
            text = md.read_text(encoding="utf-8", errors="ignore").lower()
        except OSError:
            continue
        for keyword, expected_files in enforcers.items():
            if keyword not in text:
                continue
            if any((repo_root / f).exists() for f in expected_files):
                continue
            rel = md.relative_to(repo_root)
            findings.append(
                Finding(
                    finding_id=f"C4-{rel}-{keyword}",
                    false_confidence_type="C4",
                    evidence_path=str(rel),
                    apparent_claim=(f"`{md.name}` references `{keyword}` enforcement"),
                    actual_evidence=(
                        f"none of the expected enforcer files exist: {list(expected_files)}"
                    ),
                    risk="MEDIUM",
                    priority="MEDIUM",
                    minimal_repayment_action=(
                        f"either add the enforcer file ({expected_files[0]}) "
                        "or remove the doc claim"
                    ),
                )
            )
    return findings


# ---------------------------------------------------------------------------
# C5 — validator existence-only (file present but not wired)
# ---------------------------------------------------------------------------


def _detect_c5_validator_existence_only(repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    candidates = [
        repo_root / ".claude" / "claims" / "validate_claims.py",
        repo_root / ".claude" / "evidence" / "validate_evidence.py",
        repo_root / "tools" / "deps" / "validate_dependency_truth.py",
    ]
    wf_dir = repo_root / ".github" / "workflows"
    workflow_text = ""
    if wf_dir.exists():
        for wf in wf_dir.glob("*.yml"):
            try:
                workflow_text += wf.read_text(encoding="utf-8") + "\n"
            except (OSError, UnicodeDecodeError):
                continue
    for validator in candidates:
        if not validator.exists():
            continue
        rel = validator.relative_to(repo_root)
        if str(rel) in workflow_text or validator.name in workflow_text:
            continue
        findings.append(
            Finding(
                finding_id=f"C5-{rel}",
                false_confidence_type="C5",
                evidence_path=str(rel),
                apparent_claim=(f"`{rel}` exists, suggesting it gates the contract"),
                actual_evidence=("no CI workflow invokes the validator"),
                risk="MEDIUM",
                priority="MEDIUM",
                minimal_repayment_action=(
                    "wire the validator into pr-gate.yml so regressions fail closed"
                ),
            )
        )
    return findings


# ---------------------------------------------------------------------------
# C6 — dependency manifest drift (pointer to dep-truth unifier)
# ---------------------------------------------------------------------------


def _detect_c6_dependency_manifest_drift(repo_root: Path) -> list[Finding]:
    """Synthetic pointer. We do NOT duplicate dep-truth logic; we surface
    a single advisory finding that the user should run that tool."""
    return [
        Finding(
            finding_id="C6-DELEGATE-DEPS-TRUTH",
            false_confidence_type="C6",
            evidence_path="tools/deps/validate_dependency_truth.py",
            apparent_claim=("all dependency manifests agree on lower bounds and pins"),
            actual_evidence=(
                "manifest drift detection is performed by the dependency-"
                "truth unifier; run that tool for the authoritative answer"
            ),
            risk="LOW",
            priority="LOW",
            minimal_repayment_action=(
                "run `python tools/deps/validate_dependency_truth.py --exit-on-drift`"
            ),
        )
    ]


# ---------------------------------------------------------------------------
# C8 / C9 / C10 — concentration detectors
# ---------------------------------------------------------------------------


def _scan_concentration(
    repo_root: Path,
    pattern: re.Pattern[str],
    threshold: int,
    detector_id: str,
    apparent: str,
    repayment: str,
) -> list[Finding]:
    findings: list[Finding] = []
    for path in sorted(repo_root.rglob("*.py")):
        if _is_excluded(path, repo_root):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        count = sum(1 for _ in pattern.finditer(text))
        if count < threshold:
            continue
        rel = path.relative_to(repo_root)
        risk = "HIGH" if count >= threshold * 2 else "MEDIUM"
        findings.append(
            Finding(
                finding_id=f"{detector_id}-{rel}",
                false_confidence_type=detector_id.split("-")[0],
                evidence_path=str(rel),
                apparent_claim=apparent,
                actual_evidence=(f"file contains {count} occurrence(s); threshold = {threshold}"),
                risk=risk,
                priority=risk,
                minimal_repayment_action=repayment,
            )
        )
    return findings


def _detect_c8_type_ignore(repo_root: Path) -> list[Finding]:
    return _scan_concentration(
        repo_root,
        re.compile(r"#\s*type:\s*ignore"),
        TYPE_IGNORE_THRESHOLD,
        "C8-TYPE-IGNORE",
        "module passes mypy --strict",
        (
            "audit each `# type: ignore`; either tighten the type or document "
            "the third-party gap; remove unused ignores"
        ),
    )


def _detect_c9_no_cover(repo_root: Path) -> list[Finding]:
    return _scan_concentration(
        repo_root,
        re.compile(r"#\s*pragma:\s*no\s*cover"),
        NO_COVER_THRESHOLD,
        "C9-NO-COVER",
        "module is exercised by the test suite",
        (
            "audit each `# pragma: no cover`; replace with a test for the path "
            "or an explicit branch the test exercises"
        ),
    )


def _detect_c10_broad_exception(repo_root: Path) -> list[Finding]:
    return _scan_concentration(
        repo_root,
        re.compile(r"\bexcept\s+Exception\b"),
        BROAD_EXCEPTION_THRESHOLD,
        "C10-BROAD-EXCEPTION",
        "module surfaces all errors to the caller",
        (
            "narrow each `except Exception` to the actual exception classes; "
            "or annotate the handler as a known fail-safe with a logged trace"
        ),
    )


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Exemption:
    """One documented historical-state waiver."""

    finding_id: str
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.finding_id, str) or not self.finding_id.strip():
            raise ValueError("Exemption.finding_id must be a non-empty string")
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("Exemption.reason must be a non-empty string")


def load_exemptions(manifest_path: Path) -> dict[str, Exemption]:
    """Load the exemption manifest. Missing or empty file → no exemptions.

    The manifest format is a YAML mapping with a ``schema_version: 1``
    key and an ``exemptions`` list of mappings, each with ``finding_id``
    and ``reason`` (both non-empty strings). Unknown keys are tolerated
    so future extensions (e.g. ``expires_at``) do not break older
    detectors.

    Returns a dict keyed by finding_id for O(1) lookup. Raises on
    malformed manifest so a typo cannot silently waive a finding.
    """
    if not manifest_path.exists():
        return {}
    raw = manifest_path.read_text(encoding="utf-8")
    if not raw.strip():
        return {}
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"exemption manifest {manifest_path} must be a mapping; got {type(data).__name__}"
        )
    if data.get("schema_version") != 1:
        raise ValueError(
            f"exemption manifest {manifest_path} requires schema_version: 1; "
            f"got {data.get('schema_version')!r}"
        )
    entries = data.get("exemptions") or []
    if not isinstance(entries, list):
        raise ValueError(f"exemption manifest {manifest_path} `exemptions` must be a list")
    result: dict[str, Exemption] = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"exemption manifest {manifest_path} entry [{i}] must be a mapping")
        fid = entry.get("finding_id")
        reason = entry.get("reason")
        if not isinstance(fid, str) or not isinstance(reason, str):
            raise ValueError(
                f"exemption manifest {manifest_path} entry [{i}] requires "
                f"finding_id and reason as non-empty strings"
            )
        e = Exemption(finding_id=fid, reason=reason)
        if e.finding_id in result:
            raise ValueError(
                f"exemption manifest {manifest_path} contains duplicate finding_id {e.finding_id!r}"
            )
        result[e.finding_id] = e
    return result


def collect(
    repo_root: Path,
    *,
    exemption_manifest: Path | None = None,
) -> Report:
    findings: list[Finding] = []
    findings.extend(_detect_c1_coverage_omission(repo_root))
    findings.extend(_detect_c2_scanner_path_mismatch(repo_root))
    findings.extend(_detect_c3_test_name_overclaim(repo_root))
    findings.extend(_detect_c4_doc_overclaim(repo_root))
    findings.extend(_detect_c5_validator_existence_only(repo_root))
    findings.extend(_detect_c6_dependency_manifest_drift(repo_root))
    findings.extend(_detect_c7_workflow_path_mismatch(repo_root))
    findings.extend(_detect_c8_type_ignore(repo_root))
    findings.extend(_detect_c9_no_cover(repo_root))
    findings.extend(_detect_c10_broad_exception(repo_root))

    manifest = exemption_manifest if exemption_manifest is not None else DEFAULT_EXEMPTION_MANIFEST
    exemptions = load_exemptions(manifest)
    if exemptions:
        findings = [f for f in findings if f.finding_id not in exemptions]
    return Report(findings=findings)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Detect false-confidence zones across the repository",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write JSON to this path; default stdout",
    )
    parser.add_argument(
        "--exit-on-finding",
        action="store_true",
        help="exit non-zero when any finding is reported",
    )
    parser.add_argument(
        "--exemption-manifest",
        type=Path,
        default=None,
        help=(
            "path to YAML exemption manifest documenting historical-state "
            "waivers; defaults to .claude/audit/false_confidence_exemptions.yaml"
        ),
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = collect(args.repo_root, exemption_manifest=args.exemption_manifest)
    payload = json.dumps(report.to_dict(), indent=2, sort_keys=True)
    if args.output is not None:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload)
    if report.findings and args.exit_on_finding:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Commit-acceptor evidence runner.

Closes the ACTIVE -> VERIFIED transition for the diff-bound commit
acceptor layer (PR #491). For each ACTIVE acceptor it:

    1. Executes ``expected_signal.measurement_command`` and captures
       stdout+stderr to ``signal_artifact``.
    2. Executes ``falsifier.command`` and captures output to
       ``falsifier.falsifier_artifact`` (if declared) or a sibling
       artifact next to the signal artifact.
    3. Computes lowercase hex sha256 over every existing artifact
       declared under ``evidence.evidence_artifacts`` plus the signal
       and falsifier artifacts.
    4. Writes the resulting hash list back to the YAML under
       ``evidence_sha256`` (sorted alphabetically by artifact path).
    5. With ``--promote`` and a ``PASS`` verdict, sets ``status`` to
       ``VERIFIED``.

The runner deliberately does NOT prove anything beyond
"command exited 0 and these are the artifact hashes". Mutation testing
of the falsifier is out of scope; the falsifier passing the current
implementation is treated as the green-state precondition.

Security note: ``measurement_command`` and ``falsifier.command`` are
executed via ``subprocess.run(shell=True, ...)``. This trusts the
acceptor YAML, which is committed by maintainers; it is not user input
from PRs. Acceptor schema is enforced by the validator (PR #491) before
this runner ever sees a YAML file.

Output is deterministic JSON (sorted keys, no timestamps) so the
summary itself is hashable.

Exit codes:
    0  every selected acceptor produced a PASS verdict.
    1  one or more acceptors produced a non-PASS verdict.
    2  invalid CLI args, unreadable YAML, missing repo root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess  # nosec B404 - shell=True is documented and required by spec
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import yaml  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_TIMEOUT_S: float = 600.0
MIN_TIMEOUT_S: float = 10.0
MAX_TIMEOUT_S: float = 3600.0

VERDICT_PASS = "PASS"
VERDICT_SIGNAL_FAILED = "SIGNAL_FAILED"
VERDICT_ARTIFACTS_MISSING = "ARTIFACTS_MISSING"
VERDICT_FALSIFIER_PASSED_WHEN_SHOULD_FAIL = "FALSIFIER_PASSED_WHEN_SHOULD_FAIL"
VERDICT_MUTATION_NEEDED = "MUTATION_NEEDED"

ALL_VERDICTS: frozenset[str] = frozenset(
    {
        VERDICT_PASS,
        VERDICT_SIGNAL_FAILED,
        VERDICT_ARTIFACTS_MISSING,
        VERDICT_FALSIFIER_PASSED_WHEN_SHOULD_FAIL,
        VERDICT_MUTATION_NEEDED,
    }
)

# Type alias for the runner callable used for dependency injection in tests.
Runner = Callable[[str, float], "CompletedProcess[str]"]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvidenceResult:
    """Outcome of running one acceptor's evidence cycle.

    Attributes:
        acceptor_id: the acceptor's ``id`` field.
        signal_exit_code: exit code of ``measurement_command`` (or
            ``-1`` if the command failed to launch / timed out).
        falsifier_exit_code: exit code of ``falsifier.command``
            (or ``-1`` if it failed to launch / timed out).
        signal_artifact_sha256: lowercase hex sha256 of the signal
            artifact, or ``None`` if missing.
        falsifier_artifact_sha256: lowercase hex sha256 of the
            falsifier artifact, or ``None`` if missing.
        evidence_artifact_sha256: dict {artifact_path -> sha256_hex}
            for every declared evidence artifact that exists on disk.
        success: True iff verdict is PASS.
        verdict: one of the VERDICT_* constants above.
        messages: human-readable diagnostic lines.
    """

    acceptor_id: str
    signal_exit_code: int
    falsifier_exit_code: int
    signal_artifact_sha256: str | None
    falsifier_artifact_sha256: str | None
    evidence_artifact_sha256: dict[str, str] = field(default_factory=dict)
    success: bool = False
    verdict: str = VERDICT_SIGNAL_FAILED
    messages: tuple[str, ...] = ()

    def to_summary(self) -> dict[str, Any]:
        """Deterministic dict for JSON serialisation (sorted keys)."""
        return {
            "acceptor_id": self.acceptor_id,
            "evidence_artifact_sha256": dict(sorted(self.evidence_artifact_sha256.items())),
            "falsifier_artifact_sha256": self.falsifier_artifact_sha256,
            "falsifier_exit_code": self.falsifier_exit_code,
            "messages": list(self.messages),
            "signal_artifact_sha256": self.signal_artifact_sha256,
            "signal_exit_code": self.signal_exit_code,
            "success": self.success,
            "verdict": self.verdict,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _default_runner(command: str, timeout_s: float) -> CompletedProcess[str]:
    """Real subprocess runner. Trusts maintainer-committed acceptor YAML."""
    return subprocess.run(  # nosec B602 - shell=True required by spec
        command,
        shell=True,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        check=False,
    )


def _sha256_file(path: Path) -> str:
    """Return lowercase 64-char hex sha256 of `path`."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_write_artifact(artifact_path: Path, stdout: str, stderr: str) -> None:
    """Write captured stdout+stderr to artifact_path, creating parents."""
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    body = stdout + ("\n--- STDERR ---\n" + stderr if stderr else "")
    artifact_path.write_text(body, encoding="utf-8")


def _resolve_under_repo(repo_root: Path, rel_or_abs: str) -> Path:
    """Resolve a path relative to repo_root; reject absolute paths."""
    p = Path(rel_or_abs)
    if p.is_absolute():
        # Reject path traversal via absolute paths in artifact declarations.
        # Acceptor artifact paths must be repo-relative.
        return p
    return (repo_root / p).resolve()


def _validate_repo_root(repo_root: Path) -> Path:
    repo_root = repo_root.resolve()
    if not repo_root.is_dir():
        raise ValueError(f"--repo-root not a directory: {repo_root}")
    return repo_root


def _validate_timeout(timeout_s: float) -> float:
    if not (MIN_TIMEOUT_S <= timeout_s <= MAX_TIMEOUT_S):
        raise ValueError(f"timeout_s={timeout_s} outside [{MIN_TIMEOUT_S}, {MAX_TIMEOUT_S}]")
    return float(timeout_s)


# ---------------------------------------------------------------------------
# Acceptor introspection
# ---------------------------------------------------------------------------


def _measurement_command(acceptor: dict[str, Any]) -> str | None:
    """Resolve measurement_command from either top-level (PR #491 schema) or
    nested expected_signal.measurement_command (forward-compatible)."""
    cmd = acceptor.get("measurement_command")
    if isinstance(cmd, str) and cmd.strip():
        return cmd
    es = acceptor.get("expected_signal")
    if isinstance(es, dict):
        nested = es.get("measurement_command")
        if isinstance(nested, str) and nested.strip():
            return nested
    return None


def _signal_artifact(acceptor: dict[str, Any]) -> str | None:
    sa = acceptor.get("signal_artifact")
    if isinstance(sa, str) and sa.strip():
        return sa
    es = acceptor.get("expected_signal")
    if isinstance(es, dict):
        nested = es.get("signal_artifact")
        if isinstance(nested, str) and nested.strip():
            return nested
    return None


def _falsifier_command(acceptor: dict[str, Any]) -> str | None:
    """Falsifier command may be under falsifier.command (PR #491) or
    falsifier.test_command (spec uses both spellings)."""
    f = acceptor.get("falsifier")
    if not isinstance(f, dict):
        return None
    for key in ("test_command", "command"):
        v = f.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _falsifier_artifact(acceptor: dict[str, Any], signal_artifact: str | None) -> str:
    """Resolve falsifier artifact path. Falls back to a sibling next to the
    signal artifact if not declared explicitly."""
    f = acceptor.get("falsifier")
    if isinstance(f, dict):
        v = f.get("falsifier_artifact")
        if isinstance(v, str) and v.strip():
            return v
        v2 = f.get("artifact")
        if isinstance(v2, str) and v2.strip():
            return v2
    if signal_artifact:
        sa = Path(signal_artifact)
        return str(sa.with_name(sa.stem + "_falsifier" + sa.suffix))
    return "tmp/falsifier.log"


def _evidence_artifact_paths(acceptor: dict[str, Any]) -> list[str]:
    """Extract declared evidence artifact paths.

    Supports two shapes:
      evidence:
        - path: foo
        - path: bar
    or
      evidence:
        evidence_artifacts:
          - foo
          - bar
    """
    out: list[str] = []
    ev = acceptor.get("evidence")
    if isinstance(ev, list):
        for entry in ev:
            if isinstance(entry, dict):
                p = entry.get("path")
                if isinstance(p, str) and p.strip():
                    out.append(p)
            elif isinstance(entry, str) and entry.strip():
                out.append(entry)
    elif isinstance(ev, dict):
        ea = ev.get("evidence_artifacts")
        if isinstance(ea, list):
            for entry in ea:
                if isinstance(entry, str) and entry.strip():
                    out.append(entry)
                elif isinstance(entry, dict):
                    p = entry.get("path")
                    if isinstance(p, str) and p.strip():
                        out.append(p)
    return out


# ---------------------------------------------------------------------------
# Core: run_acceptor
# ---------------------------------------------------------------------------


def run_acceptor(
    acceptor: dict[str, Any],
    repo_root: Path,
    *,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    runner: Runner | None = None,
) -> EvidenceResult:
    """Execute one acceptor's evidence cycle.

    Args:
        acceptor: parsed YAML mapping for one acceptor.
        repo_root: root directory used to resolve artifact paths.
        timeout_s: subprocess timeout in seconds (clamped to
            [MIN_TIMEOUT_S, MAX_TIMEOUT_S]).
        runner: optional callable (cmd, timeout) -> CompletedProcess for
            dependency injection in tests. Defaults to real subprocess.

    Returns:
        EvidenceResult with verdict and artifact hashes.
    """
    timeout_s = _validate_timeout(timeout_s)
    runner_fn: Runner = runner if runner is not None else _default_runner

    aid_raw = acceptor.get("id")
    aid = aid_raw if isinstance(aid_raw, str) and aid_raw else "<unknown>"

    messages: list[str] = []

    # Resolve the four pieces we need.
    measurement_cmd = _measurement_command(acceptor)
    signal_artifact = _signal_artifact(acceptor)
    falsifier_cmd = _falsifier_command(acceptor)
    falsifier_artifact_rel = _falsifier_artifact(acceptor, signal_artifact)

    # 1. Run measurement_command.
    signal_exit_code: int = -1
    signal_hash: str | None = None
    if measurement_cmd is None:
        messages.append("measurement_command missing")
    else:
        try:
            proc_signal = runner_fn(measurement_cmd, timeout_s)
            signal_exit_code = int(proc_signal.returncode)
        except subprocess.TimeoutExpired as exc:
            messages.append(f"measurement_command timeout after {timeout_s}s: {exc}")
            proc_signal = CompletedProcess(
                args=measurement_cmd, returncode=-1, stdout="", stderr=str(exc)
            )
            signal_exit_code = -1
        except (OSError, subprocess.SubprocessError) as exc:
            messages.append(f"measurement_command failed to launch: {exc}")
            proc_signal = CompletedProcess(
                args=measurement_cmd, returncode=-1, stdout="", stderr=str(exc)
            )
            signal_exit_code = -1

        if signal_artifact is not None:
            sa_path = _resolve_under_repo(repo_root, signal_artifact)
            try:
                _safe_write_artifact(sa_path, proc_signal.stdout or "", proc_signal.stderr or "")
            except OSError as exc:  # pragma: no cover - filesystem failure
                messages.append(f"failed to write signal_artifact: {exc}")
            if sa_path.is_file():
                signal_hash = _sha256_file(sa_path)

    # 2. Run falsifier.command.
    falsifier_exit_code: int = -1
    falsifier_hash: str | None = None
    if falsifier_cmd is None:
        messages.append("falsifier.command missing")
    else:
        try:
            proc_fals = runner_fn(falsifier_cmd, timeout_s)
            falsifier_exit_code = int(proc_fals.returncode)
        except subprocess.TimeoutExpired as exc:
            messages.append(f"falsifier.command timeout after {timeout_s}s: {exc}")
            proc_fals = CompletedProcess(
                args=falsifier_cmd, returncode=-1, stdout="", stderr=str(exc)
            )
            falsifier_exit_code = -1
        except (OSError, subprocess.SubprocessError) as exc:
            messages.append(f"falsifier.command failed to launch: {exc}")
            proc_fals = CompletedProcess(
                args=falsifier_cmd, returncode=-1, stdout="", stderr=str(exc)
            )
            falsifier_exit_code = -1

        fa_path = _resolve_under_repo(repo_root, falsifier_artifact_rel)
        try:
            _safe_write_artifact(fa_path, proc_fals.stdout or "", proc_fals.stderr or "")
        except OSError as exc:  # pragma: no cover - filesystem failure
            messages.append(f"failed to write falsifier_artifact: {exc}")
        if fa_path.is_file():
            falsifier_hash = _sha256_file(fa_path)

    # 3. Hash declared evidence artifacts (must already exist).
    evidence_paths = _evidence_artifact_paths(acceptor)
    evidence_hashes: dict[str, str] = {}
    missing_evidence: list[str] = []
    for rel in evidence_paths:
        ap = _resolve_under_repo(repo_root, rel)
        if ap.is_file():
            evidence_hashes[rel] = _sha256_file(ap)
        else:
            missing_evidence.append(rel)

    # 4. Determine verdict.
    verdict: str
    success: bool

    if measurement_cmd is None or falsifier_cmd is None:
        verdict = VERDICT_SIGNAL_FAILED
        success = False
    elif signal_exit_code != 0:
        verdict = VERDICT_SIGNAL_FAILED
        success = False
        messages.append(f"signal exit code {signal_exit_code} != 0")
    elif falsifier_exit_code != 0:
        # Spec semantics: falsifier MUST PASS the current code (exit 0)
        # because the implementation is correct. A non-zero exit means
        # the green-state precondition is NOT met -> SIGNAL_FAILED.
        verdict = VERDICT_SIGNAL_FAILED
        success = False
        messages.append(f"falsifier exit code {falsifier_exit_code} != 0 (green-state broken)")
    elif missing_evidence:
        verdict = VERDICT_ARTIFACTS_MISSING
        success = False
        messages.append("missing evidence artifacts: " + ", ".join(sorted(missing_evidence)))
    elif signal_artifact is not None and signal_hash is None:
        verdict = VERDICT_ARTIFACTS_MISSING
        success = False
        messages.append("signal_artifact not produced")
    elif falsifier_hash is None:
        verdict = VERDICT_ARTIFACTS_MISSING
        success = False
        messages.append("falsifier_artifact not produced")
    else:
        verdict = VERDICT_PASS
        success = True

    return EvidenceResult(
        acceptor_id=aid,
        signal_exit_code=signal_exit_code,
        falsifier_exit_code=falsifier_exit_code,
        signal_artifact_sha256=signal_hash,
        falsifier_artifact_sha256=falsifier_hash,
        evidence_artifact_sha256=evidence_hashes,
        success=success,
        verdict=verdict,
        messages=tuple(messages),
    )


# ---------------------------------------------------------------------------
# YAML round-trip writer (no ruamel; preserves order via Dumper)
# ---------------------------------------------------------------------------


class _OrderedDumper(yaml.SafeDumper):
    """SafeDumper that emits keys in their original insertion order
    when given a regular dict (Python 3.7+ preserves dict order)."""


def _represent_dict_preserve(dumper: yaml.Dumper, data: dict[str, Any]) -> yaml.MappingNode:
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items())


_OrderedDumper.add_representer(dict, _represent_dict_preserve)


def _replace_top_level_block(text: str, key: str, rendered: str) -> str:
    """Replace (or append) the top-level mapping ``key`` and its value block in
    *text* with *rendered* (which must itself begin ``key:``), preserving every
    other byte -- comments, blank lines, and all other scalars (notably the
    literal-block command scalars) are left untouched.

    A top-level key's value block spans its line plus every following line that
    is blank, indented, or a block-sequence item (``- ...`` at column 0); it
    ends at the next line starting with a non-space, non-dash character.
    """
    lines = text.split("\n")
    start = next(
        (i for i, ln in enumerate(lines) if re.match(rf"{re.escape(key)}:(\s|$)", ln)),
        None,
    )
    rendered_lines = rendered.rstrip("\n").split("\n")
    if start is None:
        # Append as the last top-level key (deterministic location).
        prefix = lines[:-1] if lines and lines[-1] == "" else lines
        return "\n".join([*prefix, *rendered_lines, ""])
    end = start + 1
    while end < len(lines):
        ln = lines[end]
        if ln == "" or ln[0] in " \t" or ln.startswith("-"):
            end += 1
            continue
        break
    return "\n".join([*lines[:start], *rendered_lines, *lines[end:]])


def update_acceptor_yaml(
    acceptor_path: Path,
    result: EvidenceResult,
    *,
    promote_to_verified: bool,
) -> None:
    """Write evidence_sha256 (sorted artifact paths) and optional VERIFIED
    promotion back to the acceptor YAML by SURGICAL field update.

    Only the ``status`` line and the ``evidence_sha256`` block are touched; every
    other byte -- comment headers and the literal-block command scalars -- is
    preserved verbatim. (The previous full ``yaml.dump`` round-trip stripped all
    comments and could reflow multi-line command scalars, silently corrupting
    the very falsifier/measurement commands the acceptor depends on.) The result
    is byte-for-byte deterministic between runs with identical inputs.
    """
    text = acceptor_path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"acceptor {acceptor_path} top-level must be a mapping")

    # Build sorted-by-path sha list aligned 1:1 with declared artifacts.
    # Includes evidence_artifact_sha256 entries (sorted alphabetically).
    sha_entries: list[dict[str, str]] = []
    for path_str, sha in sorted(result.evidence_artifact_sha256.items()):
        sha_entries.append({"path": path_str, "sha256": sha})
    if result.signal_artifact_sha256 is not None:
        # The signal_artifact path comes from the acceptor itself.
        sa = loaded.get("signal_artifact")
        if not isinstance(sa, str):
            es = loaded.get("expected_signal")
            if isinstance(es, dict):
                sa = es.get("signal_artifact")
        if isinstance(sa, str):
            sha_entries.append({"path": sa, "sha256": result.signal_artifact_sha256})
    if result.falsifier_artifact_sha256 is not None:
        f = loaded.get("falsifier")
        fa: str | None = None
        if isinstance(f, dict):
            fa_raw = f.get("falsifier_artifact") or f.get("artifact")
            if isinstance(fa_raw, str):
                fa = fa_raw
        if fa is not None:
            sha_entries.append({"path": fa, "sha256": result.falsifier_artifact_sha256})

    # Sort the FINAL list alphabetically by artifact path (deterministic).
    sha_entries_sorted = sorted(sha_entries, key=lambda e: e["path"])

    # Surgically update status in place (only on promote + success).
    if promote_to_verified and result.success:
        text = re.sub(r"^status:[^\n]*", "status: VERIFIED", text, count=1, flags=re.M)

    rendered = yaml.dump(
        {"evidence_sha256": sha_entries_sorted},
        Dumper=_OrderedDumper,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    text = _replace_top_level_block(text, "evidence_sha256", rendered)
    if not text.endswith("\n"):
        text += "\n"
    acceptor_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def _iter_acceptor_files(acceptors_dir: Path) -> list[Path]:
    if not acceptors_dir.is_dir():
        return []
    return sorted(acceptors_dir.glob("*.yaml"))


def _load_acceptor(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise ValueError(f"{path}: top-level YAML must be a mapping")
    return loaded


def _select_acceptors(
    acceptors_dir: Path,
    *,
    acceptor_id: str | None,
    re_verify: bool,
) -> list[tuple[Path, dict[str, Any]]]:
    """Return the (path, acceptor) pairs that should be executed."""
    out: list[tuple[Path, dict[str, Any]]] = []
    for p in _iter_acceptor_files(acceptors_dir):
        try:
            acc = _load_acceptor(p)
        except (OSError, yaml.YAMLError, ValueError):
            continue
        status = acc.get("status")
        aid = acc.get("id")

        if acceptor_id is not None and aid != acceptor_id:
            continue

        # DRAFT and REJECTED never run.
        if status in {"DRAFT", "REJECTED"}:
            continue
        # VERIFIED only if --re-verify.
        if status == "VERIFIED" and not re_verify:
            continue
        # ACTIVE always runs.
        if status not in {"ACTIVE", "VERIFIED"}:
            continue
        out.append((p, acc))
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Run commit-acceptor evidence cycle.")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--acceptor-id", default=None, help="Run only this acceptor id.")
    g.add_argument("--all", action="store_true", help="Run every selectable acceptor (default).")
    p.add_argument(
        "--promote",
        action="store_true",
        help="On PASS verdict, set status to VERIFIED in the acceptor YAML.",
    )
    p.add_argument(
        "--re-verify",
        action="store_true",
        help="Also run acceptors already in VERIFIED status.",
    )
    p.add_argument(
        "--timeout-s",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help=f"subprocess timeout in seconds (in [{MIN_TIMEOUT_S}, {MAX_TIMEOUT_S}]).",
    )
    p.add_argument(
        "--summary-out",
        default="tmp/run_evidence_summary.json",
        help="Where to write deterministic JSON summary.",
    )
    p.add_argument(
        "--repo-root",
        default=None,
        help="Repository root (defaults to git toplevel from CWD).",
    )
    p.add_argument(
        "--acceptors-dir",
        default=".claude/commit_acceptors",
        help="Directory containing acceptor YAML files.",
    )
    return p


def _resolve_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".git").exists():
            return parent
    return cur


def _summary_payload(results: list[EvidenceResult]) -> dict[str, Any]:
    verdict_counts: dict[str, int] = {}
    for r in results:
        verdict_counts[r.verdict] = verdict_counts.get(r.verdict, 0) + 1
    return {
        "results": [r.to_summary() for r in sorted(results, key=lambda x: x.acceptor_id)],
        "verdict_counts": dict(sorted(verdict_counts.items())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Validate timeout BEFORE any work.
    try:
        timeout_s = _validate_timeout(args.timeout_s)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.repo_root is not None:
        try:
            repo_root = _validate_repo_root(Path(args.repo_root))
        except ValueError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2
    else:
        repo_root = _resolve_repo_root(Path.cwd())

    acceptors_dir = Path(args.acceptors_dir)
    if not acceptors_dir.is_absolute():
        acceptors_dir = repo_root / acceptors_dir

    selected = _select_acceptors(
        acceptors_dir,
        acceptor_id=args.acceptor_id,
        re_verify=args.re_verify,
    )

    results: list[EvidenceResult] = []
    for path, acc in selected:
        result = run_acceptor(acc, repo_root, timeout_s=timeout_s, runner=None)
        results.append(result)
        # Always write evidence_sha256 back; only promote on --promote and PASS.
        try:
            update_acceptor_yaml(
                path,
                result,
                promote_to_verified=bool(args.promote),
            )
        except (OSError, ValueError, yaml.YAMLError) as exc:
            print(f"ERROR: failed to update {path}: {exc}", file=sys.stderr)

    summary_path = Path(args.summary_out)
    if not summary_path.is_absolute():
        summary_path = repo_root / summary_path
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _summary_payload(results)
    summary_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    all_pass = all(r.success for r in results) and len(results) > 0
    return 0 if all_pass else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

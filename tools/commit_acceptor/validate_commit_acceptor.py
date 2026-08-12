# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Diff-bound commit acceptor validator.

Validates that every code-modifying commit is governed by at least one
acceptor that declares: promise, diff_scope, falsifier, rollback, evidence,
and (optionally) memory update. The validator is fail-closed: any malformed
acceptor or unbound code change produces a non-zero exit.

Layered with --- but DISTINCT from --- the broader CLAIMS ledger
(.claude/claims/CLAIMS.yaml). CLAIMS is a long-lived contract registry;
COMMIT_ACCEPTORS is a per-commit, diff-bound contract.

Outputs deterministic JSON (sorted keys, no timestamps) so the artefact
itself is hashable.

Exit codes:
    0  valid
    1  validation error (schema, diff binding, AST, evidence mismatch)
    2  malformed YAML, missing acceptors directory, missing policy,
       unreadable file
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess  # nosec B404 - used to read git diff via explicit argv list
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

# Required top-level fields on every acceptor (Step 1 - schema).
REQUIRED_TOP_LEVEL: tuple[str, ...] = (
    "id",
    "status",
    "claim_type",
    "promise",
    "diff_scope",
    "required_python_symbols",
    "expected_signal",
    "measurement_command",
    "signal_artifact",
    "falsifier",
    "rollback_command",
    "rollback_verification_command",
    "memory_update_type",
    "ledger_path",
    "report_path",
)

REQUIRED_DIFF_SCOPE_FIELDS: tuple[str, ...] = ("changed_files", "forbidden_paths")
REQUIRED_FALSIFIER_FIELDS: tuple[str, ...] = ("command", "description")

VALID_STATUSES: frozenset[str] = frozenset({"DRAFT", "ACTIVE", "VERIFIED", "REJECTED"})
VALID_MEMORY_UPDATE_TYPES: frozenset[str] = frozenset({"append", "replace", "none"})

# Fields that must be non-empty after .strip() (audit Hole 4).
NON_EMPTY_TOP_LEVEL_FIELDS: tuple[str, ...] = ("id",)


def _is_safe_repo_relative_path(p: str) -> bool:
    """Return True iff *p* is a safe repo-relative path (audit Hole 3).

    Rejects: leading ``/`` (absolute), backslashes (Windows path
    components on a Unix repo), and any component equal to ``..``.
    Empty/whitespace-only strings are rejected as unsafe.
    """
    if not p or not p.strip():
        return False
    if p.startswith("/"):
        return False
    if "\\" in p:
        return False
    parts = p.split("/")
    if any(part == ".." for part in parts):
        return False
    return True


# Schema fields that MUST NOT appear anywhere in an acceptor (legacy / banned).
FORBIDDEN_SCHEMA_FIELDS: frozenset[str] = frozenset(
    {"forbidden_symbols", "max_files_changed", "generated_at"}
)


@dataclass(frozen=True)
class RequiredFields:
    """Sentinel exposing the required-field tuples to importers."""

    top_level: tuple[str, ...] = REQUIRED_TOP_LEVEL
    diff_scope: tuple[str, ...] = REQUIRED_DIFF_SCOPE_FIELDS
    falsifier: tuple[str, ...] = REQUIRED_FALSIFIER_FIELDS
    statuses: frozenset[str] = VALID_STATUSES
    memory_update_types: frozenset[str] = VALID_MEMORY_UPDATE_TYPES
    forbidden_schema_fields: frozenset[str] = FORBIDDEN_SCHEMA_FIELDS


@dataclass
class ValidationResult:
    """Aggregated outcome of a validation pass."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def merge(self, other: ValidationResult) -> None:
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        for k, v in other.info.items():
            self.info[k] = v


# ---------------------------------------------------------------------------
# YAML loading
# ---------------------------------------------------------------------------


def _load_yaml(path: Path) -> Any:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem failure
        raise RuntimeError(f"unreadable file: {path}: {exc}") from exc
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise RuntimeError(f"malformed YAML in {path}: {exc}") from exc


def _scan_forbidden_fields(node: Any, where: str, errors: list[str]) -> None:
    """Recursively reject any forbidden schema field anywhere in the tree."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and key in FORBIDDEN_SCHEMA_FIELDS:
                errors.append(f"{where}: forbidden schema field '{key}' present")
            _scan_forbidden_fields(value, f"{where}.{key}", errors)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            _scan_forbidden_fields(item, f"{where}[{i}]", errors)


# ---------------------------------------------------------------------------
# Schema validation (Step 4)
# ---------------------------------------------------------------------------


def _validate_single_acceptor(
    path: Path, acceptor: Any, policy: dict[str, Any]
) -> ValidationResult:
    result = ValidationResult()

    if not isinstance(acceptor, dict):
        result.errors.append(f"{path}: top-level YAML must be a mapping")
        return result

    # Forbidden fields scan (anywhere in the tree).
    _scan_forbidden_fields(acceptor, str(path), result.errors)

    # Required top-level fields.
    for field_name in REQUIRED_TOP_LEVEL:
        if field_name not in acceptor:
            result.errors.append(f"{path}: missing required field '{field_name}'")

    # status
    status = acceptor.get("status")
    if status is not None and status not in VALID_STATUSES:
        result.errors.append(f"{path}: status '{status}' not in {sorted(VALID_STATUSES)}")

    # id non-empty after .strip() (audit Hole 4).
    aid_raw = acceptor.get("id")
    if isinstance(aid_raw, str) and not aid_raw.strip():
        result.errors.append(f"{path}: id must be a non-empty string (got empty/whitespace)")

    # promise: reject None / non-dict-or-non-string and reject empty/whitespace
    # content (audit Holes 4 & 5). Canonical schema is a non-empty string;
    # mappings with a non-empty .summary are also accepted.
    if "promise" in acceptor:
        promise = acceptor.get("promise")
        if promise is None:
            result.errors.append(f"{path}: INVALID_PROMISE_BLOCK: promise must not be null")
        elif isinstance(promise, str):
            if not promise.strip():
                result.errors.append(
                    f"{path}: promise must be a non-empty string (got empty/whitespace)"
                )
        elif isinstance(promise, dict):
            summary = promise.get("summary")
            if not isinstance(summary, str) or not summary.strip():
                result.errors.append(f"{path}: promise.summary must be a non-empty string")
        else:
            result.errors.append(
                f"{path}: INVALID_PROMISE_BLOCK: promise must be a string or mapping"
            )

    # claim_type vs policy
    claim_type = acceptor.get("claim_type")
    allowed_claims: dict[str, int] = policy.get("max_changed_files_by_claim_type", {})
    if claim_type is not None and claim_type not in allowed_claims:
        result.errors.append(f"{path}: claim_type '{claim_type}' not declared in policy")

    # diff_scope
    diff_scope = acceptor.get("diff_scope")
    if isinstance(diff_scope, dict):
        for sub in REQUIRED_DIFF_SCOPE_FIELDS:
            if sub not in diff_scope:
                result.errors.append(f"{path}: diff_scope missing required field '{sub}'")
        changed_files = diff_scope.get("changed_files")
        if not isinstance(changed_files, list) or not changed_files:
            result.errors.append(f"{path}: diff_scope.changed_files must be a non-empty list")
        else:
            for i, entry in enumerate(changed_files):
                if not isinstance(entry, dict) or "path" not in entry:
                    result.errors.append(
                        f"{path}: diff_scope.changed_files[{i}] must be a mapping with 'path'"
                    )
                    continue
                # Audit Hole 3: reject path traversal / absolute / Windows
                # separators in changed_files[*].path.
                p_val = entry.get("path")
                if not isinstance(p_val, str) or not _is_safe_repo_relative_path(p_val):
                    result.errors.append(
                        f"{path}: diff_scope.changed_files[{i}].path "
                        f"unsafe (traversal/absolute/backslash): {p_val!r}"
                    )
        forbidden_paths = diff_scope.get("forbidden_paths")
        if not isinstance(forbidden_paths, list):
            result.errors.append(f"{path}: diff_scope.forbidden_paths must be a list")
        else:
            for i, fp in enumerate(forbidden_paths):
                # Audit Hole 3: forbidden_paths are also repo-relative —
                # reject traversal there too for symmetry.
                if not isinstance(fp, str) or not _is_safe_repo_relative_path(fp):
                    result.errors.append(
                        f"{path}: diff_scope.forbidden_paths[{i}] "
                        f"unsafe (traversal/absolute/backslash): {fp!r}"
                    )
    elif diff_scope is not None:
        result.errors.append(f"{path}: diff_scope must be a mapping")

    # falsifier
    falsifier = acceptor.get("falsifier")
    if isinstance(falsifier, dict):
        for sub in REQUIRED_FALSIFIER_FIELDS:
            if sub not in falsifier:
                result.errors.append(f"{path}: falsifier missing required field '{sub}'")
    elif falsifier is not None:
        result.errors.append(f"{path}: falsifier must be a mapping")

    # required_python_symbols
    syms = acceptor.get("required_python_symbols")
    if syms is not None and not isinstance(syms, list):
        result.errors.append(f"{path}: required_python_symbols must be a list")

    # memory_update_type
    mut = acceptor.get("memory_update_type")
    if mut is not None and mut not in VALID_MEMORY_UPDATE_TYPES:
        result.errors.append(
            f"{path}: memory_update_type '{mut}' not in {sorted(VALID_MEMORY_UPDATE_TYPES)}"
        )

    # id <-> filename consistency (template is allowed to live outside the dir)
    aid = acceptor.get("id")
    if isinstance(aid, str) and path.suffix == ".yaml":
        expected_id = path.stem
        # template file lives at .claude/commit_acceptor_template.yaml with id 'template'
        if path.name == "commit_acceptor_template.yaml":
            if aid != "template":
                result.errors.append(f"{path}: template id must be 'template', got '{aid}'")
        elif path.parent.name == "commit_acceptors" and aid != expected_id:
            result.errors.append(f"{path}: id '{aid}' must match filename stem '{expected_id}'")

    # REJECTED requires falsifier.description to explain rejection
    if status == "REJECTED" and isinstance(falsifier, dict):
        desc = falsifier.get("description")
        if not isinstance(desc, str) or len(desc.strip()) < 5:
            result.errors.append(
                f"{path}: REJECTED status requires falsifier.description to explain rejection"
            )

    return result


def validate_acceptors(
    policy: dict[str, Any],
    acceptors: list[tuple[Path, dict[str, Any]]],
) -> ValidationResult:
    """Validate the full set of acceptors against the policy schema."""
    result = ValidationResult()
    seen_ids: dict[str, Path] = {}
    for path, acceptor in acceptors:
        sub = _validate_single_acceptor(path, acceptor, policy)
        result.merge(sub)
        if isinstance(acceptor, dict):
            aid = acceptor.get("id")
            if isinstance(aid, str):
                if aid in seen_ids:
                    result.errors.append(f"{path}: duplicate id '{aid}' (also at {seen_ids[aid]})")
                else:
                    seen_ids[aid] = path
    return result


# ---------------------------------------------------------------------------
# Diff binding (Step 5)
# ---------------------------------------------------------------------------


def _is_governance_markdown(file_path: str, governance_paths: Sequence[str]) -> bool:
    if not file_path.endswith(".md"):
        return False
    return any(file_path.startswith(prefix) for prefix in governance_paths)


def _is_dep_manifest(file_path: str, dep_manifest_basenames: Sequence[str]) -> bool:
    """Treat dependency-manifest files as non-code for diff binding.

    Dependabot-style PRs that bump only ``package-lock.json`` /
    ``package.json`` / ``yarn.lock`` / etc. otherwise force every
    repository onto a per-PR acceptor for purely mechanical bumps.
    The exemption list is policy-controlled (``dep_manifest_paths``
    in ``commit_acceptor_policy.yaml``); workflow YAML and Python
    dependency declarations are intentionally NOT in the default set.
    """
    if not dep_manifest_basenames:
        return False
    # Match by trailing path component (basename) only — "package.json"
    # matches "apps/web/package.json" and "ui/dashboard/package.json"
    # but not arbitrary user-named JSON elsewhere.
    basename = file_path.rsplit("/", 1)[-1]
    return basename in tuple(dep_manifest_basenames)


def _file_is_code(
    file_path: str,
    code_extensions: Sequence[str],
    governance_paths: Sequence[str],
    dep_manifest_basenames: Sequence[str] = (),
) -> bool:
    # Dep-manifest bumps are mechanical and exempt from acceptor binding.
    if _is_dep_manifest(file_path, dep_manifest_basenames):
        return False
    # Markdown under governance paths is ignored for binding.
    if file_path.endswith(".md"):
        return not _is_governance_markdown(file_path, governance_paths)
    return any(file_path.endswith(ext) for ext in code_extensions)


def _git_diff_files(base_ref: str, head_ref: str) -> list[str]:
    proc = subprocess.run(  # nosec B603 - explicit argv list, no shell
        ["git", "diff", "--name-only", f"{base_ref}..{head_ref}"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in proc.stdout.splitlines() if line.strip()]


def validate_diff_binding(
    policy: dict[str, Any],
    acceptors: list[tuple[Path, dict[str, Any]]],
    changed_files: list[str],
    file_loader: Callable[[str], str | None],
) -> ValidationResult:
    """Validate that every changed code file is bound to >=1 acceptor."""
    result = ValidationResult()
    code_extensions: list[str] = list(policy.get("code_file_extensions", []))
    governance_paths: list[str] = list(policy.get("governance_markdown_paths", []))
    forbidden_patterns: list[str] = list(policy.get("forbidden_import_patterns", []))
    dep_manifest_basenames: list[str] = list(policy.get("dep_manifest_paths", []))
    max_by_claim: dict[str, int] = dict(policy.get("max_changed_files_by_claim_type", {}))

    code_files = sorted(
        f
        for f in changed_files
        if _file_is_code(f, code_extensions, governance_paths, dep_manifest_basenames)
    )
    result.info["code_files"] = code_files

    # Build path-to-acceptor index, restricted to ACTIVE/VERIFIED/DRAFT/REJECTED scope.
    path_to_acceptors: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    forbidden_index: list[tuple[Path, dict[str, Any], str]] = []
    for apath, accept in acceptors:
        ds = accept.get("diff_scope") or {}
        for entry in ds.get("changed_files") or []:
            if not isinstance(entry, dict):
                continue
            p = entry.get("path")
            if isinstance(p, str):
                path_to_acceptors.setdefault(p, []).append((apath, accept))
        for fp in ds.get("forbidden_paths") or []:
            if isinstance(fp, str):
                forbidden_index.append((apath, accept, fp))

    # Each changed code file must be bound to >=1 acceptor.
    unbound: list[str] = []
    for cf in code_files:
        if cf not in path_to_acceptors:
            unbound.append(cf)
    if unbound:
        result.errors.append("code change without acceptor: " + ", ".join(sorted(unbound)))

    # forbidden_paths: changed file under a forbidden prefix that is ALSO claimed
    # by the same acceptor's diff_scope is a hard fail.
    for cf in code_files:
        for apath, accept, fp in forbidden_index:
            if cf.startswith(fp):
                claimers = path_to_acceptors.get(cf, [])
                for cap, cacc in claimers:
                    if cap == apath:
                        result.errors.append(
                            f"{apath}: claims '{cf}' which sits under forbidden_path '{fp}'"
                        )

    # Per-claim-type file-count cap.
    counts: dict[Path, int] = {}
    for cf in code_files:
        for apath, _accept in path_to_acceptors.get(cf, []):
            counts[apath] = counts.get(apath, 0) + 1
    for apath, accept in acceptors:
        ct = accept.get("claim_type")
        if not isinstance(ct, str):
            continue
        cap = max_by_claim.get(ct)
        if cap is None:
            continue
        bound = counts.get(apath, 0)
        if bound > cap:
            result.errors.append(
                f"{apath}: bound {bound} files exceeds cap {cap} for claim_type '{ct}'"
            )

    # Forbidden imports: AST-walk every changed .py file.
    for cf in code_files:
        if not cf.endswith(".py"):
            continue
        source = file_loader(cf)
        if source is None:
            # File deleted in HEAD - skip AST scan.
            continue
        try:
            violations = forbidden_imports(source, forbidden_patterns)
        except SyntaxError as exc:
            result.errors.append(f"{cf}: AST parse error: {exc}")
            continue
        if violations:
            for v in violations:
                result.errors.append(f"{cf}: forbidden import '{v}'")

    return result


# ---------------------------------------------------------------------------
# AST forbidden-import check (Step 6)
# ---------------------------------------------------------------------------


def forbidden_imports(source: str, forbidden_patterns: Sequence[str]) -> list[str]:
    """Return list of forbidden imports found in `source` via AST.

    Matches when an imported module name equals a pattern, or starts with
    `pattern + "."`. Comments and string literals are NOT inspected.

    Relative-import semantics (audit holes 1 & 2):
      * ``from . import trading`` IS flagged: the imported alias name
        targets a forbidden module (Hole 1 — bypass closed).
      * ``from .trading import x`` IS NOT flagged: the relative module
        ``.trading`` is a repo-local sibling submodule (Hole 2 — false
        positive removed). Only ``alias.name`` is checked for relative
        imports because that is the bound symbol(s); the relative module
        name itself is repo-local by construction.
    """
    if not source.strip():
        return []
    tree = ast.parse(source)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                for pat in forbidden_patterns:
                    if name == pat or name.startswith(pat + "."):
                        violations.append(name)
                        break
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import: check each bound alias name; the
                # relative module itself is repo-local (Hole 2).
                for alias in node.names:
                    aname = alias.name
                    for pat in forbidden_patterns:
                        if aname == pat or aname.startswith(pat + "."):
                            violations.append(aname)
                            break
                continue
            mod = node.module
            if mod is None:
                continue
            for pat in forbidden_patterns:
                if mod == pat or mod.startswith(pat + "."):
                    violations.append(mod)
                    break
    return violations


# ---------------------------------------------------------------------------
# Evidence hashing (Step 7)
# ---------------------------------------------------------------------------


def compute_artifact_hashes(acceptor: dict[str, Any], repo_root: Path) -> dict[str, str]:
    """Compute sha256 hex digests for every evidence path declared.

    Returns a mapping {path -> sha256-hex}. Missing files map to the
    string "MISSING". The signal_artifact (if declared) is always
    included; explicit `evidence` entries with a `path` are also hashed.
    """
    out: dict[str, str] = {}
    candidates: list[str] = []
    sa = acceptor.get("signal_artifact")
    if isinstance(sa, str):
        candidates.append(sa)
    ev = acceptor.get("evidence") or []
    if isinstance(ev, list):
        for entry in ev:
            if isinstance(entry, dict):
                p = entry.get("path")
                if isinstance(p, str):
                    candidates.append(p)
    for rel in candidates:
        abs_path = (repo_root / rel).resolve()
        if abs_path.is_file():
            data = abs_path.read_bytes()
            out[rel] = hashlib.sha256(data).hexdigest()
        else:
            out[rel] = "MISSING"
    return out


def _evidence_check(acceptor: dict[str, Any], repo_root: Path) -> tuple[list[str], list[str]]:
    """Verify declared evidence sha256 matches actual file hash.

    Returns (errors, warnings). Status DRAFT/ACTIVE: missing -> warning.
    Status VERIFIED: missing or mismatched -> error.
    """
    errors: list[str] = []
    warnings: list[str] = []
    status = acceptor.get("status")
    hashes = compute_artifact_hashes(acceptor, repo_root)
    declared: dict[str, str] = {}
    ev = acceptor.get("evidence") or []
    if isinstance(ev, list):
        for entry in ev:
            if isinstance(entry, dict):
                p = entry.get("path")
                h = entry.get("sha256")
                if isinstance(p, str) and isinstance(h, str):
                    declared[p] = h
    for path_str, actual in hashes.items():
        if actual == "MISSING":
            msg = f"evidence missing: {path_str}"
            if status == "VERIFIED":
                errors.append(msg)
            else:
                warnings.append(msg)
            continue
        expected = declared.get(path_str)
        if expected is not None and expected != actual:
            errors.append(
                f"evidence sha256 mismatch for {path_str}: declared {expected}, actual {actual}"
            )
    return errors, warnings


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


def _load_acceptors(
    acceptors_dir: Path, template_path: Path | None
) -> list[tuple[Path, dict[str, Any]]]:
    if not acceptors_dir.is_dir():
        raise RuntimeError(f"acceptors directory not found: {acceptors_dir}")
    out: list[tuple[Path, dict[str, Any]]] = []
    for p in sorted(acceptors_dir.glob("*.yaml")):
        loaded = _load_yaml(p)
        if not isinstance(loaded, dict):
            raise RuntimeError(f"{p}: top-level YAML must be a mapping")
        out.append((p, loaded))
    if template_path is not None and template_path.is_file():
        loaded = _load_yaml(template_path)
        if isinstance(loaded, dict):
            out.append((template_path, loaded))
    return out


def _filter_acceptors_by_id(
    acceptors: list[tuple[Path, dict[str, Any]]], acceptor_ids: Sequence[str] | None
) -> list[tuple[Path, dict[str, Any]]]:
    """Return only acceptors whose ``id`` is explicitly requested.

    This keeps repository-wide validation as the default while allowing PR-local
    evidence gates to validate a scoped acceptor without surfacing unrelated
    historical evidence warnings. Missing requested IDs are treated as malformed
    invocation errors by the CLI.
    """

    if not acceptor_ids:
        return acceptors
    requested = tuple(dict.fromkeys(acceptor_ids))
    selected = [(path, accept) for path, accept in acceptors if accept.get("id") in requested]
    found = {str(accept.get("id")) for _path, accept in selected}
    missing = [acceptor_id for acceptor_id in requested if acceptor_id not in found]
    if missing:
        raise RuntimeError(f"acceptor id(s) not found: {', '.join(missing)}")
    return selected


# ---------------------------------------------------------------------------
# JSON output (Step 4F)
# ---------------------------------------------------------------------------


def _result_to_json(
    result: ValidationResult,
    acceptors: list[tuple[Path, dict[str, Any]]],
    repo_root: Path,
) -> dict[str, Any]:
    acc_summary: list[dict[str, Any]] = []
    for path, accept in acceptors:
        hashes = compute_artifact_hashes(accept, repo_root)
        acc_summary.append(
            {
                "path": (
                    str(path.relative_to(repo_root))
                    if path.is_relative_to(repo_root)
                    else str(path)
                ),
                "id": accept.get("id"),
                "status": accept.get("status"),
                "claim_type": accept.get("claim_type"),
                "artifact_hashes": dict(sorted(hashes.items())),
            }
        )
    out: dict[str, Any] = {
        "ok": result.ok,
        "errors": sorted(result.errors),
        "warnings": sorted(result.warnings),
        "acceptors": sorted(acc_summary, key=lambda a: a.get("id") or ""),
        "info": {k: result.info[k] for k in sorted(result.info)},
    }
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Validate diff-bound commit acceptors.",
    )
    p.add_argument(
        "acceptors_dir",
        nargs="?",
        default=".claude/commit_acceptors",
        help="Directory containing acceptor YAML files.",
    )
    p.add_argument(
        "--policy",
        default=".claude/commit_acceptor_policy.yaml",
        help="Path to commit acceptor policy YAML.",
    )
    p.add_argument("--base-ref", default=None, help="Git base ref for diff binding.")
    p.add_argument("--head-ref", default=None, help="Git head ref for diff binding.")
    p.add_argument(
        "--require-acceptor-for-code-change",
        action="store_true",
        help="Require every changed code file to be bound to >=1 acceptor.",
    )
    p.add_argument(
        "--summary-out",
        default="tmp/commit_acceptor_validation.json",
        help="Where to write deterministic JSON summary.",
    )
    p.add_argument(
        "--template",
        default=".claude/commit_acceptor_template.yaml",
        help="Path to template acceptor (validated as DRAFT).",
    )
    p.add_argument(
        "--acceptor-id",
        action="append",
        default=None,
        help="Validate only the acceptor with this id; repeat to include multiple ids.",
    )
    return p


def _resolve_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur] + list(cur.parents):
        if (parent / ".git").exists():
            return parent
    return cur


def _make_file_loader(repo_root: Path, head_ref: str | None) -> Callable[[str], str | None]:
    def _load(rel: str) -> str | None:
        if head_ref is None:
            p = repo_root / rel
            if p.is_file():
                try:
                    return p.read_text(encoding="utf-8")
                except OSError:
                    return None
            return None
        # Try git show first; fall back to working tree.
        try:
            proc = subprocess.run(  # nosec B603 - explicit argv
                ["git", "show", f"{head_ref}:{rel}"],
                cwd=repo_root,
                check=False,
                capture_output=True,
                text=True,
            )
            if proc.returncode == 0:
                return proc.stdout
        except (OSError, subprocess.SubprocessError):
            pass
        p = repo_root / rel
        if p.is_file():
            try:
                return p.read_text(encoding="utf-8")
            except OSError:
                return None
        return None

    return _load


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    repo_root = _resolve_repo_root(Path.cwd())

    policy_path = Path(args.policy)
    if not policy_path.is_absolute():
        policy_path = repo_root / policy_path
    if not policy_path.is_file():
        print(f"ERROR: policy file not found: {policy_path}", file=sys.stderr)
        return 2

    try:
        policy_loaded = _load_yaml(policy_path)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if not isinstance(policy_loaded, dict):
        print(f"ERROR: policy {policy_path} must be a mapping", file=sys.stderr)
        return 2
    policy: dict[str, Any] = policy_loaded

    acceptors_dir = Path(args.acceptors_dir)
    if not acceptors_dir.is_absolute():
        acceptors_dir = repo_root / acceptors_dir

    template_path: Path | None = None
    if args.template:
        tp = Path(args.template)
        if not tp.is_absolute():
            tp = repo_root / tp
        template_path = tp if tp.is_file() else None

    try:
        acceptors = _filter_acceptors_by_id(
            _load_acceptors(acceptors_dir, template_path), args.acceptor_id
        )
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    result = validate_acceptors(policy, acceptors)

    # Evidence hashing per acceptor.
    for path, accept in acceptors:
        ev_errors, ev_warnings = _evidence_check(accept, repo_root)
        for e in ev_errors:
            result.errors.append(f"{path}: {e}")
        for w in ev_warnings:
            result.warnings.append(f"{path}: {w}")

    if args.base_ref and args.head_ref:
        try:
            changed = _git_diff_files(args.base_ref, args.head_ref)
        except subprocess.CalledProcessError as exc:
            print(f"ERROR: git diff failed: {exc}", file=sys.stderr)
            return 2
        loader = _make_file_loader(repo_root, args.head_ref)
        binding = validate_diff_binding(policy, acceptors, changed, loader)
        if args.require_acceptor_for_code_change:
            result.merge(binding)
        else:
            # Soft mode: surface as warnings only.
            for e in binding.errors:
                result.warnings.append(f"binding: {e}")
            for k, v in binding.info.items():
                result.info[k] = v

    summary_path = Path(args.summary_out)
    if not summary_path.is_absolute():
        summary_path = repo_root / summary_path
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = _result_to_json(result, acceptors, repo_root)
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    if not result.ok:
        for e in result.errors:
            print(f"ERROR: {e}", file=sys.stderr)
        for w in result.warnings:
            print(f"WARN: {w}", file=sys.stderr)
        return 1

    for w in result.warnings:
        print(f"WARN: {w}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

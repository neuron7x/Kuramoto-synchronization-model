# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Forbidden torch JIT / deserialization API gate (AST-based, fail-closed).

A historical dependency advisory against ``torch`` was dismissed on the
*assumption* that the repository never exercises the TorchScript JIT or the
unsafe (arbitrary-pickle) deserialization paths. This scanner converts that
assumption into an enforced invariant: any reintroduction of a forbidden API
fails the gate.

Forbidden APIs
--------------
* ``torch.jit.script``   — compiles arbitrary Python into TorchScript.
* ``torch.jit.trace``    — traces arbitrary Python into TorchScript.
* ``torch.jit.load``     — deserializes a TorchScript archive (code + tensors).
* ``torch.load``         — pickle-based deserialization. Permitted **only**
  when called with the literal keyword ``weights_only=True``, which restricts
  the unpickler to tensor storages and rejects arbitrary object reconstruction.
  Any ``torch.load`` call that omits ``weights_only=True`` (or passes a
  non-literal / falsey value) is an untrusted-deserialization sink and is
  forbidden.

Detection is AST-based, not regex-based: it resolves attribute chains
(``torch.jit.script``) and import aliases (``import torch.jit as J;
J.script(...)`` / ``from torch.jit import load as L; L(...)``) so that aliasing
cannot smuggle a forbidden call past the gate. Comments and string literals are
never inspected, so documentation mentioning a forbidden symbol does not trip
the gate.

Allowlist
---------
A small, reviewed allowlist may exempt a *specific* ``path::line`` pair where a
legitimately guarded use exists. The allowlist lives at
``tools/security/forbidden_torch_jit_allowlist.json`` and each entry must carry
a human reason. The allowlist is intentionally narrow — it cannot exempt a
whole file or an API globally, only an exact source location.

Exit codes
----------
0  no unreviewed forbidden API usage found.
1  one or more unreviewed forbidden usages found (file:line reported).
2  malformed allowlist or unreadable input.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Policy constants
# ---------------------------------------------------------------------------

# Fully-qualified forbidden call targets that are *unconditionally* forbidden.
UNCONDITIONAL_FORBIDDEN: frozenset[str] = frozenset(
    {
        "torch.jit.script",
        "torch.jit.trace",
        "torch.jit.load",
    }
)

# ``torch.load`` is conditionally permitted (see module docstring).
CONDITIONAL_LOAD: str = "torch.load"

# Directories that are never scanned (vendored / generated / VCS noise).
SKIP_DIR_NAMES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "build",
        "dist",
    }
)

# Paths (relative, POSIX) that are part of the gate machinery itself and are
# therefore excluded from the scan: the scanner names the forbidden symbols in
# its own policy strings, and the gate's own tests construct forbidden calls as
# fixtures to prove detection works.
SELF_EXEMPT_RELPATHS: frozenset[str] = frozenset(
    {
        "tools/security/check_forbidden_torch_jit.py",
        "tests/tools/test_forbidden_torch_jit.py",
    }
)

DEFAULT_ALLOWLIST_RELPATH: str = "tools/security/forbidden_torch_jit_allowlist.json"


@dataclass(frozen=True)
class Finding:
    """A single forbidden-API usage located in source."""

    relpath: str
    line: int
    col: int
    api: str
    detail: str

    @property
    def location(self) -> str:
        return f"{self.relpath}:{self.line}"

    def render(self) -> str:
        return f"{self.relpath}:{self.line}:{self.col}: {self.api} — {self.detail}"


@dataclass(frozen=True)
class AllowlistEntry:
    """A reviewed exemption for an exact ``path::line`` location."""

    path: str
    line: int
    api: str
    reason: str

    @property
    def key(self) -> tuple[str, int, str]:
        return (self.path, self.line, self.api)


# ---------------------------------------------------------------------------
# Import-alias resolution
# ---------------------------------------------------------------------------


def _build_alias_map(tree: ast.Module) -> dict[str, str]:
    """Map local binding names to their fully-qualified torch dotted path.

    Examples handled::

        import torch                      -> {"torch": "torch"}
        import torch.jit                  -> {"torch.jit": "torch.jit", ...}
        import torch.jit as J             -> {"J": "torch.jit"}
        from torch import jit             -> {"jit": "torch.jit"}
        from torch import load as tl      -> {"tl": "torch.load"}
        from torch.jit import script as s -> {"s": "torch.jit.script"}

    Only torch-rooted symbols are recorded; everything else is ignored.
    """
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                full = alias.name
                if full != "torch" and not full.startswith("torch."):
                    continue
                if alias.asname:
                    aliases[alias.asname] = full
                else:
                    # ``import torch.jit`` binds the top name ``torch`` locally,
                    # but the dotted form is also resolvable.
                    bound = full.split(".", 1)[0]
                    aliases.setdefault(bound, bound)
                    aliases[full] = full
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            module = node.module
            if module is None:
                continue
            if module != "torch" and not module.startswith("torch."):
                continue
            for alias in node.names:
                full = f"{module}.{alias.name}"
                local = alias.asname or alias.name
                aliases[local] = full
    return aliases


def _resolve_attr_chain(node: ast.expr) -> list[str] | None:
    """Return the dotted-name components of an attribute/name chain.

    ``torch.jit.script`` -> ["torch", "jit", "script"]. Returns ``None`` if the
    chain is not a pure Name/Attribute spine (e.g. a subscript or call result).
    """
    parts: list[str] = []
    cur: ast.expr = node
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if not isinstance(cur, ast.Name):
        return None
    parts.append(cur.id)
    parts.reverse()
    return parts


def _canonical_call_target(func: ast.expr, aliases: dict[str, str]) -> str | None:
    """Resolve a call's func expression to a canonical ``torch.*`` dotted name.

    Applies the import-alias map to the head of the chain so that aliased
    imports resolve to their true torch target.
    """
    parts = _resolve_attr_chain(func)
    if parts is None:
        return None
    head = parts[0]
    if head not in aliases:
        return None
    resolved_head = aliases[head]
    tail = parts[1:]
    return ".".join([resolved_head, *tail]) if tail else resolved_head


def _load_is_guarded(call: ast.Call) -> bool:
    """True iff a ``torch.load`` call passes the literal ``weights_only=True``.

    A non-literal value (variable, attribute, expression) is treated as
    *unguarded*: the gate demands a statically provable ``True`` so that the
    untrusted-deserialization path cannot be re-enabled at runtime.
    """
    for kw in call.keywords:
        if kw.arg == "weights_only":
            value = kw.value
            return isinstance(value, ast.Constant) and value.value is True
    return False


# ---------------------------------------------------------------------------
# Per-file scan
# ---------------------------------------------------------------------------


def scan_source(source: str, relpath: str) -> list[Finding]:
    """AST-scan a single source string; return forbidden findings.

    Raises ``SyntaxError`` if *source* is not parseable.
    """
    tree = ast.parse(source)
    aliases = _build_alias_map(tree)
    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = _canonical_call_target(node.func, aliases)
        if target is None:
            continue
        if target in UNCONDITIONAL_FORBIDDEN:
            findings.append(
                Finding(
                    relpath=relpath,
                    line=node.lineno,
                    col=node.col_offset,
                    api=target,
                    detail="TorchScript JIT / code-archive API is forbidden",
                )
            )
        elif target == CONDITIONAL_LOAD:
            if not _load_is_guarded(node):
                findings.append(
                    Finding(
                        relpath=relpath,
                        line=node.lineno,
                        col=node.col_offset,
                        api=target,
                        detail=(
                            "untrusted deserialization: call must pass the literal "
                            "weights_only=True"
                        ),
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Repo walk + allowlist
# ---------------------------------------------------------------------------


def iter_python_files(root: Path) -> list[Path]:
    """Return sorted list of ``*.py`` files under *root*, skipping noise dirs."""
    out: list[Path] = []
    for path in sorted(root.rglob("*.py")):
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIR_NAMES for part in rel_parts):
            continue
        out.append(path)
    return out


def load_allowlist(path: Path) -> list[AllowlistEntry]:
    """Parse the reviewed allowlist JSON; raise ``ValueError`` if malformed."""
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"unreadable allowlist {path}: {exc}") from exc
    if not isinstance(raw, dict) or "entries" not in raw:
        raise ValueError(f"allowlist {path} must be an object with an 'entries' list")
    entries_raw = raw["entries"]
    if not isinstance(entries_raw, list):
        raise ValueError(f"allowlist {path}: 'entries' must be a list")
    entries: list[AllowlistEntry] = []
    for i, item in enumerate(entries_raw):
        if not isinstance(item, dict):
            raise ValueError(f"allowlist {path}: entries[{i}] must be an object")
        try:
            entry = AllowlistEntry(
                path=str(item["path"]),
                line=int(item["line"]),
                api=str(item["api"]),
                reason=str(item["reason"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"allowlist {path}: entries[{i}] needs path/line/api/reason: {exc}"
            ) from exc
        if not entry.reason.strip():
            raise ValueError(f"allowlist {path}: entries[{i}].reason must be non-empty")
        entries.append(entry)
    return entries


def scan_repo(
    root: Path,
    allowlist: list[AllowlistEntry],
    *,
    extra_exempt: frozenset[str] = frozenset(),
) -> tuple[list[Finding], list[Finding]]:
    """Scan the whole repo. Return ``(unreviewed, allowed)`` findings.

    *extra_exempt* lets callers (e.g. the gate's own positive tests) widen the
    self-exemption set when scanning fixture trees.
    """
    allowed_keys = {e.key for e in allowlist}
    exempt = SELF_EXEMPT_RELPATHS | extra_exempt
    unreviewed: list[Finding] = []
    allowed: list[Finding] = []
    for file_path in iter_python_files(root):
        relpath = file_path.relative_to(root).as_posix()
        if relpath in exempt:
            continue
        try:
            source = file_path.read_text(encoding="utf-8")
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise ValueError(f"unreadable source {relpath}: {exc}") from exc
        try:
            findings = scan_source(source, relpath)
        except SyntaxError:
            # A non-parseable file cannot contain a resolved torch call; the
            # repo's own ruff/black gates already reject broken syntax.
            continue
        for f in findings:
            if (f.relpath, f.line, f.api) in allowed_keys:
                allowed.append(f)
            else:
                unreviewed.append(f)
    return unreviewed, allowed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _resolve_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for parent in [cur, *cur.parents]:
        if (parent / ".git").exists():
            return parent
    return cur


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed gate for forbidden torch JIT / deserialization APIs.",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root to scan (default: auto-detect from cwd).",
    )
    parser.add_argument(
        "--allowlist",
        default=None,
        help=f"Path to the reviewed allowlist JSON (default: {DEFAULT_ALLOWLIST_RELPATH}).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = Path(args.root).resolve() if args.root else _resolve_repo_root(Path.cwd())

    allowlist_path = Path(args.allowlist) if args.allowlist else root / DEFAULT_ALLOWLIST_RELPATH
    try:
        allowlist = load_allowlist(allowlist_path)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    try:
        unreviewed, allowed = scan_repo(root, allowlist)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    scanned = len(iter_python_files(root))
    print(
        f"forbidden-torch-jit gate: scanned {scanned} python file(s); "
        f"{len(unreviewed)} unreviewed finding(s), {len(allowed)} allowlisted."
    )
    for f in allowed:
        print(f"ALLOWLISTED {f.render()}")

    if unreviewed:
        for f in sorted(unreviewed, key=lambda x: (x.relpath, x.line, x.col)):
            print(f"FORBIDDEN {f.render()}", file=sys.stderr)
        print(
            "ERROR: forbidden torch JIT / deserialization API present. "
            "Remove it, or — only for a legitimately guarded use — add a "
            f"reviewed entry to {DEFAULT_ALLOWLIST_RELPATH}.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fail-closed static gate: every inline ``python -c`` payload in a commit
acceptor's signal/falsifier command MUST be syntactically valid Python.

Motivation
----------
The commit-acceptor *evidence cycle* (``tools/commit_acceptor/run_evidence.py``)
is not executed in CI -- only the structural ``validate_commit_acceptor.py``
runs. That left a hole: an acceptor's ``measurement_command`` or
``falsifier.command`` can carry an inline ``python -c "..."`` payload that does
not even *parse*, so the evidence claim is decorative -- it would crash on the
first byte if anything ever ran it.

This happened at scale because ``run_evidence.py`` rewrites acceptor YAML on
every pass (``yaml.dump``), folding multi-line ``python -c`` scalars and
collapsing newlines into spaces (``import importlib.util spec = ...``), which
turns valid multi-statement source into a ``SyntaxError``.

This gate closes the class fail-closed: it walks every acceptor, extracts every
nested ``python -c`` payload (handling ``bash -c '...'`` wrappers), and compiles
it. Any ``SyntaxError`` fails the build. The fix is to repair the inline command
or, preferably, extract it to a committed single-purpose ``scripts/ci/*.py``
invoked as a single-line command (see ``gauss_bonnet_evidence.py``), which the
YAML round-trip cannot reflow.

Usage
-----
    python scripts/ci/check_acceptor_command_syntax.py [ACCEPTORS_DIR]

Exit codes
----------
    0  every inline python payload compiles.
    1  one or more payloads failed to compile (details on stderr).
    2  usage / IO error.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_ACCEPTORS_DIR = Path(".claude/commit_acceptors")
_PYTHON_EXES = frozenset({"python", "python3"})
_SHELL_EXES = frozenset({"bash", "sh", "dash", "zsh"})
# Recursion bound on nested ``sh -c '... sh -c ...'`` wrappers; far beyond any
# real acceptor, purely a runaway backstop.
_MAX_DEPTH = 8


@dataclass(frozen=True)
class Violation:
    """A single inline python payload that failed to compile."""

    acceptor: str
    field: str
    message: str
    payload_head: str


def _is_python_exe(token: str) -> bool:
    """True for ``python``, ``python3``, ``python3.12`` and basename forms."""
    base = token.rsplit("/", 1)[-1]
    return base in _PYTHON_EXES or base.startswith("python3.")


def _is_shell_exe(token: str) -> bool:
    return token.rsplit("/", 1)[-1] in _SHELL_EXES


def _extract_python_payloads(command: str, depth: int = 0) -> list[str]:
    """Return every inline ``python -c`` source string reachable from *command*,
    descending through ``bash -c '...'`` / ``sh -c '...'`` wrappers.

    Unparseable shell (``shlex`` ValueError, e.g. unbalanced quotes) yields no
    payloads here; that is reported separately as its own violation by the
    caller so a mangled wrapper is never silently skipped.
    """
    if depth > _MAX_DEPTH:
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []

    payloads: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if _is_python_exe(tok):
            j = i + 1
            # Skip interpreter flags until we hit ``-c`` or a non-flag.
            while j < len(tokens) and tokens[j] != "-c" and tokens[j].startswith("-"):
                j += 1
            if j < len(tokens) and tokens[j] == "-c" and j + 1 < len(tokens):
                payloads.append(tokens[j + 1])
                i = j + 2
                continue
        elif _is_shell_exe(tok):
            j = i + 1
            while j < len(tokens) and tokens[j] != "-c" and tokens[j].startswith("-"):
                j += 1
            if j < len(tokens) and tokens[j] == "-c" and j + 1 < len(tokens):
                payloads.extend(_extract_python_payloads(tokens[j + 1], depth + 1))
                i = j + 2
                continue
        i += 1
    return payloads


def _extract_shell_scripts(command: str, depth: int = 0) -> list[str]:
    """Return every inline ``bash -c '...'`` / ``sh -c '...'`` script reachable
    from *command* (the script payloads themselves, for ``bash -n`` checking)."""
    if depth > _MAX_DEPTH:
        return []
    try:
        tokens = shlex.split(command)
    except ValueError:
        return []
    scripts: list[str] = []
    i = 0
    while i < len(tokens):
        if _is_shell_exe(tokens[i]):
            j = i + 1
            while j < len(tokens) and tokens[j] != "-c" and tokens[j].startswith("-"):
                j += 1
            if j < len(tokens) and tokens[j] == "-c" and j + 1 < len(tokens):
                inner = tokens[j + 1]
                scripts.append(inner)
                scripts.extend(_extract_shell_scripts(inner, depth + 1))
                i = j + 2
                continue
        i += 1
    return scripts


_BASH = shutil.which("bash")


def _bash_syntax_error(script: str) -> str | None:
    """Return the first ``bash -n`` syntax error for *script*, or None.

    A no-op (returns None) when ``bash`` is unavailable -- the gate then degrades
    to python-only checking rather than failing spuriously on a bash-less host.
    CI runs on Linux with bash, so the shell leg is enforced there.
    """
    if _BASH is None:
        return None
    proc = subprocess.run(
        [_BASH, "-n"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 0:
        return None
    line = proc.stderr.strip().splitlines()
    return line[-1][:120] if line else f"bash -n exit {proc.returncode}"


def _commands_of(acceptor: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (field_label, command) pairs to check for one acceptor.

    Covers the measurement command (top-level or nested under
    ``expected_signal``) and the falsifier command. Rollback / verification
    commands are intentionally excluded -- they are shell hygiene, not evidence.
    """
    out: list[tuple[str, str]] = []
    mc = acceptor.get("measurement_command")
    if not isinstance(mc, str):
        es = acceptor.get("expected_signal")
        if isinstance(es, dict):
            nested = es.get("measurement_command")
            if isinstance(nested, str):
                mc = nested
    if isinstance(mc, str):
        out.append(("measurement_command", mc))
    fal = acceptor.get("falsifier")
    if isinstance(fal, dict):
        fc = fal.get("command")
        if isinstance(fc, str):
            out.append(("falsifier.command", fc))
    return out


def _check_command(name: str, field: str, command: str) -> list[Violation]:
    violations: list[Violation] = []
    # A wrapper that does not even tokenize is itself a defect.
    try:
        shlex.split(command)
    except ValueError as exc:
        violations.append(Violation(name, field, f"unparseable shell: {exc}", command[:80]))
        return violations
    # Shell layer: the whole command plus every nested bash/sh -c script.
    for script in [command, *_extract_shell_scripts(command)]:
        err = _bash_syntax_error(script)
        if err is not None:
            head = " ".join(script.split())[:80]
            violations.append(Violation(name, field, f"bash: {err}", head))
    # Python layer: every nested python -c payload must compile.
    for payload in _extract_python_payloads(command):
        try:
            compile(payload, f"<{name}:{field}>", "exec")
        except SyntaxError as exc:
            head = " ".join(payload.split())[:80]
            violations.append(Violation(name, field, f"{exc.msg} (line {exc.lineno})", head))
    return violations


def scan(acceptors_dir: Path) -> list[Violation]:
    violations: list[Violation] = []
    for path in sorted(acceptors_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:  # malformed YAML is a hard failure
            violations.append(Violation(path.name, "<yaml>", f"YAML error: {exc}", ""))
            continue
        if not isinstance(doc, dict):
            continue
        for field, command in _commands_of(doc):
            violations.extend(_check_command(path.stem, field, command))
    return violations


def selftest() -> int:
    """Prove the gate has teeth: a deliberately broken acceptor MUST be flagged
    and a valid one MUST NOT. Returns 0 iff the gate fires exactly as expected.

    Wired as the acceptor's falsifier so the gate continuously self-validates --
    a green-state probe (exit 0) rather than an inverse mutation test.
    """
    import tempfile

    broken = (
        "id: selftest-broken\n"
        "falsifier:\n"
        "  command: |-\n"
        "    bash -c "
        "'python -c \"import os from sys import path\"'\n"
    )
    valid = (
        "id: selftest-valid\n"
        "falsifier:\n"
        "  command: |-\n"
        "    bash -c "
        "'python -c \"import os; from sys import path\"'\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "broken.yaml").write_text(broken, encoding="utf-8")
        (root / "valid.yaml").write_text(valid, encoding="utf-8")
        flagged = {v.acceptor for v in scan(root)}
    ok = flagged == {"broken"}
    if ok:
        print("OK: gate teeth verified (broken flagged, valid passed)")
        return 0
    print(f"FAIL: selftest expected {{'broken'}}, got {flagged}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] == "--selftest":
        return selftest()
    acceptors_dir = Path(args[0]) if args else DEFAULT_ACCEPTORS_DIR
    if not acceptors_dir.is_dir():
        print(f"acceptors dir not found: {acceptors_dir}", file=sys.stderr)
        return 2

    violations = scan(acceptors_dir)
    if not violations:
        count = len(sorted(acceptors_dir.glob("*.yaml")))
        print(f"OK: inline python payloads compile across {count} acceptors")
        return 0

    print(
        f"FAIL: {len(violations)} inline-command syntax violation(s):",
        file=sys.stderr,
    )
    for v in violations:
        print(f"  - {v.acceptor} [{v.field}]: {v.message}", file=sys.stderr)
        if v.payload_head:
            print(f"      payload: {v.payload_head}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

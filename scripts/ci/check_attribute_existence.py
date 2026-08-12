#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""``getattr(module, "name", default)`` where the module has no such name.

This gate exists for one line of code::

    # geosync/core/security/incident.py -- IncidentResponse._kill_switch
    activate = getattr(kill_switch, "activate", None)
    if callable(activate):
        activate()

``geosync.runtime.kill_switch`` exports ``activate_kill_switch``. There is no
``activate``. So the lookup returned ``None``, ``callable(None)`` was ``False``, and the
emergency halt fell off the end of the function. A CRITICAL security incident -- key
exfiltration -- filed itself neatly and left the system trading. No exception, no log,
no halt.

**``getattr`` with a default IS a silent fallback.** It is the runtime equivalent of a
config naming a module that no longer exists: a name that resolves to nothing, and a
language that answers "nothing" rather than raising. Aimed at a safety path, it makes the
failure invisible by construction -- there is no error to see, only an action that never
happened.

Scope is deliberately narrow, so a RED here is always a real defect:

  * FIRST-PARTY modules only (``geosync.*``). ``getattr(numpy, "bfloat16", None)`` or
    ``getattr(pydantic, "AliasChoices", None)`` is legitimate feature-detection against a
    dependency whose version you do not control -- that is what the default is FOR. We
    control geosync; a missing name there is a bug, not a version.
  * Only a constant string attribute (``getattr(m, "x")``); a computed name is out of
    scope and stays so.
  * Resolution is by PARSING the module file, never by importing it. Importing to check a
    name is how ``configs/templates/*.j2`` came to execute another project's ``core/``
    package: import consults sys.path, and answers with whatever else defines the name.

FALSIFICATION: restore the ``getattr(kill_switch, "activate", None)`` line and this gate
must go RED.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOT = REPO_ROOT / "geosync"


def _module_file(dotted: str) -> Path | None:
    """Resolve ``geosync.a.b`` to a file on disk. Never imports."""
    if not dotted.startswith("geosync"):
        return None
    rel = Path(*dotted.split("."))
    for candidate in (REPO_ROOT / rel.with_suffix(".py"), REPO_ROOT / rel / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _top_level_names(module_file: Path) -> set[str]:
    """Every name the module binds at module scope. Parsed, never executed.

    Descends into ``try``/``if``/``with`` at module level, because a CONDITIONAL binding
    is still a binding -- and it is exactly how an optional dependency is handled::

        try:
            from deap import base
        except ModuleNotFoundError:
            _DEAP_AVAILABLE = False
        else:
            _DEAP_AVAILABLE = True

    A first draft of this gate walked only the flat ``tree.body`` and reported
    ``_DEAP_AVAILABLE`` as missing — a false positive on a name that plainly exists. A
    gate that cries wolf on correct code gets suppressed, and then it is worth less than
    nothing.
    """
    try:
        tree = ast.parse(module_file.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()

    names: set[str] = set()

    def collect(body: list[ast.stmt]) -> bool:
        """Returns False if the module star-imports (then no name can be ruled out)."""
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for a in node.names:
                    if a.name == "*":
                        return False
                    names.add(a.asname or a.name.split(".")[0])
            elif isinstance(node, ast.Try):
                for sub in (node.body, node.orelse, node.finalbody):
                    if not collect(sub):
                        return False
                for handler in node.handlers:
                    if not collect(handler.body):
                        return False
            elif isinstance(node, (ast.If, ast.With)):
                if not collect(node.body):
                    return False
                if isinstance(node, ast.If) and not collect(node.orelse):
                    return False
        return True

    if not collect(tree.body):
        return set()
    return names


def _imported_modules(tree: ast.Module) -> dict[str, str]:
    """Local name -> dotted module path, for names bound to a MODULE."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out[a.asname or a.name.split(".")[0]] = a.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            for a in node.names:
                out[a.asname or a.name] = f"{node.module}.{a.name}"
    return out


def find_dangling_getattr() -> list[str]:
    violations: list[str] = []
    for path in sorted(SCAN_ROOT.rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        modules = _imported_modules(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)):
                continue
            if node.func.id != "getattr" or len(node.args) < 2:
                continue
            obj, attr = node.args[0], node.args[1]
            if not (isinstance(obj, ast.Name) and isinstance(attr, ast.Constant)):
                continue
            if not isinstance(attr.value, str):
                continue
            dotted = modules.get(obj.id)
            if not dotted:
                continue
            module_file = _module_file(dotted)
            if module_file is None:
                continue  # third-party: a missing name is a VERSION, not a bug
            names = _top_level_names(module_file)
            if not names:
                continue  # star-import: cannot rule anything out
            if attr.value not in names:
                violations.append(
                    f"{rel}:{node.lineno}: getattr({obj.id}, {attr.value!r}) — "
                    f"`{dotted}` defines no `{attr.value}`. With a default this returns "
                    f"None SILENTLY; if it guards an action, the action never happens and "
                    f"nothing says so."
                )
    return violations


def main() -> int:
    violations = find_dangling_getattr()
    if violations:
        print(f"[-] attribute-existence gate RED: {len(violations)} dangling getattr\n")
        for v in violations:
            print(f"  {v}")
        print(
            "\nCall the name directly (an import fails loudly when it is renamed), or fix "
            "the name. A getattr default on a first-party module hides the very failure "
            "you would need to see."
        )
        return 1
    print("[+] attribute-existence gate GREEN: every first-party getattr name resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())

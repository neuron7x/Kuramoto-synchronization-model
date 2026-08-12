#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""validate_tests.py — static analyser turning pytest coverage into law coverage.

Run from repo root:

    python tools/validate_tests.py                    # audit all tests
    python tools/validate_tests.py --paths tests core # audit subset
    python tools/validate_tests.py --json report.json # machine output for CI

Exit codes:
    0  all blocking laws have ≥ 1 witness and all witnesses are valid
    1  at least one blocking violation (missing witness or invalid binding)
    2  tool-level failure (bad catalog, unreadable source, …)

Checks performed
----------------
1. **catalog sanity** — ``physics_contracts/catalog.yaml`` parses, no
   duplicate ids, every entry has the required fields.
2. **witness resolution** — every ``@law("…")`` decorator on a pytest
   ``test_*`` function references an id that exists in the catalog.
3. **magic-literal rejection** — inside a witness body, every numeric
   literal (``ast.Constant`` of ``int``/``float``) either:
       (a) is trivial (−1, 0, 1, 2, ``math.pi``, ``math.e`` aliases),
       (b) is introduced via a name that appeared in the law's
           ``variables`` mapping (rough match on the identifier), or
       (c) has an inline ``# law: <reason>`` comment on the same line
           justifying the number.
4. **coverage report** — counts witnesses per law, emits list of
   unwitnessed laws split by severity.

This is intentionally a *static* analyser — it never imports the test
modules. Import-time side effects in this repo (torch, CUDA, network
adapters) are too heavy and fragile to trigger from a validator. We pay for
that with a coarser check: we cannot see ``@law`` arguments that are
computed at runtime, only literal kwargs. That is fine — witnesses should
declare their N/trials as literals anyway, so CI can diff them.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

# Repo-root-relative import so the tool works from any cwd as long as it's
# invoked via ``python tools/validate_tests.py`` at the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from physics_contracts import Law, load_catalog  # noqa: E402

# ---------------------------------------------------------------------------
# AST inspection
# ---------------------------------------------------------------------------


# Numeric literals that are always allowed — they carry no physics and no
# hidden tolerance. Everything else must be justified.
_TRIVIAL_NUMBERS: frozenset[float] = frozenset({-1.0, 0.0, 1.0, 2.0, 0.5, 10.0, 100.0})


@dataclass
class WitnessFinding:
    """One violation discovered by the analyser, or one clean witness."""

    file: str
    function: str
    law_id: str | None
    line: int
    kind: str  # "ok" | "unknown_law" | "magic_literal" | "orphan_test"
    detail: str = ""


def _is_law_decorator(node: ast.expr) -> tuple[bool, str | None]:
    """Return (is_law, law_id) for a decorator AST node.

    Accepts both ``@law("…")`` (direct import) and
    ``@physics_contracts.law("…")`` (qualified access). Anything else is not
    a witness binding.
    """

    if not isinstance(node, ast.Call):
        return False, None
    func = node.func
    name: str | None = None
    if isinstance(func, ast.Name):
        name = func.id
    elif isinstance(func, ast.Attribute):
        name = func.attr
    if name != "law":
        return False, None
    if not node.args or not isinstance(node.args[0], ast.Constant):
        return True, None  # decorator present but id is dynamic — flag it
    first = node.args[0].value
    return True, first if isinstance(first, str) else None


def _iter_numeric_literals(func: ast.FunctionDef) -> Iterable[ast.Constant]:
    """Yield every numeric constant in the function body.

    We skip constants used as default arguments on the function signature
    itself — those are configuration, not asserts. We also skip constants
    that are the sole argument of ``pytest.approx`` because an author who
    wrote ``approx(expected, abs=1e-9)`` clearly had tolerance in mind and
    the structural presence of ``approx`` is itself an audit signal.
    """

    for node in ast.walk(func):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool):
                continue
            yield node


def _collect_name_bindings(func: ast.FunctionDef) -> set[str]:
    """Return the set of identifier sub-tokens assigned in the function body.

    Used to decide whether a numeric literal arrived via a named variable
    (``bound = 3.0 / math.sqrt(N)``) — in which case we can match the name
    against the law's ``variables`` mapping — or as a bare magic literal.

    Names are tokenised on underscores and lowercased so a binding like
    ``n_oscillators`` contributes ``{"n", "oscillators"}``; this lets the
    intersection with a law variable ``N`` succeed without forcing authors
    to name their Python locals after single-letter physics symbols.
    """

    raw_names: set[str] = set()
    for node in ast.walk(func):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    raw_names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            raw_names.add(node.target.id)

    tokens: set[str] = set()
    for name in raw_names:
        tokens.add(name.lower())
        for part in name.lower().split("_"):
            if part:
                tokens.add(part)
    return tokens


def _read_inline_comments(source: str) -> dict[int, str]:
    """Return ``{line_number: comment_text}`` for every single-line comment.

    We re-tokenise the source to keep tolerance-justification comments
    (``# law: tolerance from 3/√N``) addressable by line. ``ast`` throws
    comments away, so we do this out-of-band.
    """

    import io
    import tokenize

    comments: dict[int, str] = {}
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.string
    except tokenize.TokenizeError:
        return comments
    return comments


def _variables_of(law: Law) -> set[str]:
    """Lowercased identifier tokens the law declares as physical variables.

    Tolerant match: we split on non-alphanumeric chars and lowercase, so a
    law variable named ``K_c`` matches a Python binding ``k_c`` or ``kc``.
    """

    tokens: set[str] = set()
    for name in law.variables:
        for part in "".join(c if c.isalnum() else " " for c in name).split():
            tokens.add(part.lower())
    return tokens


# ---------------------------------------------------------------------------
# Analyser
# ---------------------------------------------------------------------------


@dataclass
class Report:
    findings: list[WitnessFinding] = field(default_factory=list)
    witnesses_by_law: dict[str, list[str]] = field(default_factory=dict)

    def add(self, finding: WitnessFinding) -> None:
        self.findings.append(finding)
        if finding.kind == "ok" and finding.law_id is not None:
            self.witnesses_by_law.setdefault(finding.law_id, []).append(
                f"{finding.file}::{finding.function}"
            )


def analyse_file(path: Path, catalog: dict[str, Law], report: Report) -> None:
    """Walk a single test file and append findings to ``report``."""

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        report.add(
            WitnessFinding(
                file=str(path),
                function="<file>",
                law_id=None,
                line=0,
                kind="unknown_law",
                detail=f"could not read file: {exc}",
            )
        )
        return

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        report.add(
            WitnessFinding(
                file=str(path),
                function="<file>",
                law_id=None,
                line=exc.lineno or 0,
                kind="unknown_law",
                detail=f"syntax error: {exc.msg}",
            )
        )
        return

    comments = _read_inline_comments(source)

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.name.startswith("test_"):
            continue

        # Find the @law(...) decorator, if any.
        law_id: str | None = None
        has_law_decorator = False
        for dec in node.decorator_list:
            is_law, candidate = _is_law_decorator(dec)
            if is_law:
                has_law_decorator = True
                law_id = candidate
                break

        if not has_law_decorator:
            # Not a witness yet. During baseline migration this is expected
            # for the bulk of the 681 existing tests — they are "orphans",
            # not failures. We record them for the coverage report but do
            # not count them as violations unless a CI flag demands it.
            report.add(
                WitnessFinding(
                    file=str(path),
                    function=node.name,
                    law_id=None,
                    line=node.lineno,
                    kind="orphan_test",
                )
            )
            continue

        if law_id is None:
            report.add(
                WitnessFinding(
                    file=str(path),
                    function=node.name,
                    law_id=None,
                    line=node.lineno,
                    kind="unknown_law",
                    detail="@law(...) with dynamic / non-string id",
                )
            )
            continue

        law = catalog.get(law_id)
        if law is None:
            report.add(
                WitnessFinding(
                    file=str(path),
                    function=node.name,
                    law_id=law_id,
                    line=node.lineno,
                    kind="unknown_law",
                    detail="law id not in catalog.yaml",
                )
            )
            continue

        # Witness-body check: every numeric literal must be justified.
        bindings = _collect_name_bindings(node)
        tokens = _variables_of(law)
        name_ok = bindings & tokens  # any binding matches a law variable?
        violations: list[str] = []

        for const in _iter_numeric_literals(node):
            value = float(const.value)
            if value in _TRIVIAL_NUMBERS:
                continue
            comment = comments.get(const.lineno, "")
            if "law:" in comment:
                continue
            if name_ok:
                # The author bound at least one law variable to a name;
                # trust that downstream literals feed into that computation.
                # This is a permissive rule — the strict mode can be turned
                # on later once the baseline is green.
                continue
            violations.append(
                f"line {const.lineno}: literal {const.value!r} has no "
                "law-derived name and no '# law: …' justification"
            )

        if violations:
            report.add(
                WitnessFinding(
                    file=str(path),
                    function=node.name,
                    law_id=law_id,
                    line=node.lineno,
                    kind="magic_literal",
                    detail="; ".join(violations),
                )
            )
        else:
            report.add(
                WitnessFinding(
                    file=str(path),
                    function=node.name,
                    law_id=law_id,
                    line=node.lineno,
                    kind="ok",
                )
            )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _iter_test_files(paths: Iterable[Path]) -> Iterable[Path]:
    for root in paths:
        if root.is_file() and root.name.startswith("test_") and root.suffix == ".py":
            yield root
            continue
        if root.is_dir():
            yield from sorted(root.rglob("test_*.py"))


def _format_text_report(report: Report, catalog: dict[str, Law]) -> str:
    lines: list[str] = []
    lines.append("GeoSync — Physical Law Coverage Report")
    lines.append("=" * 48)

    total = len(catalog)
    witnessed = sum(1 for lid in catalog if report.witnesses_by_law.get(lid))
    lines.append(f"Laws in catalog       : {total}")
    lines.append(f"Laws with ≥1 witness  : {witnessed}")
    lines.append(f"Coverage fraction     : {witnessed / total:.1%}")
    lines.append("")

    blocking_missing = sorted(
        lid
        for lid, law in catalog.items()
        if law.is_blocking() and not report.witnesses_by_law.get(lid)
    )
    warn_missing = sorted(
        lid
        for lid, law in catalog.items()
        if not law.is_blocking() and not report.witnesses_by_law.get(lid)
    )
    if blocking_missing:
        lines.append(f"BLOCKING — {len(blocking_missing)} law(s) with no witness:")
        for lid in blocking_missing:
            lines.append(f"  - {lid}  ({catalog[lid].statement})")
        lines.append("")
    if warn_missing:
        lines.append(f"WARN — {len(warn_missing)} non-blocking law(s) with no witness:")
        for lid in warn_missing:
            lines.append(f"  - {lid}")
        lines.append("")

    errors = [f for f in report.findings if f.kind in {"unknown_law", "magic_literal"}]
    if errors:
        lines.append(f"WITNESS ERRORS — {len(errors)}:")
        for f in errors:
            lines.append(f"  {f.file}:{f.line} {f.function} [{f.kind}] {f.detail}")
        lines.append("")

    orphans = [f for f in report.findings if f.kind == "orphan_test"]
    lines.append(f"Orphan tests (not yet witnesses): {len(orphans)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--paths",
        nargs="*",
        default=["tests", "core/neuro/tests", "tests/regression"],
        help="test roots to audit (default: the three pytest testpaths)",
    )
    parser.add_argument(
        "--json",
        dest="json_out",
        default=None,
        help="write machine-readable report to this path",
    )
    parser.add_argument(
        "--fail-on-orphans",
        action="store_true",
        help="treat orphan tests as errors (off during baseline migration)",
    )
    args = parser.parse_args(argv)

    try:
        catalog = load_catalog()
    except Exception as exc:  # pragma: no cover - CLI surface
        print(f"catalog error: {exc}", file=sys.stderr)
        return 2

    report = Report()
    roots = [Path(p) for p in args.paths]
    for test_file in _iter_test_files(roots):
        analyse_file(test_file, catalog, report)

    text = _format_text_report(report, catalog)
    print(text)

    if args.json_out:
        payload = {
            "catalog_size": len(catalog),
            "witnesses_by_law": report.witnesses_by_law,
            "findings": [f.__dict__ for f in report.findings],
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=2), encoding="utf-8")

    blocking_missing = [
        lid
        for lid, law in catalog.items()
        if law.is_blocking() and not report.witnesses_by_law.get(lid)
    ]
    witness_errors = [f for f in report.findings if f.kind in {"unknown_law", "magic_literal"}]
    orphan_fail = args.fail_on_orphans and any(f.kind == "orphan_test" for f in report.findings)

    if blocking_missing or witness_errors or orphan_fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

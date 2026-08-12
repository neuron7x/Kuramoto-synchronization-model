#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Doc-command gate — every command a document tells you to run must exist.

A quickstart whose commands fail is worse than no quickstart: it costs the reader
the time to discover that the project does not run, and it teaches them not to
trust the rest of the corpus. The 2026-07 audit found the flagship quickstart
failing at three separate steps, both documented paths to dev TLS material dead,
a `docker compose` invocation naming a service the compose file does not define,
and `geosync-cli` — the command around which ten documents are written — absent
from `[project.scripts]` entirely.

This gate checks the two classes that are mechanically decidable:

  D1  `make <target>`  — the target exists in the Makefile
  D2  `python -m <module>` / `python <script.py>` — the module or script exists

Only commands inside fenced code blocks are checked. Prose ("make sure", "make
sense", "make it work") is not a command, and a gate that cannot tell the
difference is a gate that gets switched off.

**Ratchet.** The corpus starts with a known debt (recorded in
``.github/doc_commands_baseline.json``). The gate fails when the debt *grows*, and
rewrites the baseline down when it shrinks — the same monotonic-debt idiom as
``scripts/ci/check_debt_baseline_monotonic.py``. Freezing the debt is honest;
pretending it is zero would be the very defect this file exists to catch.

Stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / ".github" / "doc_commands_baseline.json"

# Records of the past may cite commands that no longer exist.
HISTORICAL_GENRES = (
    "docs/adr/",
    "docs/audit/",
    "docs/audits/",
    "docs/archive/",
    "docs/releases/",
    "docs/reports/",
)

FENCE = re.compile(r"^\s*(?:```|~~~)")
MAKE = re.compile(r"(?:^|[;&|]\s*|\$\s*)make\s+([a-z][a-z0-9_.-]*)")

#: `make no claim` is English, not a build target. Backticked prose is still prose.
MAKE_STOPWORDS = frozenset(
    {
        "no", "not", "sure", "sense", "the", "it", "this", "that", "them", "such",
        "any", "one", "a", "an", "for", "you", "your", "our", "us", "me", "him",
        "her", "these", "those", "trading", "informed", "irreversible", "complex",
        "payment", "modifications", "or", "and", "final", "up", "system", "after",
        "optional", "repository", "law", "hashes", "targets", "observability",
        "non-comparable",
    }
)
PY_MODULE = re.compile(r"python3?\s+-m\s+([A-Za-z_][A-Za-z0-9_.]*)")
PY_SCRIPT = re.compile(r"python3?\s+([A-Za-z_][\w/.-]*\.py)\b")


def make_targets() -> set[str]:
    mk = (REPO / "Makefile").read_text(encoding="utf-8")
    return set(re.findall(r"^([a-zA-Z0-9_.-]+):", mk, re.MULTILINE))


#: A command in backticks is still an instruction to the reader. Scanning only
#: fenced blocks would miss "run `make docs-check-links`" — which is exactly how most
#: of the fictional Make targets were cited.
INLINE_CODE = re.compile(r"`([^`\n]+)`")


def _fenced_commands(text: str):
    """Yield (lineno, text) for command-bearing spans: fenced code blocks, plus
    inline-code spans in prose."""
    fenced = False
    for lineno, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            yield lineno, line
        else:
            for span in INLINE_CODE.findall(line):
                yield lineno, span


#: Third-party and stdlib tooling a document may legitimately tell you to run.
#: These are not first-party modules and their absence from the tree is not a defect.
EXTERNAL_MODULES = frozenset(
    {
        "pip", "venv", "pytest", "build", "mkdocs", "ruff", "mypy", "black", "isort",
        "flake8", "coverage", "pre_commit", "twine", "wheel", "setuptools", "json",
        "http.server", "timeit", "cProfile", "unittest", "pdb", "ensurepip",
        "compileall", "site", "sysconfig", "pipx", "uv", "hypothesis", "IPython",
        "jupyter", "notebook", "grpc_tools.protoc", "alembic", "memory_profiler",
        "line_profiler", "scalene", "py_spy", "tox", "nox",
    }
)

#: A template name in an example is not a missing file. `python my_strategy.py` tells
#: the reader to run *their* script, not one this repository ships.
PLACEHOLDER = re.compile(
    r"^(?:my_|your_|example|foo|bar|<|\{)|(?:^|/)(?:example|template|sample_script)\.py$",
    re.IGNORECASE,
)


def _module_exists(dotted: str) -> bool:
    if dotted in EXTERNAL_MODULES or dotted.split(".")[0] in EXTERNAL_MODULES:
        return True
    parts = dotted.split(".")
    base = REPO.joinpath(*parts)
    if (
        base.with_suffix(".py").is_file()
        or (base / "__init__.py").is_file()
        or base.is_dir()
    ):
        return True
    # An installed distribution (the doc may assume `pip install geosync`).
    try:
        import importlib.util

        return importlib.util.find_spec(dotted) is not None
    except (ImportError, ValueError, ModuleNotFoundError):
        return False


def scan() -> list[dict]:
    targets = make_targets()
    findings: list[dict] = []
    for path in sorted(REPO.glob("docs/**/*.md")) + [REPO / "README.md", REPO / "CONTRIBUTING.md"]:
        if not path.is_file():
            continue
        rel = path.relative_to(REPO).as_posix()
        if rel.startswith(HISTORICAL_GENRES):
            continue
        for lineno, line in _fenced_commands(path.read_text(encoding="utf-8")):
            if line.lstrip().startswith("#"):
                continue  # a comment inside a code block is prose
            for m in MAKE.finditer(line):
                t = m.group(1)
                if t in MAKE_STOPWORDS:
                    continue
                if t not in targets:
                    findings.append(
                        {"path": rel, "line": lineno, "kind": "make", "name": t}
                    )
            for m in PY_MODULE.finditer(line):
                mod = m.group(1)
                if not _module_exists(mod):
                    findings.append(
                        {"path": rel, "line": lineno, "kind": "python -m", "name": mod}
                    )
            for m in PY_SCRIPT.finditer(line):
                script = m.group(1)
                if PLACEHOLDER.match(script):
                    continue
                if not (REPO / script).is_file():
                    findings.append(
                        {"path": rel, "line": lineno, "kind": "script", "name": script}
                    )
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--list", action="store_true", help="print every finding")
    args = ap.parse_args()

    findings = scan()
    # Debt is counted by distinct (kind, name) — the same missing target cited by
    # three documents is one defect, not three.
    debt = sorted({(f["kind"], f["name"]) for f in findings})

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {
                    "_doc": (
                        "Frozen debt: commands cited by documentation that do not exist. "
                        "The gate fails if this grows. Fix a command (or delete the claim) "
                        "and re-run with --write-baseline to ratchet it down."
                    ),
                    "count": len(debt),
                    "missing": [{"kind": k, "name": n} for k, n in debt],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"wrote baseline: {len(debt)} missing command(s)")
        return 0

    if args.list:
        for f in findings:
            print(f"  {f['path']}:{f['line']}: {f['kind']} {f['name']}")

    if not BASELINE.is_file():
        print("no baseline — run with --write-baseline")
        return 1

    base = json.loads(BASELINE.read_text(encoding="utf-8"))
    allowed = {(e["kind"], e["name"]) for e in base["missing"]}
    new = [d for d in debt if d not in allowed]
    fixed = [d for d in allowed if d not in set(debt)]

    print(f"doc-command gate: {len(debt)} missing command(s), baseline {len(allowed)}")

    if new:
        print(f"\ndoc-command gate FAILED: {len(new)} NEW missing command(s)\n")
        for kind, name in new:
            where = [f for f in findings if (f["kind"], f["name"]) == (kind, name)]
            print(f"  {kind} {name}")
            for f in where[:3]:
                print(f"      cited at {f['path']}:{f['line']}")
        print("\n  Either make the command exist, or stop documenting it.")
        return 1

    if fixed:
        print(f"\n{len(fixed)} command(s) fixed since the baseline — ratchet it down:")
        for kind, name in fixed:
            print(f"  + {kind} {name}")
        print("  python scripts/ci/check_doc_commands.py --write-baseline")

    print("doc-command gate held: no new broken commands")
    return 0


if __name__ == "__main__":
    sys.exit(main())

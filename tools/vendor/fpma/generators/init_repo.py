# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
from pathlib import Path

LICENSES = {
    "MIT": """MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
""",
}

GITIGNORE = """.venv/
node_modules/
dist/
bazel-*
.DS_Store
.env
__pycache__/
"""

BAZEL_WORKSPACE = """workspace(name = "{name}")
"""

ROOT_README = """# {name}

This repository follows the FPM-A (Fractal Project Method - Algorithmic Edition). See docs/spec.md.
"""

SPEC_TEXT = r"""# FPM-A: Formal methodology for a fractal algorithmic system

## 1. Terms

Fractal Unit (FU) - minimal autonomous unit with the same internal structure:
src/, tests/, api/, docs/, config/, ci/, benchmarks/.
Bounded Context (BC) - domain boundary containing one or more FUs.
Core / Ports / Adapters - domain core; abstract ports; technical adapters (DB/HTTP/CLI/UI).
Contract - formal interface (OpenAPI 3.1 or gRPC) validated by contract tests.

## 2. Architecture invariants

I1. Self-similarity: each FU contains mandatory subdirectories:
{src,tests,api,docs,config,ci,benchmarks}.
I2. Import boundary: adapters must not import core across BC; forbids access to
private paths of other FU except via ports/api.
I3. Acyclic graph: dependency graph between FUs is a DAG.
I4. Contracts: changes follow SemVer; backward compatibility is verified via contract tests.
I5. Configs: managed by environment variables; .env.example provided per FU.
I6. Testing: unit tests are mandatory; contract/integration tests when applicable.
I7. Performance: FUs with NFRs provide benchmarks; >10% regression blocks merge.
I8. Clean deps: only declared dependencies; no hidden imports.
I9. ADRs: architecture decisions affecting invariants must be recorded.

## 3. Algorithmic checks

3.1 Dependency graph:
Nodes: FU (domains/*, libs/*). Edges: import from one FU to another.
Parsers: heuristics for Python (import/from) and Node/TS (import/require).
Checks: cycle detection; forbidden imports (I2).

3.2 Complexity:
CYC = 1 + (#if + #for + #while + #case + #catch + #and/or + #ternary).
Default threshold: 10 per function (configurable).

3.3 Contracts:
OpenAPI 3.1 (api/openapi.yaml) schema validation. CDC if applicable.

## 4. Change protocol

Conventional Commits -> SemVer. Pipeline: check
(invariants+complexity+graph) -> test -> bench -> release.

## 5. Operational model

Configs via env; document defaults in config/README.md and .env.example.
Logging/tracing: unified fields (trace_id, span_id, correlation_id).

## 6. Formal definitions

FU = (S,T,A,D,C,CI,B) where S=src, T=tests, A=api, D=docs, C=config, CI=ci, B=benchmarks.
Graph G=(V,E) where V are FUs; E contains (u,v) if code in u imports v. Require DAG (no cycles).
Import invariant: adapter code must not import other FU's core directly.

## 7. CI artifacts

tools/dep_graph.dot - dependency graph (GraphViz DOT).
report/complexity.json - complexity metrics.
report/invariants.json - invariant violations.
"""

CI_REUSABLE = r"""name: fu-ci
on:
  workflow_call:
    inputs:
      path:
        required: true
        type: string
jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Python
        uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Install fpma (local)
        run: pip install . || true
      - name: Graph check
        run: python -m fpma graph --path . --out-dot tools/dep_graph.dot
      - name: Invariants & Complexity
        run: python -m fpma check --path . --fail-on any
"""

DEPGRAPH_GATE = r"""name: depgraph-gate
on: [push, pull_request]
jobs:
  depgraph:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Graph & invariants
        run: |
          python -m pip install . || true
          python -m fpma graph --path . --out-dot tools/dep_graph.dot
          python -m fpma check --path . --fail-on cycles
      - name: Upload dot
        uses: actions/upload-artifact@v4
        with:
          name: dep-graph
          path: tools/dep_graph.dot
"""

COMPLEXITY_GATE = r"""name: complexity-gate
on: [push, pull_request]
jobs:
  complexity:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Complexity
        run: |
          python -m pip install . || true
          python -m fpma check --path . --fail-on complexity --max-cyc 10 --json | tee report.json
      - name: Upload report
        uses: actions/upload-artifact@v4
        with:
          name: complexity
          path: report.json
"""

PERF_GATE = r"""name: perf-gate
on: [workflow_dispatch]
jobs:
  perf:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - name: Benchmarks (custom)
        run: |
          echo "Run your benchmarks under each FU/benchmarks"
          exit 0
"""

DEP_AUDIT = r"""#!/usr/bin/env python3
import sys, json

def find_cycles(adj):
    visited, stack = set(), []
    in_stack = set()
    cycles = []
    def dfs(u):
        visited.add(u); stack.append(u); in_stack.add(u)
        for v in adj.get(u, []):
            if v not in visited:
                dfs(v)
            elif v in in_stack:
                if v in stack:
                    i = stack.index(v)
                    cyc = stack[i:] + [v]
                    if cyc not in cycles:
                        cycles.append(cyc)
        stack.pop(); in_stack.remove(u)
    for n in adj:
        if n not in visited:
            dfs(n)
    return cycles

def main():
    data = sys.stdin.read().strip()
    try:
        adj = json.loads(data)
    except Exception:
        print("Expecting JSON adjacency", file=sys.stderr); return 1
    cycles = find_cycles(adj)
    if cycles:
        print("CYCLES:")
        for c in cycles:
            print(" -> ".join(c))
        return 2
    print("NO CYCLES")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"""

GRAPHVIZ_SH = r"""#!/usr/bin/env bash
set -euo pipefail
if [ ! -f tools/dep_graph.dot ]; then
  echo "tools/dep_graph.dot not found. Run: python -m fpma graph --path ."
  exit 1
fi
dot -Tpng tools/dep_graph.dot -o tools/dep_graph.png
echo "Wrote tools/dep_graph.png"
"""


def init_repo(name: str, license_id="MIT", include_ci=True, include_bazel=True):
    root = Path(name)
    root.mkdir(parents=True, exist_ok=True)

    (root / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    (root / "adr").mkdir(parents=True, exist_ok=True)
    (root / "domains").mkdir(parents=True, exist_ok=True)
    (root / "libs").mkdir(parents=True, exist_ok=True)
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "tools").mkdir(parents=True, exist_ok=True)

    (root / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    (root / "README.md").write_text(ROOT_README.format(name=name), encoding="utf-8")
    (root / "LICENSE").write_text(
        LICENSES.get(license_id, LICENSES["MIT"]), encoding="utf-8"
    )
    (root / "docs" / "spec.md").write_text(SPEC_TEXT, encoding="utf-8")

    if include_ci:
        (root / ".github" / "workflows" / "ci-reusable.yml").write_text(
            CI_REUSABLE, encoding="utf-8"
        )
        (root / ".github" / "workflows" / "depgraph-gate.yml").write_text(
            DEPGRAPH_GATE, encoding="utf-8"
        )
        (root / ".github" / "workflows" / "complexity-gate.yml").write_text(
            COMPLEXITY_GATE, encoding="utf-8"
        )
        (root / ".github" / "workflows" / "perf-gate.yml").write_text(
            PERF_GATE, encoding="utf-8"
        )

    if include_bazel:
        (root / "WORKSPACE").write_text(
            BAZEL_WORKSPACE.format(name=name.replace("-", "_")), encoding="utf-8"
        )
        (root / "BUILD.bazel").write_text("# root build\n", encoding="utf-8")

    (root / "tools" / "dep_audit.py").write_text(DEP_AUDIT, encoding="utf-8")
    (root / "tools" / "graphviz_export.sh").write_text(GRAPHVIZ_SH, encoding="utf-8")
    (root / "tools" / "graphviz_export.sh").chmod(0o755)

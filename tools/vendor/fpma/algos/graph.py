# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
import re
from pathlib import Path


def discover_fu(root: Path):
    result = []
    for top in ["domains", "libs"]:
        base = root / top
        if base.exists():
            for d in base.iterdir():
                if d.is_dir():
                    result.append((f"{top}/{d.name}", d))
    return result


def build_dep_graph(root: Path):
    fus = discover_fu(root)
    adj = {n: set() for n, _ in fus}

    py_import = re.compile(r"^\s*(?:from\s+([a-zA-Z0-9_\.]+)\s+import|import\s+([a-zA-Z0-9_\.]+))")
    js_import = re.compile(
        r"^\s*(?:import\s+.*?from\s+[\'\"]([^\'\"]+)[\'\"]|require\(\s*[\'\"]([^\'\"]+)[\'\"]\s*\))"
    )

    for name, path in fus:
        for ext in ("py", "js", "ts", "tsx", "jsx"):
            for f in path.rglob(f"*.{ext}"):
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                for line in text.splitlines():
                    if ext == "py":
                        m = py_import.match(line)
                    else:
                        m = js_import.match(line)
                    if not m:
                        continue
                    mod = m.group(1) or m.group(2)
                    if not mod:
                        continue
                    for other, _ in fus:
                        if other == name:
                            continue
                        candidates = [
                            other.replace("/", "."),
                            other.split("/")[1],
                        ]
                        if any(mod.startswith(c) for c in candidates):
                            adj[name].add(other)
    return {k: sorted(v) for k, v in adj.items()}


def export_graphviz(adj):
    lines = ["digraph G {"]
    for u, vs in adj.items():
        if not vs:
            lines.append(f'  "{u}";')
        for v in vs:
            lines.append(f'  "{u}" -> "{v}";')
    lines.append("}")
    return "\n".join(lines)


def find_cycles(adj):
    visited = set()
    stack = set()
    cycles = []

    def dfs(u, path):
        visited.add(u)
        stack.add(u)
        for v in adj.get(u, []):
            if v not in visited:
                dfs(v, path + [v])
            elif v in stack:
                if v in path:
                    i = path.index(v)
                    cyc = path[i:] + [v]
                    if cyc not in cycles:
                        cycles.append(cyc)
        stack.remove(u)

    for n in adj:
        if n not in visited:
            dfs(n, [n])
    return cycles

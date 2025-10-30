# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import ast
import re
import statistics
from pathlib import Path


def cyclomatic_complexity_of_py(fn: Path):
    try:
        tree = ast.parse(fn.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.scores = []

        def visit_FunctionDef(self, node):
            score = 1
            for n in ast.walk(node):
                if isinstance(
                    n,
                    (
                        ast.If,
                        ast.For,
                        ast.While,
                        ast.With,
                        ast.BoolOp,
                        ast.Try,
                        ast.ExceptHandler,
                        ast.Match,
                    ),
                ):
                    score += 1
            self.scores.append(score)
            self.generic_visit(node)

        visit_AsyncFunctionDef = visit_FunctionDef

    v = V()
    v.visit(tree)
    return v.scores


def cyclomatic_complexity_of_js(fn: Path):
    txt = fn.read_text(encoding="utf-8", errors="ignore")
    # naive split: count keywords in file, assign to one synthetic function
    s = 1
    s += len(re.findall(r"\bif\b|\bfor\b|\bwhile\b|\bcase\b|\bcatch\b|\?", txt))
    return [s] if s > 1 else []


def scan_complexity(root: Path):
    scores = []
    for fn in root.rglob("*.py"):
        scores.extend(cyclomatic_complexity_of_py(fn))
    for fn in root.rglob("*.js"):
        scores.extend(cyclomatic_complexity_of_js(fn))
    if not scores:
        return {"functions_scanned": 0, "max": 0, "avg": 0.0}
    return {
        "functions_scanned": len(scores),
        "max": max(scores),
        "avg": statistics.mean(scores),
    }

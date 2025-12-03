"""Low-level analyzers used by the code health aggregator."""

from __future__ import annotations

import ast
import json
import statistics
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    MutableMapping,
    Optional,
    Set,
    Tuple,
)

import networkx as nx

from .models import DeveloperMetrics, RiskProfile

_AST_COMPLEXITY_NODES = (
    ast.If,
    ast.For,
    ast.While,
    ast.Try,
    ast.With,
    ast.BoolOp,
    ast.IfExp,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.ExceptHandler,
)


@dataclass(slots=True)
class ParsedFunction:
    """Intermediate representation for AST traversal."""

    name: str
    qualname: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    start_line: int
    end_line: int
    cyclomatic_complexity: int
    calls: Set[str]


class PythonFileAnalyzer:
    """Parse Python modules and extract structural metrics."""

    def __init__(self, path: Path):
        self.path = path
        self._tree: Optional[ast.AST] = None

    def parse(self) -> ast.AST:
        if self._tree is None:
            source = self.path.read_text(encoding="utf-8")
            self._tree = ast.parse(source, filename=str(self.path))
        return self._tree

    def iter_functions(self) -> Iterator[ParsedFunction]:
        tree = self.parse()
        module_name = self.path.stem

        def traverse(node: ast.AST, stack: List[str]) -> Iterator[ParsedFunction]:
            # Update stack context before visiting children so nested classes/functions
            # inherit the appropriate qualified name prefix.
            if isinstance(node, ast.ClassDef):
                stack = [*stack, node.name]
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualname = ".".join([module_name, *stack, node.name])
                complexity = self._compute_cyclomatic_complexity(node)
                start_line = getattr(node, "lineno", 0)
                end_line = self._infer_end_line(node)
                calls = self._collect_calls(node)
                yield ParsedFunction(
                    name=node.name,
                    qualname=qualname,
                    node=node,
                    start_line=start_line,
                    end_line=end_line,
                    cyclomatic_complexity=complexity,
                    calls=calls,
                )
                stack = [*stack, node.name]

            for child in ast.iter_child_nodes(node):
                yield from traverse(child, stack)

        yield from traverse(tree, [])

    def _compute_cyclomatic_complexity(self, node: ast.AST) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, _AST_COMPLEXITY_NODES):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += max(len(child.values) - 1, 0)
        return complexity

    def _infer_end_line(self, node: ast.AST) -> int:
        end_line = getattr(node, "end_lineno", None)
        if end_line is not None:
            return end_line
        # Fallback: walk the body to find the maximum line number.
        max_line = getattr(node, "lineno", 0)
        for child in ast.walk(node):
            max_line = max(max_line, getattr(child, "lineno", max_line))
        return max_line

    def _collect_calls(self, node: ast.AST) -> Set[str]:
        calls: Set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Attribute):
                    calls.add(child.func.attr)
                elif isinstance(child.func, ast.Name):
                    calls.add(child.func.id)
        return calls


class CallGraphAnalyzer:
    """Compute fan-in and fan-out based on AST-derived call graphs."""

    def __init__(self) -> None:
        self.graph = nx.DiGraph()
        self.known_functions: Dict[str, str] = {}

    def ingest(self, functions: Iterable[ParsedFunction]) -> None:
        local_functions = list(functions)
        for fn in local_functions:
            self.graph.add_node(fn.qualname, file=fn)
            self.known_functions.setdefault(fn.name, fn.qualname)
            simple_name = fn.name.split(".")[-1]
            self.known_functions.setdefault(simple_name, fn.qualname)
        for fn in local_functions:
            for callee in fn.calls:
                target = self.known_functions.get(callee, callee)
                self.graph.add_edge(fn.qualname, target)

    def fan_in(self, qualname: str) -> int:
        if not self.graph.has_node(qualname):
            return 0
        return int(self.graph.in_degree(qualname))

    def fan_out(self, qualname: str) -> int:
        if not self.graph.has_node(qualname):
            return 0
        return int(self.graph.out_degree(qualname))


class CouplingAnalyzer:
    """Approximate coupling by counting unique imports from other modules."""

    def __init__(self, path: Path):
        self.path = path

    def measure(self) -> int:
        tree = ast.parse(self.path.read_text(encoding="utf-8"), filename=str(self.path))
        imports: Set[str] = set()
        module_base = self.path.stem
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module.split(".")[0])
        # Coupling excludes self references.
        imports.discard(module_base)
        return len(imports)


class GitHistoryAnalyzer:
    """Interact with git history to capture churn and activity metrics."""

    def __init__(self, repo_path: Path):
        self.repo_path = repo_path
        self._change_cache: Dict[int, Dict[str, Dict[str, int]]] = {}
        self._interface_cache: Dict[int, Dict[str, Tuple[int, int]]] = {}

    def _run(self, *args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            check=check,
        )

    def file_change_frequency(self, file_path: Path, days: int = 180) -> int:
        change_data = self._ensure_change_cache(days)
        return change_data.get(self._relative(file_path), {}).get("frequency", 0)

    def file_churn(self, file_path: Path, days: int = 180) -> int:
        change_data = self._ensure_change_cache(days)
        return change_data.get(self._relative(file_path), {}).get("churn", 0)

    def interface_instability(self, file_path: Path, days: int = 365) -> float:
        interface_data = self._ensure_interface_cache(days)
        totals = interface_data.get(self._relative(file_path))
        if not totals:
            return 1.0
        interface_changes, total_changes = totals
        if total_changes == 0:
            return 1.0
        stability = 1.0 - (interface_changes / total_changes)
        return max(0.0, min(1.0, stability))

    def hot_files(self, limit: int = 10, days: int = 90) -> List[Tuple[str, int]]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = self._run("log", "--since", since, "--name-only", "--pretty=format:")
        counter: Counter[str] = Counter()
        for line in result.stdout.splitlines():
            path = line.strip()
            if not path:
                continue
            counter[path] += 1
        return counter.most_common(limit)

    def developer_activity(self, days: int = 90) -> List[DeveloperMetrics]:
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = self._run("log", "--since", since, "--numstat", "--pretty=%an")
        author: Optional[str] = None
        churn: Counter[str] = Counter()
        files: MutableMapping[str, Set[str]] = defaultdict(set)
        file_counts: MutableMapping[str, Counter[str]] = defaultdict(Counter)
        commits: Counter[str] = Counter()
        for line in result.stdout.splitlines():
            if not line:
                continue
            if not line[0].isdigit():
                author = line.strip()
                if author:
                    commits[author] += 1
                continue
            if author is None:
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            added, removed, path = parts
            if added.isdigit():
                churn[author] += int(added)
            if removed.isdigit():
                churn[author] += int(removed)
            files[author].add(path)
            file_counts[author][path] += 1
        metrics: List[DeveloperMetrics] = []
        for author_name, commit_count in commits.items():
            hotspots = [path for path, _ in file_counts[author_name].most_common(5)]
            metrics.append(
                DeveloperMetrics(
                    author=author_name,
                    commits=commit_count,
                    files_touched=len(files[author_name]),
                    churn=churn[author_name],
                    hotspots=hotspots,
                )
            )
        return sorted(metrics, key=lambda m: m.churn, reverse=True)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_change_cache(self, days: int) -> Dict[str, Dict[str, int]]:
        if days in self._change_cache:
            return self._change_cache[days]
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = self._run("log", "--since", since, "--numstat", "--pretty=%H")
        data: Dict[str, Dict[str, int]] = defaultdict(
            lambda: {"frequency": 0, "churn": 0}
        )
        seen_in_commit: Set[str] = set()
        for line in result.stdout.splitlines():
            if not line:
                continue
            if len(line) == 40 and all(c in "0123456789abcdef" for c in line.lower()):
                seen_in_commit.clear()
                continue
            parts = line.split()
            if len(parts) != 3:
                continue
            added, removed, path = parts
            if path == "-":
                continue
            entry = data[path]
            if added.isdigit():
                entry["churn"] += int(added)
            if removed.isdigit():
                entry["churn"] += int(removed)
            if path not in seen_in_commit:
                entry["frequency"] += 1
                seen_in_commit.add(path)
        self._change_cache[days] = data
        return data

    def _ensure_interface_cache(self, days: int) -> Dict[str, Tuple[int, int]]:
        if days in self._interface_cache:
            return self._interface_cache[days]
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        result = self._run(
            "log",
            "--since",
            since,
            "--max-count",
            "400",
            "-p",
            "--pretty=%H",
        )
        interface_changes: Counter[str] = Counter()
        total_changes: Counter[str] = Counter()
        current_file: Optional[str] = None
        for line in result.stdout.splitlines():
            if line.startswith("diff --git"):
                parts = line.split()
                if len(parts) >= 4:
                    current_file = parts[3][2:]
                continue
            if line.startswith("+++ b/"):
                current_file = line[6:]
                continue
            if not current_file or current_file == "/dev/null":
                continue
            if line.startswith("Binary files"):
                continue
            if line.startswith(("+++", "---")):
                continue
            if line.startswith(("+", "-")):
                total_changes[current_file] += 1
                stripped = line[1:].strip()
                if stripped.startswith("def ") or stripped.startswith("class "):
                    interface_changes[current_file] += 1
        data = {
            path: (interface_changes[path], total_changes[path])
            for path in total_changes
        }
        self._interface_cache[days] = data
        return data

    def _relative(self, file_path: Path) -> str:
        try:
            return str(file_path.relative_to(self.repo_path))
        except ValueError:
            return str(file_path)


class RiskHeuristics:
    """Combine structural and historical signals into a risk profile."""

    def __init__(self, thresholds: Mapping[str, float]):
        self.thresholds = thresholds

    def evaluate(
        self,
        *,
        avg_complexity: float,
        max_complexity: int,
        fan_in: int,
        fan_out: int,
        churn: int,
        change_frequency: int,
        interface_stability: float,
    ) -> RiskProfile:
        contributions: List[str] = []
        score_components: List[float] = []

        if avg_complexity > self.thresholds.get("complexity", 10):
            contributions.append("High average cyclomatic complexity")
            score_components.append(
                avg_complexity / (self.thresholds.get("complexity", 10) * 2)
            )
        if max_complexity > self.thresholds.get("max_complexity", 15):
            contributions.append("Elevated worst-case complexity")
            score_components.append(
                max_complexity / (self.thresholds.get("max_complexity", 15) * 2)
            )
        if fan_in > self.thresholds.get("fan_in", 10):
            contributions.append("High fan-in indicates coupling")
            score_components.append(fan_in / (self.thresholds.get("fan_in", 10) * 2))
        if fan_out > self.thresholds.get("fan_out", 10):
            contributions.append("High fan-out indicates broad dependencies")
            score_components.append(fan_out / (self.thresholds.get("fan_out", 10) * 2))
        if churn > self.thresholds.get("churn", 50):
            contributions.append("Significant churn in recent history")
            score_components.append(churn / (self.thresholds.get("churn", 50) * 3))
        if change_frequency > self.thresholds.get("change_frequency", 10):
            contributions.append("Frequent modifications make this area unstable")
            score_components.append(
                change_frequency / (self.thresholds.get("change_frequency", 10) * 3)
            )
        if interface_stability < self.thresholds.get("interface_stability", 0.8):
            contributions.append("Public interface changes too frequently")
            score_components.append((1 - interface_stability) * 1.5)

        risk_score = max(0.0, min(1.0, sum(score_components)))
        recommendations = self._make_recommendations(contributions, interface_stability)
        return RiskProfile(
            risk_score=risk_score,
            contributing_factors=contributions,
            recommendations=recommendations,
        )

    def _make_recommendations(
        self, factors: Iterable[str], interface_stability: float
    ) -> List[str]:
        recommendations: List[str] = []
        factor_set = set(factors)
        if (
            "High average cyclomatic complexity" in factor_set
            or "Elevated worst-case complexity" in factor_set
        ):
            recommendations.append(
                "Break large functions into smaller units and add focused tests."
            )
        if "High fan-in indicates coupling" in factor_set:
            recommendations.append(
                "Isolate responsibilities via facades or domain services."
            )
        if "High fan-out indicates broad dependencies" in factor_set:
            recommendations.append(
                "Introduce abstractions to reduce direct dependency breadth."
            )
        if "Significant churn in recent history" in factor_set:
            recommendations.append(
                "Pair refactoring with regression tests to stabilise behavior."
            )
        if "Frequent modifications make this area unstable" in factor_set:
            recommendations.append(
                "Schedule dedicated hardening sprint for this module."
            )
        if interface_stability < 0.5:
            recommendations.append(
                "Document contract changes and version interfaces to restore trust."
            )
        return recommendations


def load_previous_snapshot(history_file: Path) -> Optional[Dict[str, Dict[str, float]]]:
    if not history_file.exists():
        return None
    try:
        return json.loads(history_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def save_snapshot(history_file: Path, snapshot: Mapping[str, Dict[str, float]]) -> None:
    history_file.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, default=str), encoding="utf-8"
    )


def compute_trends(
    *,
    previous: Optional[Mapping[str, Dict[str, float]]],
    current: Mapping[str, Dict[str, float]],
) -> List[Tuple[str, float, float]]:
    trends: List[Tuple[str, float, float]] = []
    if previous is None:
        return trends
    for key, values in current.items():
        prev_value = previous.get(key, {}).get("avg_cyclomatic_complexity")
        current_value = values.get("avg_cyclomatic_complexity")
        if prev_value is None or current_value is None:
            continue
        trends.append((key, prev_value, current_value))
    return trends


def rolling_average(values: Iterable[float]) -> float:
    seq = list(values)
    return statistics.mean(seq) if seq else 0.0

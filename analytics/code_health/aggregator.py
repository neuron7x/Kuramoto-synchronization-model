"""High-level orchestration for code health metrics collection."""

from __future__ import annotations

import csv
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from fastapi import FastAPI

from . import widgets
from .analyzers import (
    CallGraphAnalyzer,
    CouplingAnalyzer,
    GitHistoryAnalyzer,
    ParsedFunction,
    PythonFileAnalyzer,
    RiskHeuristics,
    compute_trends,
    load_previous_snapshot,
    rolling_average,
    save_snapshot,
)
from .models import (
    FileMetrics,
    FunctionMetrics,
    RepositoryMetrics,
    Thresholds,
    TrendInsight,
)


class CodeMetricAggregator:
    """Collect structural and historical metrics for the repository."""

    def __init__(
        self,
        repo_root: Path | str = Path.cwd(),
        *,
        file_globs: Sequence[str] = ("**/*.py",),
        history_file: Path | str | None = None,
        thresholds: Optional[Thresholds] = None,
    ) -> None:
        self.repo_root = Path(repo_root)
        self.file_globs = file_globs
        self.thresholds = thresholds or Thresholds()
        self.history_file = (
            Path(history_file)
            if history_file
            else self.repo_root / ".code_metrics_history.json"
        )
        self.git = GitHistoryAnalyzer(self.repo_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def collect(self) -> RepositoryMetrics:
        """Collect repository metrics and persist history for trend analysis."""

        python_files = self._discover_files()
        parsed_functions: Dict[str, List[ParsedFunction]] = {}
        call_graph = CallGraphAnalyzer()

        for path in python_files:
            analyzer = PythonFileAnalyzer(path)
            functions = list(analyzer.iter_functions())
            relative_path = str(path.relative_to(self.repo_root))
            parsed_functions[relative_path] = functions
            call_graph.ingest(functions)

        file_metrics: Dict[str, FileMetrics] = {}
        snapshot: Dict[str, Dict[str, float]] = {}
        risk_calculator = RiskHeuristics(
            {
                "complexity": self.thresholds.max_cyclomatic_complexity,
                "max_complexity": self.thresholds.max_cyclomatic_complexity * 1.5,
                "fan_in": 12,
                "fan_out": 12,
                "churn": self.thresholds.max_hotspot_churn,
                "change_frequency": 12,
                "interface_stability": self.thresholds.min_interface_stability,
            }
        )

        for path_str, functions in parsed_functions.items():
            path = self.repo_root / path_str
            if not path.exists():
                continue
            total_lines = self._safe_line_count(path)
            coupling = CouplingAnalyzer(path).measure()
            fan_in = rolling_average(call_graph.fan_in(fn.qualname) for fn in functions)
            fan_out = rolling_average(
                call_graph.fan_out(fn.qualname) for fn in functions
            )
            change_freq = self.git.file_change_frequency(path)
            churn = self.git.file_churn(path)
            stability = self.git.interface_instability(path)
            function_metrics = self._build_function_metrics(
                functions, call_graph, path_str
            )

            avg_complexity = rolling_average(
                fn.cyclomatic_complexity for fn in functions
            )
            max_complexity = max(
                (fn.cyclomatic_complexity for fn in functions), default=0
            )
            hot_score = churn * 0.6 + change_freq * 0.4
            risk_profile = risk_calculator.evaluate(
                avg_complexity=avg_complexity,
                max_complexity=max_complexity,
                fan_in=int(round(fan_in)),
                fan_out=int(round(fan_out)),
                churn=churn,
                change_frequency=change_freq,
                interface_stability=stability,
            )

            metrics = FileMetrics(
                path=path_str,
                total_lines=total_lines,
                avg_cyclomatic_complexity=avg_complexity,
                max_cyclomatic_complexity=max_complexity,
                functions=function_metrics,
                coupling=coupling,
                fan_in=int(round(fan_in)),
                fan_out=int(round(fan_out)),
                change_frequency=change_freq,
                interface_stability=stability,
                churn=churn,
                hot_spot_score=hot_score,
                risk_profile=risk_profile,
            )
            file_metrics[path_str] = metrics
            snapshot[path_str] = {
                "avg_cyclomatic_complexity": avg_complexity,
                "max_cyclomatic_complexity": float(max_complexity),
                "hot_spot_score": hot_score,
                "risk_score": risk_profile.risk_score,
            }

        previous_snapshot = load_previous_snapshot(self.history_file)
        save_snapshot(self.history_file, snapshot)

        trends = [
            TrendInsight(
                metric=path,
                previous=prev,
                current=curr,
                delta=curr - prev,
                direction="up" if curr > prev else ("down" if curr < prev else "flat"),
                timestamp=datetime.now(timezone.utc),
            )
            for path, prev, curr in compute_trends(
                previous=previous_snapshot, current=snapshot
            )
        ]

        developer_metrics = self.git.developer_activity()
        hotspots = self._identify_hotspots(file_metrics)

        repo_metrics = RepositoryMetrics(
            generated_at=datetime.now(timezone.utc),
            files=file_metrics,
            thresholds=self.thresholds,
            risk_hotspots=hotspots,
            trends=trends,
            developer_metrics=developer_metrics,
        )
        return repo_metrics

    def export_csv(self, metrics: RepositoryMetrics, output_path: Path | str) -> None:
        """Export file-level metrics to CSV for offline processing."""

        fieldnames = [
            "path",
            "total_lines",
            "avg_cyclomatic_complexity",
            "max_cyclomatic_complexity",
            "coupling",
            "fan_in",
            "fan_out",
            "change_frequency",
            "interface_stability",
            "churn",
            "hot_spot_score",
            "risk_score",
        ]
        with Path(output_path).open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for file_metric in metrics.iter_files():
                writer.writerow(
                    {
                        "path": file_metric.path,
                        "total_lines": file_metric.total_lines,
                        "avg_cyclomatic_complexity": f"{file_metric.avg_cyclomatic_complexity:.2f}",
                        "max_cyclomatic_complexity": file_metric.max_cyclomatic_complexity,
                        "coupling": file_metric.coupling,
                        "fan_in": file_metric.fan_in,
                        "fan_out": file_metric.fan_out,
                        "change_frequency": file_metric.change_frequency,
                        "interface_stability": f"{file_metric.interface_stability:.2f}",
                        "churn": file_metric.churn,
                        "hot_spot_score": f"{file_metric.hot_spot_score:.2f}",
                        "risk_score": f"{file_metric.risk_profile.risk_score:.2f}",
                    }
                )

    def build_pr_report(
        self, metrics: RepositoryMetrics, *, base_ref: str = "origin/main"
    ) -> str:
        """Generate a PR-friendly summary scoped to the current branch."""

        changed_files = self._changed_files(base_ref)
        if not changed_files:
            return "No code changes detected against the baseline."

        lines: List[str] = ["### Code Health Summary", ""]
        for file in changed_files:
            file_metrics = metrics.files.get(file)
            if not file_metrics:
                continue
            lines.append(f"**{file}**")
            factors = (
                ", ".join(file_metrics.risk_profile.contributing_factors) or "stable"
            )
            lines.append(
                f"- Risk score: {file_metrics.risk_profile.risk_score:.2f} ({factors})"
            )
            violations = file_metrics.exceeding_thresholds(metrics.thresholds)
            if violations:
                lines.append("- Threshold alerts:")
                for key, value in violations.items():
                    lines.append(f"  - {key}: {value}")
            if file_metrics.risk_profile.recommendations:
                lines.append("- Refactoring guidance:")
                for tip in file_metrics.risk_profile.recommendations:
                    lines.append(f"  - {tip}")
            lines.append("")
        return "\n".join(lines).strip()

    def build_dashboard_payload(self, metrics: RepositoryMetrics) -> Dict[str, object]:
        """Prepare structured data for developer dashboards or BI tools."""

        return {
            "generated_at": metrics.generated_at.isoformat(),
            "risk_hotspots": [
                self._serialize_file_metric(fm) for fm in metrics.most_risky()
            ],
            "hot_files": self.git.hot_files(),
            "developers": [asdict(dm) for dm in metrics.developer_metrics],
            "trends": [
                {
                    "metric": trend.metric,
                    "previous": trend.previous,
                    "current": trend.current,
                    "delta": trend.delta,
                    "direction": trend.direction,
                    "timestamp": trend.timestamp.isoformat(),
                }
                for trend in metrics.trends
            ],
        }

    def create_api(self, metrics: RepositoryMetrics) -> FastAPI:
        """Expose metrics via a FastAPI application."""

        app = FastAPI(title="TradePulse Code Metrics", version="1.0.0")

        @app.get("/metrics/files")
        def list_files() -> (
            List[Dict[str, object]]
        ):  # pragma: no cover - FastAPI wiring
            return [self._serialize_file_metric(fm) for fm in metrics.iter_files()]

        @app.get("/metrics/files/{path:path}")
        def file_detail(
            path: str,
        ) -> Dict[str, object]:  # pragma: no cover - FastAPI wiring
            metric = metrics.files.get(path)
            if metric is None:
                return {"error": "File not found"}
            return self._serialize_file_metric(metric)

        @app.get("/metrics/developers")
        def developer_overview() -> (
            List[Dict[str, object]]
        ):  # pragma: no cover - FastAPI wiring
            return [asdict(dm) for dm in metrics.developer_metrics]

        @app.get("/metrics/hot-files")
        def hot_files() -> List[Tuple[str, int]]:  # pragma: no cover - FastAPI wiring
            return self.git.hot_files()

        @app.get("/metrics/trends")
        def trend_overview() -> (
            List[Dict[str, object]]
        ):  # pragma: no cover - FastAPI wiring
            return [
                {
                    "metric": trend.metric,
                    "previous": trend.previous,
                    "current": trend.current,
                    "delta": trend.delta,
                    "direction": trend.direction,
                    "timestamp": trend.timestamp.isoformat(),
                }
                for trend in metrics.trends
            ]

        return app

    def render_widget(self, metrics: RepositoryMetrics, *, theme: str = "light") -> str:
        """Render an embeddable HTML widget summarising key metrics."""

        context = {
            "generated_at": metrics.generated_at,
            "hotspots": metrics.most_risky(5),
            "theme": theme,
        }
        return widgets.render_widget(context)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _discover_files(self) -> List[Path]:
        files: Set[Path] = set()
        for pattern in self.file_globs:
            files.update(self.repo_root.glob(pattern))
        return [path for path in files if path.is_file() and "venv" not in path.parts]

    def _safe_line_count(self, path: Path) -> int:
        try:
            return sum(1 for _ in path.open(encoding="utf-8"))
        except UnicodeDecodeError:
            return 0

    def _build_function_metrics(
        self,
        functions: Iterable[ParsedFunction],
        call_graph: CallGraphAnalyzer,
        file_path: str,
    ) -> List[FunctionMetrics]:
        result: List[FunctionMetrics] = []
        for fn in functions:
            result.append(
                FunctionMetrics(
                    name=fn.name,
                    file_path=file_path,
                    start_line=fn.start_line,
                    end_line=fn.end_line,
                    cyclomatic_complexity=fn.cyclomatic_complexity,
                    length=fn.end_line - fn.start_line + 1,
                    fan_in=call_graph.fan_in(fn.qualname),
                    fan_out=call_graph.fan_out(fn.qualname),
                )
            )
        return result

    def _identify_hotspots(
        self, file_metrics: Mapping[str, FileMetrics]
    ) -> List[FileMetrics]:
        candidates = [
            fm
            for fm in file_metrics.values()
            if fm.hot_spot_score > self.thresholds.max_hotspot_churn
        ]
        return sorted(
            candidates, key=lambda fm: fm.risk_profile.risk_score, reverse=True
        )

    def _serialize_file_metric(self, metric: FileMetrics) -> Dict[str, object]:
        return {
            "path": metric.path,
            "total_lines": metric.total_lines,
            "avg_cyclomatic_complexity": metric.avg_cyclomatic_complexity,
            "max_cyclomatic_complexity": metric.max_cyclomatic_complexity,
            "coupling": metric.coupling,
            "fan_in": metric.fan_in,
            "fan_out": metric.fan_out,
            "change_frequency": metric.change_frequency,
            "interface_stability": metric.interface_stability,
            "churn": metric.churn,
            "hot_spot_score": metric.hot_spot_score,
            "risk_profile": {
                "score": metric.risk_profile.risk_score,
                "factors": metric.risk_profile.contributing_factors,
                "recommendations": metric.risk_profile.recommendations,
            },
            "functions": [
                {
                    "name": fn.name,
                    "start_line": fn.start_line,
                    "end_line": fn.end_line,
                    "complexity": fn.cyclomatic_complexity,
                    "length": fn.length,
                    "fan_in": fn.fan_in,
                    "fan_out": fn.fan_out,
                }
                for fn in metric.functions
            ],
        }

    def _changed_files(self, base_ref: str) -> List[str]:
        result = self.git._run("diff", "--name-only", base_ref)
        if result.returncode != 0:
            return []
        return [
            line.strip()
            for line in result.stdout.splitlines()
            if line.strip().endswith(".py")
        ]

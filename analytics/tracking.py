# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Experiment tracking utilities providing reproducibility and reporting."""
from __future__ import annotations

import hashlib
import json
import logging
import shutil
import textwrap
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from omegaconf import DictConfig, OmegaConf

from analytics._config_sanitizer import redacted_config_yaml
from core.config.cli_models import ExperimentConfig, ExperimentTrackingConfig

try:  # pragma: no cover - optional rich formatting
    import markdown  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - markdown is optional
    markdown = None


if markdown is None:  # pragma: no cover - fallback for environments without markdown

    def _markdown_to_html(source: str) -> str:
        return "<pre>" + source.replace("<", "&lt;").replace(">", "&gt;") + "</pre>"

else:  # pragma: no cover - executed when markdown package is available

    def _markdown_to_html(source: str) -> str:
        return markdown.markdown(source, extensions=["tables", "fenced_code"])


@dataclass(slots=True)
class BaselineDeviation:
    """Represents a deviation from the registered baseline metrics."""

    metric: str
    baseline: float
    observed: float
    delta: float
    threshold: float


class ExperimentDeviationError(RuntimeError):
    """Raised when experiment metrics deviate from the baseline beyond tolerance."""

    def __init__(self, message: str, deviations: Iterable[BaselineDeviation]):
        super().__init__(message)
        self.deviations = list(deviations)


class NullExperimentTracker:
    """No-op tracker used when experiment tracking is disabled."""

    def log_configuration(
        self, cfg: DictConfig, safe_yaml: str | None
    ) -> None:  # noqa: D401
        return

    def log_data_version(self, data_path: Path) -> None:  # noqa: D401
        return

    def log_metrics(self, metrics: Mapping[str, Any]) -> None:  # noqa: D401
        return

    def record_status(
        self, status: str, payload: Mapping[str, Any] | None = None
    ) -> None:  # noqa: D401
        return

    def log_artifact(self, path: Path, alias: str | None = None) -> None:  # noqa: D401
        return

    def log_metadata(self, metadata: Any) -> None:  # noqa: D401
        return

    def finalize(
        self, results: Mapping[str, Any] | None, error: BaseException | None
    ) -> None:  # noqa: D401
        return


class ExperimentTracker:
    """Stateful helper that captures experiment artifacts and diagnostics."""

    def __init__(
        self,
        experiment: ExperimentConfig,
        metadata: Any,
    ) -> None:
        self._experiment = experiment
        self._tracking: ExperimentTrackingConfig = experiment.tracking
        self._metadata = metadata
        self._logger = logging.getLogger("tradepulse.tracking")

        run_dir = Path(metadata.run_dir)
        base_dir = Path(self._tracking.base_dir)
        if not base_dir.is_absolute():
            base_dir = run_dir / base_dir
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

        self._artifacts_dir = self._base_dir / self._tracking.artifacts_dirname
        self._artifacts_dir.mkdir(parents=True, exist_ok=True)

        self._reports_dir = self._base_dir / self._tracking.reports_dirname
        self._reports_dir.mkdir(parents=True, exist_ok=True)

        archive_dir = self._tracking.archive.directory
        if archive_dir is None:
            archive_dir = self._base_dir / "archives"
        else:
            archive_dir = Path(archive_dir)
            if not archive_dir.is_absolute():
                archive_dir = self._base_dir / archive_dir
        self._archive_dir = archive_dir
        if self._tracking.archive.enabled:
            self._archive_dir.mkdir(parents=True, exist_ok=True)

        self._status_log: list[dict[str, Any]] = []
        self._metrics: Mapping[str, Any] | None = None
        self._data_version: Mapping[str, Any] | None = None
        self._deviations: list[BaselineDeviation] = []
        self._alerts_written = False

    @classmethod
    def from_experiment(
        cls,
        experiment: ExperimentConfig,
        metadata: Any,
    ) -> ExperimentTracker | NullExperimentTracker:
        if not experiment.tracking.enabled:
            return NullExperimentTracker()
        return cls(experiment=experiment, metadata=metadata)

    def log_configuration(self, cfg: DictConfig, safe_yaml: str | None) -> None:
        """Persist sanitized configuration and hyperparameters."""

        if not self._tracking.auto_log_config:
            return

        redacted_yaml = safe_yaml
        if redacted_yaml is None:
            try:
                redacted_yaml = redacted_config_yaml(cfg)
            except Exception as exc:  # pragma: no cover - defensive path
                self._logger.warning(
                    "Skipping configuration redaction because sanitization failed: %s",
                    exc,
                )

        if redacted_yaml is not None:
            redacted_path = self._artifacts_dir / "config.redacted.yaml"
            redacted_path.write_text(redacted_yaml, encoding="utf-8")

        try:
            resolved = OmegaConf.to_container(cfg.experiment, resolve=True)
        except Exception:  # pragma: no cover - defensive path
            resolved = OmegaConf.to_container(cfg.experiment, resolve=False)
        hyperparameters = resolved.get("analytics", {})
        hp_path = self._artifacts_dir / self._tracking.hyperparameters_filename
        hp_path.write_text(json.dumps(hyperparameters, indent=2), encoding="utf-8")

    def log_metadata(self, metadata: Any) -> None:
        """Capture execution metadata for provenance."""

        if not self._tracking.auto_log_metadata:
            return
        payload = (
            asdict(metadata)
            if hasattr(metadata, "__dataclass_fields__")
            else dict(metadata)
        )
        payload["recorded_at"] = datetime.now(timezone.utc).isoformat()
        path = self._artifacts_dir / "metadata.json"
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    def log_data_version(self, data_path: Path) -> None:
        """Store dataset fingerprint information for reproducibility."""

        if not self._tracking.data_versioning:
            self._data_version = {"path": str(data_path), "versioning": "disabled"}
            return

        record: dict[str, Any] = {
            "path": str(data_path),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "exists": data_path.exists(),
        }
        if data_path.exists():
            hasher = hashlib.sha256()
            with data_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    hasher.update(chunk)
            record["sha256"] = hasher.hexdigest()
            stat = data_path.stat()
            record["size_bytes"] = stat.st_size
        if self._tracking.versioning.backend != "none":
            record["versioning"] = {
                "backend": self._tracking.versioning.backend,
                "repo_path": (
                    str(self._tracking.versioning.repo_path)
                    if self._tracking.versioning.repo_path
                    else None
                ),
                "message": self._tracking.versioning.message,
            }
        self._data_version = record
        path = self._artifacts_dir / "data_version.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    def log_metrics(self, metrics: Mapping[str, Any]) -> None:
        """Persist computed metrics and validate against the baseline."""

        self._metrics = dict(metrics)
        metrics_path = self._artifacts_dir / "metrics.json"
        metrics_path.write_text(json.dumps(self._metrics, indent=2), encoding="utf-8")

        if not self._tracking.alerts.enabled:
            return

        deviations = self._evaluate_baseline()
        if deviations:
            self._write_alerts(deviations)
            if self._tracking.alerts.fail_on_deviation:
                msg = "Experiment metrics deviated from the registered baseline"
                raise ExperimentDeviationError(msg, deviations)

    def _evaluate_baseline(self) -> list[BaselineDeviation]:
        """Compare metrics with the configured baseline and return deviations."""

        baseline_cfg = self._tracking.baseline
        if baseline_cfg is None or self._metrics is None:
            self._deviations = []
            return []

        metrics_path = Path(baseline_cfg.metrics_path)
        if not metrics_path.exists():
            self._logger.warning(
                "Baseline metrics file %s not found; skipping deviation check.",
                metrics_path,
            )
            self._deviations = []
            return []

        baseline_metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        deviations: list[BaselineDeviation] = []
        strategy = self._tracking.alerts.strategy
        default_tolerance = float(self._tracking.alerts.tolerance)

        for metric, baseline_value in baseline_metrics.items():
            if metric not in self._metrics:
                continue
            observed = float(self._metrics[metric])
            baseline_val = float(baseline_value)
            if strategy == "relative" and baseline_val != 0:
                delta = abs((observed - baseline_val) / baseline_val)
            else:
                delta = abs(observed - baseline_val)
            threshold = float(
                baseline_cfg.metric_tolerances.get(metric, default_tolerance)
            )
            if delta > threshold:
                deviations.append(
                    BaselineDeviation(
                        metric=metric,
                        baseline=baseline_val,
                        observed=observed,
                        delta=delta,
                        threshold=threshold,
                    )
                )

        self._deviations = deviations
        return deviations

    def _write_alerts(self, deviations: Iterable[BaselineDeviation]) -> None:
        payload = {
            "triggered": True,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "deviations": [asdict(item) for item in deviations],
        }
        path = self._reports_dir / "alerts.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self._alerts_written = True
        for deviation in deviations:
            self._logger.error(
                "Metric %s deviated beyond threshold %.6f (observed %.6f, baseline %.6f)",
                deviation.metric,
                deviation.threshold,
                deviation.observed,
                deviation.baseline,
            )

    def record_status(
        self, status: str, payload: Mapping[str, Any] | None = None
    ) -> None:
        """Append a structured status entry for CI dashboards."""

        entry = {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if payload is not None:
            entry["payload"] = dict(payload)
        self._status_log.append(entry)

    def log_artifact(self, path: Path, alias: str | None = None) -> None:
        """Persist an artifact in the tracking directory."""

        if not path.exists():
            return

        target_name = alias or path.name
        target = self._artifacts_dir / target_name
        if path.resolve() == target.resolve():
            return

        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(path, target)
        else:
            shutil.copy2(path, target)

    def finalize(
        self,
        results: Mapping[str, Any] | None,
        error: BaseException | None,
    ) -> None:
        """Generate reports, CI summaries, and archives."""

        if self._tracking.reports.auto_generate:
            self._generate_reports(results, error)
        if self._tracking.ci_integration:
            self._write_ci_summary(results, error)
        if self._tracking.archive.enabled:
            self._archive_run_dir()

    def _generate_reports(
        self, results: Mapping[str, Any] | None, error: BaseException | None
    ) -> None:
        """Write Markdown and HTML experiment reports."""

        markdown_report = self._build_markdown_report(results, error)
        report_path = self._reports_dir / self._tracking.reports.markdown_filename
        report_path.write_text(markdown_report, encoding="utf-8")

        dashboard_path = self._reports_dir / self._tracking.reports.dashboard_filename
        dashboard_html = _markdown_to_html(markdown_report)
        dashboard_path.write_text(dashboard_html, encoding="utf-8")

    def _build_markdown_report(
        self, results: Mapping[str, Any] | None, error: BaseException | None
    ) -> str:
        metadata_block = json.dumps(
            (
                asdict(self._metadata)
                if hasattr(self._metadata, "__dataclass_fields__")
                else {}
            ),
            indent=2,
            default=str,
        )
        metrics_block = json.dumps(self._metrics or {}, indent=2, default=str)
        data_version_block = json.dumps(self._data_version or {}, indent=2, default=str)
        deviations_block = json.dumps(
            [asdict(item) for item in self._deviations], indent=2, default=str
        )
        status_block = json.dumps(self._status_log, indent=2, default=str)
        error_block = str(error) if error else "None"

        return textwrap.dedent(
            f"""
            # Experiment Report — {self._experiment.name}

            ## Metadata
            ```json
            {metadata_block}
            ```

            ## Metrics
            ```json
            {metrics_block}
            ```

            ## Data Version
            ```json
            {data_version_block}
            ```

            ## Baseline Deviations
            ```json
            {deviations_block}
            ```

            ## Status Log
            ```json
            {status_block}
            ```

            ## Final Results
            ```json
            {json.dumps(results or {}, indent=2, default=str)}
            ```

            ## Error
            {error_block}
            """
        ).strip()

    def _write_ci_summary(
        self, results: Mapping[str, Any] | None, error: BaseException | None
    ) -> None:
        """Persist a CI-friendly JSON summary for dashboards and alerts."""

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "experiment": self._experiment.name,
            "status": "error" if error else "completed",
            "metrics": self._metrics,
            "alerts_triggered": self._alerts_written or bool(self._deviations),
            "deviations": [asdict(item) for item in self._deviations],
            "results": results,
            "status_log": self._status_log,
        }
        if hasattr(self._metadata, "__dataclass_fields__"):
            payload["metadata"] = asdict(self._metadata)
        summary_path = self._reports_dir / "ci_summary.json"
        summary_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )

    def _archive_run_dir(self) -> None:
        """Archive the Hydra run directory for long-term storage."""

        run_dir = Path(self._metadata.run_dir)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        archive_base = self._archive_dir / f"{run_dir.name}_{timestamp}"
        shutil.make_archive(
            str(archive_base),
            self._tracking.archive.format,
            root_dir=str(run_dir),
        )


__all__ = [
    "BaselineDeviation",
    "ExperimentDeviationError",
    "ExperimentTracker",
    "NullExperimentTracker",
]

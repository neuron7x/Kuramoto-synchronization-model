#!/usr/bin/env python3
"""Comprehensive backwards-compatibility regression guardrails for TradePulse APIs."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import argparse
import fnmatch
import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

import httpx

from scripts.runtime import (
    apply_environment,
    configure_deterministic_runtime,
    configure_logging,
    parse_env_file,
)

LOGGER = logging.getLogger(__name__)
JSONValue = Any

try:  # Optional YAML support for configuration files.
    import yaml

    _YAML_AVAILABLE = True
except Exception:  # pragma: no cover - yaml is optional and not required in CI
    yaml = None
    _YAML_AVAILABLE = False


def _determine_log_level(verbose: int, quiet: int) -> int:
    """Compute the desired logging level based on verbosity flags."""

    base_level = logging.INFO
    level = base_level - (verbose * 10) + (quiet * 10)
    return max(logging.DEBUG, min(logging.CRITICAL, level))


def _load_environment(env_file: Path | None) -> None:
    """Load environment variables from the provided file if present."""

    candidates = [env_file] if env_file else [Path("scripts/.env"), Path(".env")]
    for candidate in candidates:
        if candidate is None or not candidate.exists():
            continue
        env = parse_env_file(candidate)
        if env:
            apply_environment(env.variables)
            LOGGER.debug("Loaded environment overrides from %s", candidate)
            break


@dataclass(slots=True)
class HttpConfig:
    """Configuration options for HTTP-based traffic replay."""

    base_url: str
    timeout: float = 10.0
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ToleranceRule:
    """Resolved tolerance thresholds for a single JSON path."""

    absolute: float
    relative: float


@dataclass(slots=True)
class ToleranceConfig:
    """Tolerance configuration with optional per-field overrides."""

    absolute: float = 0.0
    relative: float = 0.0
    overrides: Mapping[str, Mapping[str, float]] = field(default_factory=dict)

    def resolve(self, path: str) -> ToleranceRule:
        """Return the tolerance rule that applies to the provided JSON path."""

        for pattern, override in self.overrides.items():
            if fnmatch.fnmatch(path, pattern):
                return ToleranceRule(
                    absolute=float(override.get("absolute", self.absolute)),
                    relative=float(override.get("relative", self.relative)),
                )
        return ToleranceRule(absolute=self.absolute, relative=self.relative)


@dataclass(slots=True)
class DatasetConfig:
    """Configuration for a single dataset participating in replay validation."""

    name: str
    traffic_path: Path
    baseline_path: Path
    tolerance: ToleranceConfig
    whitelist: Sequence[str] = field(default_factory=tuple)
    counterexample_path: Path | None = None
    actual_results_path: Path | None = None
    contract_snapshot_path: Path | None = None


@dataclass(slots=True)
class AlertConfig:
    """Alerting and escalation configuration."""

    channels: Sequence[str] = field(default_factory=lambda: ("stdout",))
    recipients: Sequence[str] = field(default_factory=tuple)
    escalation_after_failures: int = 0
    label: str = "backcompat"


@dataclass(slots=True)
class BackcompatConfig:
    """Top-level configuration for the backwards compatibility runner."""

    datasets: Sequence[DatasetConfig]
    report_dir: Path
    blocking_threshold: float = 0.0
    http: HttpConfig | None = None
    alerts: AlertConfig = field(default_factory=AlertConfig)
    stability_history_path: Path | None = None
    auto_update_baseline: bool = False
    auto_update_release_channels: Sequence[str] = field(default_factory=tuple)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any], base_dir: Path) -> "BackcompatConfig":
        """Build a :class:`BackcompatConfig` from a raw mapping."""

        datasets_payload = payload.get("datasets")
        if not datasets_payload:
            raise ValueError("Configuration must include at least one dataset entry.")

        datasets: list[DatasetConfig] = []
        for entry in datasets_payload:
            name = entry["name"]
            tolerance_cfg = entry.get("tolerance", {})
            overrides = tolerance_cfg.get("overrides", {})
            tolerance = ToleranceConfig(
                absolute=float(tolerance_cfg.get("absolute", 0.0)),
                relative=float(tolerance_cfg.get("relative", 0.0)),
                overrides={str(k): dict(v) for k, v in overrides.items()},
            )
            whitelist = tuple(str(item) for item in entry.get("whitelist", ()))
            datasets.append(
                DatasetConfig(
                    name=str(name),
                    traffic_path=(base_dir / Path(entry["traffic"])).expanduser().resolve(),
                    baseline_path=(base_dir / Path(entry["baseline"])).expanduser().resolve(),
                    tolerance=tolerance,
                    whitelist=whitelist,
                    counterexample_path=(
                        (base_dir / Path(entry["counterexamples"])).expanduser().resolve()
                        if entry.get("counterexamples")
                        else None
                    ),
                    actual_results_path=(
                        (base_dir / Path(entry["actual"])).expanduser().resolve()
                        if entry.get("actual")
                        else None
                    ),
                    contract_snapshot_path=(
                        (base_dir / Path(entry["contract_snapshot"])).expanduser().resolve()
                        if entry.get("contract_snapshot")
                        else None
                    ),
                )
            )

        report_dir = (base_dir / Path(payload.get("report_dir", "reports/backcompat"))).resolve()

        http_cfg = payload.get("http")
        http = None
        if http_cfg:
            http = HttpConfig(
                base_url=str(http_cfg["base_url"]),
                timeout=float(http_cfg.get("timeout", 10.0)),
                headers={str(k): str(v) for k, v in http_cfg.get("headers", {}).items()},
            )

        alerts_cfg = payload.get("alerts", {})
        alerts = AlertConfig(
            channels=tuple(str(ch) for ch in alerts_cfg.get("channels", ("stdout",))),
            recipients=tuple(str(rcp) for rcp in alerts_cfg.get("recipients", ())),
            escalation_after_failures=int(alerts_cfg.get("escalation_after_failures", 0)),
            label=str(alerts_cfg.get("label", "backcompat")),
        )

        stability_history = payload.get("stability_history")
        stability_path = (
            (base_dir / Path(stability_history)).resolve() if stability_history else None
        )

        auto_release_channels = tuple(
            str(ch).lower() for ch in payload.get("auto_update_release_channels", ())
        )

        return cls(
            datasets=datasets,
            report_dir=report_dir,
            blocking_threshold=float(payload.get("blocking_threshold", 0.0)),
            http=http,
            alerts=alerts,
            stability_history_path=stability_path,
            auto_update_baseline=bool(payload.get("auto_update_baseline", False)),
            auto_update_release_channels=auto_release_channels,
        )

    def with_overrides(
        self,
        *,
        report_dir: Path | None = None,
        http_base_url: str | None = None,
        http_timeout: float | None = None,
    ) -> "BackcompatConfig":
        """Return a copy of the configuration applying CLI overrides."""

        http = self.http
        if http_base_url is not None:
            if http is None:
                http = HttpConfig(base_url=http_base_url)
            else:
                http = HttpConfig(
                    base_url=http_base_url,
                    timeout=http_timeout if http_timeout is not None else http.timeout,
                    headers=http.headers,
                )
        elif http_timeout is not None and http is not None:
            http = HttpConfig(base_url=http.base_url, timeout=http_timeout, headers=http.headers)

        return BackcompatConfig(
            datasets=self.datasets,
            report_dir=report_dir or self.report_dir,
            blocking_threshold=self.blocking_threshold,
            http=http,
            alerts=self.alerts,
            stability_history_path=self.stability_history_path,
            auto_update_baseline=self.auto_update_baseline,
            auto_update_release_channels=self.auto_update_release_channels,
        )


@dataclass(slots=True)
class TrafficRecord:
    """Single replay request description."""

    record_id: str
    method: str
    path: str
    query: Mapping[str, Any]
    headers: Mapping[str, str]
    body: JSONValue


@dataclass(slots=True)
class Violation:
    """Deviation discovered during comparison."""

    record_id: str
    path: str
    baseline_value: JSONValue
    candidate_value: JSONValue
    absolute_delta: float | None
    relative_delta: float | None


@dataclass(slots=True)
class DatasetSummary:
    """Summary of comparison results for a dataset."""

    dataset: DatasetConfig
    total_records: int
    violations: list[Violation]
    whitelisted: list[Violation]
    missing_records: list[str]
    unexpected_records: list[str]

    @property
    def blocking_deviation_ratio(self) -> float:
        """Return the ratio of blocking deviations relative to record volume."""

        if self.total_records == 0:
            return 0.0
        total_blocking = len(self.violations) + len(self.missing_records) + len(
            self.unexpected_records
        )
        return total_blocking / self.total_records


@dataclass(slots=True)
class OverallResult:
    """Aggregate result for the runner execution."""

    timestamp: datetime
    summaries: Sequence[DatasetSummary]
    blocked: bool


class BackcompatRunner:
    """Orchestrates traffic replay, comparison, reporting, and alerting."""

    def __init__(self, config: BackcompatConfig, *, release_channel: str | None = None) -> None:
        self.config = config
        self.release_channel = release_channel.lower() if release_channel else None

    def execute(self) -> OverallResult:
        """Run the full backwards compatibility validation workflow."""

        timestamp = datetime.now(timezone.utc)
        summaries: list[DatasetSummary] = []

        self.config.report_dir.mkdir(parents=True, exist_ok=True)
        if self.config.stability_history_path:
            self.config.stability_history_path.parent.mkdir(parents=True, exist_ok=True)

        for dataset in self.config.datasets:
            LOGGER.info("Processing dataset: %s", dataset.name)
            records = self._load_traffic(dataset.traffic_path)
            baseline = self._load_json(dataset.baseline_path)
            candidate = self._obtain_candidate(dataset, records)
            summary = self._compare(dataset, records, baseline, candidate)
            summaries.append(summary)

            if dataset.counterexample_path:
                self._write_counterexamples(dataset.counterexample_path, summary, timestamp)
            if dataset.contract_snapshot_path:
                self._write_contract_snapshot(dataset.contract_snapshot_path, baseline, timestamp)

        self._write_report(summaries, timestamp)
        self._update_stability_history(summaries, timestamp)
        self._dispatch_alerts(summaries, timestamp)
        self._maybe_update_baselines(summaries, timestamp)

        blocked = any(
            summary.blocking_deviation_ratio > self.config.blocking_threshold for summary in summaries
        )

        if blocked:
            LOGGER.error(
                "Blocking deviations detected (threshold=%.4f).", self.config.blocking_threshold
            )
        else:
            LOGGER.info("Backwards compatibility validation succeeded without blocking deviations.")

        return OverallResult(timestamp=timestamp, summaries=summaries, blocked=blocked)

    # ------------------------------------------------------------------
    # Loading helpers

    def _load_traffic(self, path: Path) -> list[TrafficRecord]:
        with path.open("r", encoding="utf-8") as handle:
            records = [json.loads(line) for line in handle if line.strip()]

        result: list[TrafficRecord] = []
        for entry in records:
            result.append(
                TrafficRecord(
                    record_id=str(entry["id"]),
                    method=str(entry.get("method", "GET")),
                    path=str(entry.get("path", "/")),
                    query=dict(entry.get("query", {})),
                    headers={str(k): str(v) for k, v in entry.get("headers", {}).items()},
                    body=entry.get("body"),
                )
            )
        return result

    def _load_json(self, path: Path) -> MutableMapping[str, Any]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if isinstance(payload, Mapping):
            return dict(payload)
        raise ValueError(f"Expected mapping at {path}, received {type(payload)!r}")

    def _obtain_candidate(
        self, dataset: DatasetConfig, records: Sequence[TrafficRecord]
    ) -> MutableMapping[str, Any]:
        if dataset.actual_results_path and dataset.actual_results_path.exists():
            LOGGER.debug("Loading candidate responses from %s", dataset.actual_results_path)
            return self._load_json(dataset.actual_results_path)

        if not self.config.http:
            raise RuntimeError(
                "No candidate results available. Provide 'actual' path in configuration or configure HTTP replay."
            )

        LOGGER.info(
            "Replaying %d records against %s", len(records), self.config.http.base_url
        )
        return self._execute_http_replay(records)

    def _execute_http_replay(self, records: Sequence[TrafficRecord]) -> MutableMapping[str, Any]:
        http_cfg = self.config.http
        if http_cfg is None:  # pragma: no cover - guarded by caller
            raise RuntimeError("HTTP configuration missing")

        responses: dict[str, Any] = {}
        with httpx.Client(base_url=http_cfg.base_url, timeout=http_cfg.timeout) as client:
            for record in records:
                LOGGER.debug("Replaying %s %s", record.method, record.path)
                response = client.request(
                    record.method,
                    record.path,
                    params=record.query,
                    headers={**http_cfg.headers, **record.headers},
                    json=record.body,
                )
                responses[record.record_id] = {
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": self._safe_json(response),
                }
        return responses

    @staticmethod
    def _safe_json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except Exception:
            return response.text

    # ------------------------------------------------------------------
    # Comparison helpers

    def _compare(
        self,
        dataset: DatasetConfig,
        records: Sequence[TrafficRecord],
        baseline: Mapping[str, Any],
        candidate: Mapping[str, Any],
    ) -> DatasetSummary:
        violations: list[Violation] = []
        whitelisted: list[Violation] = []
        missing: list[str] = []
        unexpected: list[str] = []

        record_ids: set[str] = {record.record_id for record in records}
        for record_id in sorted(record_ids | set(baseline) | set(candidate)):
            base_payload = baseline.get(record_id)
            cand_payload = candidate.get(record_id)

            if base_payload is None and cand_payload is not None:
                unexpected.append(record_id)
                continue
            if cand_payload is None and base_payload is not None:
                missing.append(record_id)
                continue
            if base_payload is None and cand_payload is None:
                continue

            assert base_payload is not None and cand_payload is not None  # for mypy
            base_map = _flatten_json(base_payload)
            cand_map = _flatten_json(cand_payload)

            for path in sorted(set(base_map) | set(cand_map)):
                if _is_whitelisted(path, dataset.whitelist):
                    whitelisted.append(
                        Violation(
                            record_id=record_id,
                            path=path,
                            baseline_value=base_map.get(path),
                            candidate_value=cand_map.get(path),
                            absolute_delta=None,
                            relative_delta=None,
                        )
                    )
                    continue

                if path not in base_map:
                    unexpected.append(f"{record_id}:{path}")
                    continue
                if path not in cand_map:
                    missing.append(f"{record_id}:{path}")
                    continue

                base_value = base_map[path]
                cand_value = cand_map[path]
                tolerance = dataset.tolerance.resolve(path)
                if _values_close(base_value, cand_value, tolerance):
                    continue

                abs_delta, rel_delta = _compute_deltas(base_value, cand_value)
                violations.append(
                    Violation(
                        record_id=record_id,
                        path=path,
                        baseline_value=base_value,
                        candidate_value=cand_value,
                        absolute_delta=abs_delta,
                        relative_delta=rel_delta,
                    )
                )

        return DatasetSummary(
            dataset=dataset,
            total_records=len(record_ids),
            violations=violations,
            whitelisted=whitelisted,
            missing_records=missing,
            unexpected_records=unexpected,
        )

    # ------------------------------------------------------------------
    # Artifact generation

    def _write_counterexamples(
        self, destination: Path, summary: DatasetSummary, timestamp: datetime
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8") as handle:
            for violation in summary.violations:
                record = {
                    "dataset": summary.dataset.name,
                    "record_id": violation.record_id,
                    "path": violation.path,
                    "baseline": violation.baseline_value,
                    "candidate": violation.candidate_value,
                    "absolute_delta": violation.absolute_delta,
                    "relative_delta": violation.relative_delta,
                    "timestamp": timestamp.isoformat(),
                }
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _write_contract_snapshot(
        self, destination: Path, baseline: Mapping[str, Any], timestamp: datetime
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        aggregated: dict[str, set[str]] = {}
        for payload in baseline.values():
            for path, value in _flatten_json(payload).items():
                aggregated.setdefault(path, set()).add(_type_name(value))

        snapshot = {
            "generated_at": timestamp.isoformat(),
            "release_channel": self.release_channel,
            "fields": [
                {
                    "path": path,
                    "types": sorted(types),
                }
                for path, types in sorted(aggregated.items())
            ],
        }

        with destination.open("w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, ensure_ascii=False)

    def _write_report(self, summaries: Sequence[DatasetSummary], timestamp: datetime) -> None:
        report_path = self.config.report_dir / f"backcompat_{timestamp:%Y%m%dT%H%M%SZ}.md"
        lines = ["# Backwards Compatibility Validation Report", ""]
        lines.append(f"_Generated at {timestamp.isoformat()}_\n")

        for summary in summaries:
            lines.append(f"## Dataset `{summary.dataset.name}`")
            lines.append(
                f"- Total records: **{summary.total_records}**"  # Basic metrics
            )
            lines.append(f"- Blocking deviations: **{len(summary.violations)}**")
            lines.append(f"- Whitelisted deviations: **{len(summary.whitelisted)}**")
            lines.append(f"- Missing records: **{len(summary.missing_records)}**")
            lines.append(f"- Unexpected records: **{len(summary.unexpected_records)}**\n")

            if summary.violations:
                lines.append("### Blocking Differences")
                for violation in summary.violations:
                    lines.append(
                        "- ``%s`` record ``%s``: baseline=%r candidate=%r (Δ=%.6g, δ=%s)"
                        % (
                            violation.path,
                            violation.record_id,
                            violation.baseline_value,
                            violation.candidate_value,
                            violation.absolute_delta or 0.0,
                            (
                                f"{violation.relative_delta:.6g}"
                                if violation.relative_delta is not None
                                else "n/a"
                            ),
                        )
                    )
                lines.append("")

        report_path.write_text("\n".join(lines), encoding="utf-8")
        LOGGER.info("Report written to %s", report_path)

    def _update_stability_history(
        self, summaries: Sequence[DatasetSummary], timestamp: datetime
    ) -> None:
        if not self.config.stability_history_path:
            return

        history_path = self.config.stability_history_path
        history: list[dict[str, Any]] = []
        if history_path.exists():
            history = json.loads(history_path.read_text(encoding="utf-8"))

        for summary in summaries:
            history.append(
                {
                    "timestamp": timestamp.isoformat(),
                    "dataset": summary.dataset.name,
                    "total_records": summary.total_records,
                    "blocking_deviations": len(summary.violations),
                    "whitelisted": len(summary.whitelisted),
                    "missing": len(summary.missing_records),
                    "unexpected": len(summary.unexpected_records),
                }
            )

        history_path.parent.mkdir(parents=True, exist_ok=True)
        history_path.write_text(json.dumps(history, indent=2), encoding="utf-8")
        LOGGER.debug("Updated stability history at %s", history_path)

    def _dispatch_alerts(self, summaries: Sequence[DatasetSummary], timestamp: datetime) -> None:
        total_blocking = sum(len(summary.violations) for summary in summaries)
        if total_blocking == 0:
            return

        alert_payload = {
            "timestamp": timestamp.isoformat(),
            "label": self.config.alerts.label,
            "total_blocking": total_blocking,
            "datasets": [
                {
                    "name": summary.dataset.name,
                    "blocking": len(summary.violations),
                    "missing": len(summary.missing_records),
                    "unexpected": len(summary.unexpected_records),
                }
                for summary in summaries
                if summary.violations or summary.missing_records or summary.unexpected_records
            ],
            "recipients": list(self.config.alerts.recipients),
        }

        for channel in self.config.alerts.channels:
            if channel == "stdout":
                LOGGER.warning("Regression alert: %s", json.dumps(alert_payload))
            elif channel == "file":
                alert_file = self.config.report_dir / "alerts.json"
                alert_file.write_text(json.dumps(alert_payload, indent=2), encoding="utf-8")
            else:
                LOGGER.warning("Unknown alert channel '%s'", channel)

        if (
            self.config.alerts.escalation_after_failures
            and total_blocking >= self.config.alerts.escalation_after_failures
        ):
            LOGGER.error(
                "Escalation triggered for %d blocking deviations (threshold=%d)",
                total_blocking,
                self.config.alerts.escalation_after_failures,
            )

    def _maybe_update_baselines(
        self, summaries: Sequence[DatasetSummary], timestamp: datetime
    ) -> None:
        if not self.config.auto_update_baseline:
            return

        if self.release_channel and self.config.auto_update_release_channels:
            if self.release_channel not in self.config.auto_update_release_channels:
                LOGGER.info(
                    "Skipping automatic baseline update for release channel '%s'", self.release_channel
                )
                return

        if any(summary.violations for summary in summaries):
            LOGGER.warning("Baseline update skipped due to blocking deviations.")
            return

        for summary in summaries:
            dataset = summary.dataset
            candidate_path = dataset.actual_results_path
            if candidate_path is None or not candidate_path.exists():
                LOGGER.debug(
                    "Skipping baseline update for %s; no candidate artifact available.", dataset.name
                )
                continue

            backup_path = dataset.baseline_path.with_suffix(".backup")
            if dataset.baseline_path.exists():
                dataset.baseline_path.replace(backup_path)

            contents = json.loads(candidate_path.read_text(encoding="utf-8"))
            dataset.baseline_path.write_text(
                json.dumps(contents, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            LOGGER.info("Baseline for %s updated from %s", dataset.name, candidate_path)


def _flatten_json(payload: Any, prefix: str = "$") -> dict[str, Any]:
    result: dict[str, Any] = {}
    if isinstance(payload, Mapping):
        if not payload:
            result[prefix] = {}
        for key, value in payload.items():
            child = f"{prefix}.{key}" if prefix else str(key)
            result.update(_flatten_json(value, child))
    elif isinstance(payload, list):
        if not payload:
            result[prefix] = []
        for index, value in enumerate(payload):
            child = f"{prefix}[{index}]"
            result.update(_flatten_json(value, child))
    else:
        result[prefix] = payload
    return result


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, Mapping):
        return "object"
    return type(value).__name__


def _values_close(base: Any, candidate: Any, tolerance: ToleranceRule) -> bool:
    if isinstance(base, (int, float)) and isinstance(candidate, (int, float)):
        if math.isnan(base) or math.isnan(candidate):
            return False
        absolute_delta = abs(candidate - base)
        relative_delta = absolute_delta / abs(base) if base not in (0, 0.0) else math.inf
        threshold = max(tolerance.absolute, tolerance.relative * abs(base))
        return absolute_delta <= threshold or relative_delta <= tolerance.relative
    return base == candidate


def _compute_deltas(base: Any, candidate: Any) -> tuple[float | None, float | None]:
    if isinstance(base, (int, float)) and isinstance(candidate, (int, float)):
        abs_delta = abs(candidate - base)
        rel_delta: float | None
        if base == 0:
            rel_delta = math.inf if abs_delta else 0.0
        else:
            rel_delta = abs_delta / abs(base)
        return abs_delta, rel_delta
    return None, None


def _is_whitelisted(path: str, whitelist: Sequence[str]) -> bool:
    return any(fnmatch.fnmatch(path, pattern) for pattern in whitelist)


def _load_configuration(path: Path) -> Mapping[str, Any]:
    if path.suffix.lower() in {".yaml", ".yml"}:
        if not _YAML_AVAILABLE:
            raise RuntimeError(
                "YAML configuration requested but PyYAML is not installed in this environment."
            )
        with path.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle)
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True, help="Path to configuration file.")
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=None,
        help="Override report directory defined in configuration.",
    )
    parser.add_argument(
        "--http-base-url",
        type=str,
        default=None,
        help="Override HTTP base URL for replay.",
    )
    parser.add_argument(
        "--http-timeout",
        type=float,
        default=None,
        help="Override HTTP timeout for replay calls.",
    )
    parser.add_argument(
        "--release-channel",
        type=str,
        default=None,
        help="Release channel label used for escalation and auto-baseline policies.",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Force baseline update regardless of configuration defaults.",
    )
    parser.add_argument(
        "-v", "--verbose", action="count", default=0, help="Increase log verbosity."
    )
    parser.add_argument(
        "-q", "--quiet", action="count", default=0, help="Decrease log verbosity."
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Optional environment file containing secrets and overrides.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    configure_deterministic_runtime()
    configure_logging(_determine_log_level(args.verbose, args.quiet))
    _load_environment(args.env_file)

    config_path = args.config.expanduser().resolve()
    raw_config = _load_configuration(config_path)
    config = BackcompatConfig.from_mapping(raw_config, config_path.parent)

    if args.update_baseline:
        config = BackcompatConfig(
            datasets=config.datasets,
            report_dir=config.report_dir,
            blocking_threshold=config.blocking_threshold,
            http=config.http,
            alerts=config.alerts,
            stability_history_path=config.stability_history_path,
            auto_update_baseline=True,
            auto_update_release_channels=config.auto_update_release_channels,
        )

    config = config.with_overrides(
        report_dir=args.report_dir.resolve() if args.report_dir else None,
        http_base_url=args.http_base_url,
        http_timeout=args.http_timeout,
    )

    runner = BackcompatRunner(config, release_channel=args.release_channel)
    result = runner.execute()
    return 1 if result.blocked else 0


if __name__ == "__main__":  # pragma: no cover - exercised through CLI invocation
    raise SystemExit(main())

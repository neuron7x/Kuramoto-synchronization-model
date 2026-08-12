# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""High-assurance data pipeline orchestration primitives.

The goal of this module is to provide an opinionated yet extensible
orchestrator that codifies the battle-tested practices used across GeoSync
for preparing market and alternative data.  The orchestration layer stitches
existing building blocks together (schema validation, quality gates, drift
monitoring, backfill tooling, offline/online materialisation) and guarantees
that every batch honours the strict quality bar required for trading systems.

The orchestrator deliberately focuses on *determinism* and *observability*:

* Sources of truth are evaluated deterministically by priority.
* Schemas and validation contracts are enforced through ``core.data.validation``
  and ``core.data.quality_control``.
* Deduplication, toxicity filtering, and anonymisation are handled centrally so
  downstream consumers can rely on consistent semantics.
* Balancing, stratification, and synthetic augmentation are provided to ensure
  model training sets remain healthy without ad-hoc scripts.
* Drift monitoring hooks into the observability stack to detect distribution
  shifts early.
* Backfill planning leverages the existing ``BackfillPlanner`` so gap filling
  remains uniform across ingestion and retraining pipelines.
* SLA monitoring and quarantine integrate with the dead-letter queue to route
  problematic payloads for manual inspection.
* Managed offline (parquet/warehouse) and online (feature store) serving are
  executed atomically after all quality gates pass.

The implementation aims to be self-documenting while remaining highly
configurable.  Most behaviours can be tuned via declarative dataclasses to keep
complex configuration out of imperative code.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC
from hashlib import blake2b
from time import perf_counter
from typing import Any, Callable, Mapping, MutableMapping, Protocol

import numpy as np
import pandas as pd

from core.data.backfill import BackfillPlanner, BackfillResult, CacheKey
from core.data.dead_letter import DeadLetterQueue, DeadLetterReason
from core.data.feature_store import OnlineFeatureStore
from core.data.quality_control import (
    QualityGateConfig,
    QualityGateError,
    QualityReport,
    QualitySummary,
    validate_and_quarantine,
)
from core.data.validation import TimeSeriesValidationConfig, validate_timeseries_frame
from observability.drift import DriftDetector, FeatureDriftSummary, FeatureSnapshot

# ---------------------------------------------------------------------------
# Configuration dataclasses
# ---------------------------------------------------------------------------


class OfflineWriter(Protocol):
    """Minimal protocol for persisting processed datasets offline."""

    def __call__(
        self, dataset: str, frame: pd.DataFrame, *, metadata: Mapping[str, Any]
    ) -> None: ...


class OnlineWriter(Protocol):
    """Protocol abstraction mirroring ``OnlineFeatureStore.sync`` semantics."""

    def __call__(self, feature_view: str, frame: pd.DataFrame, *, mode: str = "append") -> None: ...


@dataclass(frozen=True, slots=True)
class SourceOfTruthSpec:
    """Declarative definition of a dataset source of truth."""

    name: str
    loader: Callable[["PipelineContext"], pd.DataFrame]
    datasets: frozenset[str] = frozenset()
    priority: int = 100

    def supports(self, dataset: str) -> bool:
        return not self.datasets or dataset in self.datasets


@dataclass(frozen=True, slots=True)
class ToxicityFilterConfig:
    """Configuration for filtering toxic payloads prior to serving."""

    column: str = "toxicity_score"
    threshold: float = 3.0


@dataclass(frozen=True, slots=True)
class AnonymizationRule:
    """Column level anonymisation rule using salted BLAKE2 hashing."""

    column: str
    salt: bytes
    keep_last_chars: int = 0

    def apply(self, frame: pd.DataFrame) -> None:
        if self.column not in frame.columns:
            return
        series = frame[self.column].astype(str)
        hashed = series.map(self._hash_value)
        frame[self.column] = hashed

    def _hash_value(self, value: str) -> str:
        digest = blake2b(key=self.salt, digest_size=32)
        digest.update(value.encode("utf-8"))
        token = digest.hexdigest()
        if self.keep_last_chars <= 0:
            return token
        suffix = value[-self.keep_last_chars :]
        return f"{token}:{suffix}"


@dataclass(frozen=True, slots=True)
class BalanceConfig:
    """Class balancing configuration via random undersampling."""

    column: str
    strategy: str = "undersample"


@dataclass(frozen=True, slots=True)
class StratifiedSplitConfig:
    """Definition of stratified dataset splits."""

    column: str
    splits: Mapping[str, float]
    shuffle: bool = True

    def normalised_splits(self) -> Mapping[str, float]:
        total = sum(self.splits.values())
        if total <= 0:
            raise ValueError("Stratified splits must have a positive total fraction")
        if total > 1.0 + 1e-6:
            raise ValueError("Stratified split fractions cannot exceed 1.0")
        return dict(self.splits)


@dataclass(frozen=True, slots=True)
class SyntheticAugmentationConfig:
    """Configuration for generating synthetic observations via noise injection."""

    samples: int = 0
    noise_scale: float = 0.01


@dataclass(frozen=True, slots=True)
class SLAConfig:
    """Service level objective for pipeline execution latency."""

    target_seconds: float
    strict: bool = False

    def ensure_within_budget(self, duration: float) -> bool:
        if duration <= self.target_seconds:
            return True
        if self.strict:
            raise PipelineSLAError(
                f"Pipeline exceeded SLA: {duration:.3f}s > {self.target_seconds:.3f}s"
            )
        return False


@dataclass(slots=True)
class DataPipelineConfig:
    """Composite configuration driving the orchestrator."""

    sources: tuple[SourceOfTruthSpec, ...]
    schema_registry: Mapping[str, TimeSeriesValidationConfig]
    quality_gates: Mapping[str, QualityGateConfig] = field(default_factory=dict)
    toxicity_filter: ToxicityFilterConfig | None = None
    anonymization_rules: tuple[AnonymizationRule, ...] = ()
    balance: BalanceConfig | None = None
    stratified_split: StratifiedSplitConfig | None = None
    synthetic: SyntheticAugmentationConfig = SyntheticAugmentationConfig()
    drift_detector: DriftDetector | None = None
    dead_letter: DeadLetterQueue | None = None
    backfill_planner: BackfillPlanner | None = None
    sla: SLAConfig | None = None
    offline_writer: OfflineWriter | None = None
    online_writer: OnlineWriter | None = None
    random_seed: int = 7_211_203

    def resolve_schema(self, dataset: str) -> TimeSeriesValidationConfig:
        try:
            return self.schema_registry[dataset]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise PipelineConfigurationError(
                f"No schema registered for dataset '{dataset}'"
            ) from exc

    def resolve_quality_gate(self, dataset: str) -> QualityGateConfig | None:
        return self.quality_gates.get(dataset)


# ---------------------------------------------------------------------------
# Runtime context and result containers
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PipelineContext:
    """Execution context supplied per pipeline invocation."""

    dataset: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    reference_frame: pd.DataFrame | None = None
    expected_index: pd.DatetimeIndex | None = None
    backfill: bool = False
    cache_key: CacheKey | None = None
    feature_view: str | None = None
    offline_dataset: str | None = None


@dataclass(slots=True)
class DataPipelineResult:
    """Outcome of a pipeline execution."""

    dataset: str
    source: str
    clean_frame: pd.DataFrame
    quarantined_frame: pd.DataFrame
    toxic_frame: pd.DataFrame
    synthetic_frame: pd.DataFrame
    stratified_splits: Mapping[str, pd.DataFrame]
    drift_summaries: tuple[FeatureDriftSummary, ...]
    backfill_result: BackfillResult | None
    duration_seconds: float
    sla_met: bool
    metadata: Mapping[str, Any]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PipelineError(RuntimeError):
    """Base class for pipeline related failures."""


class PipelineConfigurationError(PipelineError):
    """Raised when configuration prevents the orchestrator from running."""


class PipelineExecutionError(PipelineError):
    """Raised when a runtime failure prevents completion."""


class PipelineSLAError(PipelineExecutionError):
    """Raised when the configured SLA is violated in strict mode."""


# ---------------------------------------------------------------------------
# Orchestrator implementation
# ---------------------------------------------------------------------------


class DataPipeline:
    """High-level orchestrator coordinating ingestion, validation and serving."""

    def __init__(self, config: DataPipelineConfig) -> None:
        if not config.sources:
            raise PipelineConfigurationError("At least one source of truth must be configured")
        self._config = config
        self._rng = np.random.default_rng(config.random_seed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self, context: PipelineContext) -> DataPipelineResult:
        dataset = context.dataset
        start = perf_counter()

        frame, source_name = self._load_source(dataset, context)
        schema = self._config.resolve_schema(dataset)
        validated = self._validate(frame, schema)
        quality_outcome = self._apply_quality_gates(dataset, validated)
        clean = quality_outcome.clean_frame
        quarantined = quality_outcome.quarantined_frame
        quality_summary = quality_outcome.summary

        toxic_clean, toxic_rows = self._apply_toxicity_filter(clean)
        anonymised = self._apply_anonymisation(toxic_clean)
        balanced = self._apply_balancing(anonymised)
        augmented, synthetic = self._augment_with_synthetic(balanced)
        splits = self._build_stratified_splits(augmented)
        drift_summaries = self._evaluate_drift(dataset, augmented, context)
        # Execute backfill against the pre-synthetic frame to avoid duplicate
        # timestamps introduced by augmentation.
        backfill_result = self._execute_backfill(dataset, balanced, context)

        self._persist(dataset, augmented, context)

        duration = perf_counter() - start
        sla_met = True
        if self._config.sla is not None:
            try:
                sla_met = self._config.sla.ensure_within_budget(duration)
            except PipelineSLAError:
                sla_met = False
                raise
            except PipelineExecutionError:
                sla_met = False
                raise
            except Exception as exc:  # pragma: no cover - defensive guard
                sla_met = False
                raise PipelineExecutionError("Unable to evaluate SLA") from exc

        metadata = {
            "source": source_name,
            "rows": int(augmented.shape[0]),
            "quarantined_rows": int(quarantined.shape[0]),
            "toxic_rows": int(toxic_rows.shape[0]),
            "synthetic_rows": int(synthetic.shape[0]),
            "duration_seconds": duration,
        }
        metadata = {**metadata, **context.metadata}
        metadata["quality"] = quality_summary.to_dict()

        return DataPipelineResult(
            dataset=dataset,
            source=source_name,
            clean_frame=augmented,
            quarantined_frame=quarantined,
            toxic_frame=toxic_rows,
            synthetic_frame=synthetic,
            stratified_splits=splits,
            drift_summaries=drift_summaries,
            backfill_result=backfill_result,
            duration_seconds=duration,
            sla_met=sla_met,
            metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Loading and validation
    # ------------------------------------------------------------------
    def _load_source(self, dataset: str, context: PipelineContext) -> tuple[pd.DataFrame, str]:
        candidates = sorted(self._config.sources, key=lambda spec: spec.priority)
        for spec in candidates:
            if not spec.supports(dataset):
                continue
            frame = spec.loader(context)
            if frame is not None and not frame.empty:
                return frame.copy(), spec.name
        raise PipelineExecutionError(f"No non-empty sources yielded data for dataset '{dataset}'")

    def _validate(self, frame: pd.DataFrame, schema: TimeSeriesValidationConfig) -> pd.DataFrame:
        timestamp_col = schema.timestamp_column
        if timestamp_col not in frame.columns:
            raise PipelineExecutionError(
                f"Timestamp column '{timestamp_col}' missing prior to validation"
            )
        duplicates = frame[frame[timestamp_col].duplicated(keep=False)]
        if not duplicates.empty:
            self._dead_letter(
                duplicates,
                context="duplicate_timestamp",
                reason=DeadLetterReason.VALIDATION_ERROR,
                error="duplicate_timestamp",
            )
            frame = frame.drop_duplicates(subset=timestamp_col, keep="last")
        frame = frame.sort_values(timestamp_col).reset_index(drop=True)
        for column in schema.value_columns:
            if column.dtype and column.name in frame.columns:
                frame[column.name] = frame[column.name].astype(column.dtype)
        validated = validate_timeseries_frame(frame.copy(), schema)
        timestamp_col = schema.timestamp_column
        return validated.sort_values(timestamp_col).reset_index(drop=True)

    # ------------------------------------------------------------------
    # Quality control and toxicity management
    # ------------------------------------------------------------------
    @dataclass(slots=True)
    class _QualityOutcome:
        clean_frame: pd.DataFrame
        quarantined_frame: pd.DataFrame
        summary: QualitySummary

    def _apply_quality_gates(
        self, dataset: str, frame: pd.DataFrame
    ) -> "DataPipeline._QualityOutcome":
        gate = self._config.resolve_quality_gate(dataset)
        if gate is None:
            empty_quarantine = frame.iloc[0:0].copy()
            report = QualityReport(
                clean=frame.copy(),
                quarantined=empty_quarantine.copy(),
                duplicates=empty_quarantine.copy(),
                spikes=empty_quarantine.copy(),
            )
            summary = report.summarise(None)
            return DataPipeline._QualityOutcome(frame, empty_quarantine, summary)

        report = validate_and_quarantine(frame, gate)
        try:
            report.raise_if_blocked()
        except QualityGateError as exc:
            self._dead_letter(
                report.quarantined,
                dataset,
                reason=DeadLetterReason.VALIDATION_ERROR,
                error=exc,
            )
            raise

        quarantined = report.quarantined
        if not quarantined.empty:
            self._dead_letter(
                quarantined,
                dataset,
                reason=DeadLetterReason.VALIDATION_ERROR,
                error="quality_gate_quarantine",
            )

        clean = report.clean
        clean = clean.drop_duplicates(subset=gate.validation_schema.timestamp_column, keep="last")
        summary = report.summarise(gate)
        return DataPipeline._QualityOutcome(clean.reset_index(drop=True), quarantined, summary)

    def _apply_toxicity_filter(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        cfg = self._config.toxicity_filter
        if cfg is None or cfg.column not in frame.columns:
            empty = frame.iloc[0:0].copy()
            return frame, empty
        toxicity = frame[cfg.column].fillna(0.0)
        mask = toxicity > cfg.threshold
        toxic_rows = frame.loc[mask].reset_index(drop=True)
        if not toxic_rows.empty:
            self._dead_letter(
                toxic_rows,
                context="toxicity_filter",
                reason=DeadLetterReason.TOXIC_PAYLOAD,
                error="toxicity_threshold_exceeded",
            )
        clean = frame.loc[~mask].reset_index(drop=True)
        return clean, toxic_rows

    def _apply_anonymisation(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not self._config.anonymization_rules:
            return frame
        anonymised = frame.copy()
        for rule in self._config.anonymization_rules:
            rule.apply(anonymised)
        return anonymised

    def _apply_balancing(self, frame: pd.DataFrame) -> pd.DataFrame:
        cfg = self._config.balance
        if cfg is None or cfg.column not in frame.columns or frame.empty:
            return frame

        grouped = frame.groupby(cfg.column, group_keys=False, sort=False)
        counts = grouped.size()
        if counts.empty:
            return frame

        target = int(counts.min())
        if target <= 0:
            return frame

        sampled = grouped.sample(
            n=target,
            replace=False,
            random_state=int(self._rng.integers(0, np.iinfo(np.int32).max)),
        ).reset_index(drop=True)

        return sampled.sample(
            frac=1.0,
            random_state=int(self._rng.integers(0, np.iinfo(np.int32).max)),
        ).reset_index(drop=True)

    def _build_stratified_splits(self, frame: pd.DataFrame) -> Mapping[str, pd.DataFrame]:
        cfg = self._config.stratified_split
        if cfg is None or frame.empty or cfg.column not in frame.columns:
            return {"full": frame.reset_index(drop=True)}

        splits = tuple(cfg.normalised_splits().items())
        empty_template = frame.iloc[0:0].copy()

        collected_indices: dict[str, list[np.ndarray]] = {name: [] for name, _ in splits}
        remainder_indices: list[np.ndarray] = []

        column = frame[cfg.column]
        null_mask = column.isna()
        if null_mask.any():
            remainder_indices.append(frame.loc[null_mask].index.to_numpy())

        grouped = frame.loc[~null_mask] if null_mask.any() else frame

        for _, group in grouped.groupby(cfg.column, sort=False):
            if group.empty:
                continue

            # pandas 3 Copy-on-Write returns read-only ndarrays from
            # ``Index.to_numpy``; ``Generator.shuffle`` mutates in place
            # and rejects read-only buffers. Force ``copy=True`` so we own
            # a writable buffer regardless of pandas version.
            indices = group.index.to_numpy(copy=True)
            if cfg.shuffle:
                self._rng.shuffle(indices)

            total = len(indices)
            offset = 0
            for name, fraction in splits:
                if fraction <= 0 or offset >= total:
                    continue

                remaining = total - offset
                take = int(math.floor(remaining * fraction))
                if fraction > 0 and take <= 0:
                    take = min(1, remaining)
                else:
                    take = min(take, remaining)

                if take <= 0:
                    continue

                selected = indices[offset : offset + take]
                collected_indices[name].append(selected)
                offset += take

            if offset < total:
                remainder_indices.append(indices[offset:])

        results: MutableMapping[str, pd.DataFrame] = {}
        for name, _ in splits:
            parts = collected_indices[name]
            if parts:
                combined = np.concatenate(parts)
                results[name] = frame.loc[combined].reset_index(drop=True)
            else:
                results[name] = empty_template.copy()

        if remainder_indices:
            combined_remainder = np.concatenate(remainder_indices)
            results["remainder"] = frame.loc[combined_remainder].reset_index(drop=True)
        else:
            results["remainder"] = empty_template.copy()

        return results

    def _augment_with_synthetic(self, frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        cfg = self._config.synthetic
        if frame.empty or cfg.samples <= 0:
            return frame, frame.iloc[0:0].copy()
        numeric_cols = frame.select_dtypes(include=["number"]).columns.tolist()
        if not numeric_cols:
            return frame, frame.iloc[0:0].copy()
        sample = frame.sample(
            n=min(cfg.samples, len(frame)),
            replace=True,
            random_state=self._rng.integers(0, np.iinfo(np.int32).max),
        ).reset_index(drop=True)
        noise = self._rng.normal(0.0, cfg.noise_scale, size=(len(sample), len(numeric_cols)))
        synthetic = sample.copy()
        synthetic.loc[:, numeric_cols] = sample.loc[:, numeric_cols] + noise
        synthetic["synthetic"] = True
        augmented = pd.concat(
            [frame.reset_index(drop=True), synthetic], ignore_index=True
        ).reset_index(drop=True)
        return augmented, synthetic

    # ------------------------------------------------------------------
    # Drift monitoring
    # ------------------------------------------------------------------
    def _evaluate_drift(
        self, dataset: str, frame: pd.DataFrame, context: PipelineContext
    ) -> tuple[FeatureDriftSummary, ...]:
        detector = self._config.drift_detector
        reference = context.reference_frame
        if detector is None or reference is None or frame.empty:
            return tuple()
        numeric_columns = [
            column
            for column in frame.select_dtypes(include=["number"]).columns
            if column in reference.columns
        ]
        summaries: list[FeatureDriftSummary] = []
        for column in numeric_columns:
            current_series = frame[column].dropna().astype(float)
            reference_series = reference[column].dropna().astype(float)
            if current_series.empty or reference_series.empty:
                continue
            snapshot = FeatureSnapshot(
                name=f"{dataset}:{column}",
                reference=reference_series.to_numpy(),
                current=current_series.to_numpy(),
                metadata={"dataset": dataset, "column": column},
            )
            summaries.append(detector.evaluate(snapshot))
        return tuple(summaries)

    # ------------------------------------------------------------------
    # Backfill planning
    # ------------------------------------------------------------------
    def _execute_backfill(
        self, dataset: str, frame: pd.DataFrame, context: PipelineContext
    ) -> BackfillResult | None:
        planner = self._config.backfill_planner
        if not context.backfill or planner is None:
            return None
        if context.expected_index is None or context.cache_key is None:
            raise PipelineConfigurationError(
                "Backfill requested but expected_index or cache_key is missing"
            )

        schema = self._config.resolve_schema(dataset)
        timestamp_col = schema.timestamp_column
        if timestamp_col not in frame.columns:
            raise PipelineExecutionError(
                f"Timestamp column '{timestamp_col}' missing from frame during backfill"
            )

        def loader(key: CacheKey, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
            del key  # loader may not need the cache key in simple setups
            mask = (frame[timestamp_col] >= start) & (frame[timestamp_col] < end)
            subset = frame.loc[mask]
            if subset.empty:
                return frame.iloc[0:0].copy()
            indexed = subset.set_index(timestamp_col)
            return indexed.sort_index()

        result = planner.backfill(
            context.cache_key,
            expected_index=context.expected_index,
            loader=loader,
        )
        return result

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def _persist(self, dataset: str, frame: pd.DataFrame, context: PipelineContext) -> None:
        offline = self._config.offline_writer
        if offline is not None:
            offline_dataset = context.offline_dataset or dataset
            offline(
                offline_dataset,
                frame,
                metadata={
                    "dataset": dataset,
                    "feature_view": context.feature_view,
                    "timestamp": pd.Timestamp.now(tz=UTC).isoformat(),
                },
            )
        online = self._config.online_writer
        if online is not None and context.feature_view is not None:
            online(context.feature_view, frame, mode="overwrite")

    # ------------------------------------------------------------------
    # Dead-letter integration
    # ------------------------------------------------------------------
    def _dead_letter(
        self,
        payload: pd.DataFrame,
        context: str,
        *,
        reason: DeadLetterReason,
        error: Exception | str,
    ) -> None:
        queue = self._config.dead_letter
        if queue is None or payload.empty:
            return
        as_records = payload.to_dict(orient="records")
        for record in as_records:
            queue.push(record, error, context=context, reason=reason)


def build_online_writer(store: OnlineFeatureStore) -> OnlineWriter:
    """Return a callable wrapping :class:`OnlineFeatureStore` for pipeline usage."""

    def writer(feature_view: str, frame: pd.DataFrame, *, mode: str = "append") -> None:
        store.sync(feature_view, frame, mode=mode, validate=True)

    return writer


__all__ = [
    "AnonymizationRule",
    "BalanceConfig",
    "DataPipeline",
    "DataPipelineConfig",
    "DataPipelineResult",
    "OfflineWriter",
    "OnlineWriter",
    "PipelineConfigurationError",
    "PipelineContext",
    "PipelineError",
    "PipelineExecutionError",
    "PipelineSLAError",
    "SLAConfig",
    "SourceOfTruthSpec",
    "StratifiedSplitConfig",
    "SyntheticAugmentationConfig",
    "ToxicityFilterConfig",
    "build_online_writer",
]

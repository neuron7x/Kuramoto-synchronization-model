"""Composable ETL/ELT pipeline engine with reliability tooling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Awaitable, Callable, MutableMapping, Sequence

import pandas as pd
import pandera as pa
from pandera.errors import SchemaError, SchemaErrors
from tenacity import AsyncRetrying, RetryError, retry_if_exception_type, stop_after_attempt, wait_exponential

from .monitoring import AutoReporter, DistributionProfiler, DriftDetector, DriftReport, ProfileSummary, SLAMonitor
from .stores import (
    AuditEntry,
    AuditLog,
    CatalogEntry,
    DataCatalog,
    IdempotencyStore,
    PartitionVersioner,
    QuarantineStore,
    dataframe_signature,
)

Extractor = Callable[["PipelineContext"], Awaitable[pd.DataFrame] | pd.DataFrame]
Transformer = Callable[[pd.DataFrame, "PipelineContext"], Awaitable[pd.DataFrame] | pd.DataFrame]
Loader = Callable[[pd.DataFrame, "PipelineContext"], Awaitable[Any] | Any]
Validator = Callable[[pd.DataFrame, "PipelineContext"], Awaitable[pd.DataFrame] | pd.DataFrame]


async def _maybe_await(obj: Awaitable[Any] | Any) -> Any:
    if asyncio.iscoroutine(obj) or isinstance(obj, Awaitable):
        return await obj  # type: ignore[return-value]
    return obj


@dataclass(slots=True)
class RetryPolicy:
    """Unified retry configuration shared across segments."""

    attempts: int = 3
    base: float = 1.0
    max_wait: float = 30.0

    async def run(self, func: Callable[..., Awaitable[Any] | Any], *args: Any, **kwargs: Any) -> Any:
        retrying = AsyncRetrying(
            retry=retry_if_exception_type(Exception),
            stop=stop_after_attempt(self.attempts),
            wait=wait_exponential(multiplier=self.base, max=self.max_wait),
            reraise=True,
        )
        async for attempt in retrying:  # pragma: no branch - tenacity handles control
            with attempt:
                return await _maybe_await(func(*args, **kwargs))
        raise RuntimeError("Retry loop exited unexpectedly")


@dataclass(slots=True)
class PipelineSegment:
    """Represents a logical slice of an ETL/ELT pipeline."""

    name: str
    extract: Extractor
    transform: Sequence[Transformer] = field(default_factory=tuple)
    load: Loader | None = None
    schema: pa.DataFrameSchema | None = None
    validators: Sequence[Validator] = field(default_factory=tuple)
    deduplicate_on: Sequence[str] | None = None
    catalog_dataset: str | None = None


@dataclass(slots=True)
class PipelineRunConfig:
    """Run-time configuration passed to a pipeline execution."""

    run_id: str
    partition_key: str
    description: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    restart_from: str | None = None
    baseline_frames: dict[str, pd.DataFrame] = field(default_factory=dict)


@dataclass(slots=True)
class PipelineContext:
    """Mutable context passed through segment lifecycle."""

    run_config: PipelineRunConfig
    metadata: MutableMapping[str, Any]
    segment_outputs: MutableMapping[str, pd.DataFrame]


@dataclass(slots=True)
class SegmentResult:
    """Captured output and metadata for a single segment execution."""

    data: pd.DataFrame
    profiles: list[ProfileSummary]
    drift_reports: list[DriftReport]
    load_result: Any | None


@dataclass(slots=True)
class PipelineRunResult:
    """Aggregate view over an entire pipeline execution."""

    run_id: str
    outputs: dict[str, pd.DataFrame]
    audit_entries: list[AuditEntry]
    profiles: dict[str, list[ProfileSummary]]
    drift_reports: dict[str, list[DriftReport]]
    sla_breaches: list[str]
    report: str | None
    context_snapshot: dict[str, Any]


class ETLPipeline:
    """High-level orchestrator implementing resilient ETL semantics."""

    def __init__(
        self,
        segments: Sequence[PipelineSegment],
        *,
        retry_policy: RetryPolicy | None = None,
        idempotency_store: IdempotencyStore | None = None,
        audit_log: AuditLog | None = None,
        data_catalog: DataCatalog | None = None,
        partition_versioner: PartitionVersioner | None = None,
        quarantine_store: QuarantineStore | None = None,
        profiler: DistributionProfiler | None = None,
        drift_detector: DriftDetector | None = None,
        sla_monitor: SLAMonitor | None = None,
        auto_reporter: AutoReporter | None = None,
    ) -> None:
        self._segments = list(segments)
        self._retry_policy = retry_policy or RetryPolicy()
        self._idempotency_store = idempotency_store or IdempotencyStore()
        self._audit_log = audit_log or AuditLog()
        self._data_catalog = data_catalog or DataCatalog()
        self._partition_versioner = partition_versioner or PartitionVersioner()
        self._quarantine = quarantine_store or QuarantineStore()
        self._profiler = profiler or DistributionProfiler()
        self._drift_detector = drift_detector or DriftDetector()
        self._sla_monitor = sla_monitor
        self._auto_reporter = auto_reporter
        self._run_cache: dict[str, PipelineRunResult] = {}
        self._run_configs: dict[str, PipelineRunConfig] = {}

    @property
    def audit_log(self) -> AuditLog:
        return self._audit_log

    @property
    def data_catalog(self) -> DataCatalog:
        return self._data_catalog

    @property
    def quarantine_store(self) -> QuarantineStore:
        return self._quarantine

    async def run(self, config: PipelineRunConfig, *, allow_rerun: bool = False) -> PipelineRunResult:
        """Execute pipeline segments with resilience features."""

        if not allow_rerun and not self._idempotency_store.check_and_register(config.run_id):
            raise ValueError(f"Run {config.run_id} has already been processed")

        self._run_configs[config.run_id] = replace(config)
        context = PipelineContext(
            run_config=config,
            metadata=dict(config.metadata),
            segment_outputs={},
        )

        previous_result = self._run_cache.get(config.run_id)
        if previous_result is not None:
            context.segment_outputs.update(previous_result.outputs)

        outputs: dict[str, pd.DataFrame] = {}
        profiles: dict[str, list[ProfileSummary]] = {}
        drifts: dict[str, list[DriftReport]] = {}
        audit_entries: list[AuditEntry] = []

        skipping = config.restart_from is not None

        for segment in self._segments:
            if skipping:
                if segment.name == config.restart_from:
                    skipping = False
                else:
                    continue

            start = datetime.utcnow()
            try:
                result: SegmentResult = await self._retry_policy.run(
                    self._execute_segment, segment, context
                )
            except RetryError as exc:
                finished = datetime.utcnow()
                audit_entries.append(
                    AuditEntry(
                        run_id=config.run_id,
                        segment=segment.name,
                        status="FAILED",
                        started_at=start,
                        finished_at=finished,
                        details={"error": repr(exc.last_attempt.exception())},
                    )
                )
                raise exc.last_attempt.exception() from exc
            finished = datetime.utcnow()
            audit_entry = AuditEntry(
                run_id=config.run_id,
                segment=segment.name,
                status="SUCCESS",
                started_at=start,
                finished_at=finished,
                details={"rows": int(result.data.shape[0])},
            )
            audit_entries.append(audit_entry)
            self._audit_log.record(audit_entry)

            outputs[segment.name] = result.data
            profiles[segment.name] = result.profiles
            drifts[segment.name] = result.drift_reports
            context.segment_outputs[segment.name] = result.data

        sla_breaches: list[str] = []
        if self._sla_monitor is not None:
            sla_breaches = self._sla_monitor.evaluate(audit_entries)

        report = None
        if self._auto_reporter is not None:
            report = self._auto_reporter.render(
                run_id=config.run_id,
                audit_entries=audit_entries,
                sla_findings=sla_breaches,
            )

        result = PipelineRunResult(
            run_id=config.run_id,
            outputs=outputs,
            audit_entries=audit_entries,
            profiles=profiles,
            drift_reports=drifts,
            sla_breaches=sla_breaches,
            report=report,
            context_snapshot={
                "metadata": dict(context.metadata),
                "segment_outputs": {k: v.copy(deep=True) for k, v in context.segment_outputs.items()},
            },
        )
        self._run_cache[config.run_id] = result
        return result

    async def _execute_segment(
        self, segment: PipelineSegment, context: PipelineContext
    ) -> SegmentResult:
        frame = await _maybe_await(segment.extract(context))
        if not isinstance(frame, pd.DataFrame):  # pragma: no cover - guard rail
            raise TypeError(
                f"Segment {segment.name} extractor returned {type(frame)!r}, expected pandas.DataFrame"
            )

        if segment.deduplicate_on:
            duplicates = frame.duplicated(subset=list(segment.deduplicate_on), keep="first")
            if duplicates.any():
                self._quarantine.append(
                    f"deduplicated:{segment.name}", frame.loc[duplicates]
                )
                frame = frame.loc[~duplicates].copy()

        if segment.schema is not None:
            try:
                frame = segment.schema.validate(frame, lazy=True)
            except SchemaErrors as exc:
                failure_frame = exc.failure_cases
                self._quarantine.append(f"schema:{segment.name}", failure_frame)
                raise
            except SchemaError as exc:
                raise

        for transform in segment.transform:
            frame = await _maybe_await(transform(frame, context))
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(
                    f"Transform in segment {segment.name} must return DataFrame, got {type(frame)!r}"
                )

        for validator in segment.validators:
            invalid_rows = await _maybe_await(validator(frame, context))
            if not isinstance(invalid_rows, pd.DataFrame):
                raise TypeError(
                    f"Validator in segment {segment.name} must return DataFrame of invalid rows"
                )
            if not invalid_rows.empty:
                self._quarantine.append(
                    f"validator:{segment.name}:{getattr(validator, '__name__', 'anonymous')}",
                    invalid_rows,
                )
                frame = frame.drop(index=invalid_rows.index).reset_index(drop=True)

        load_result = None
        if segment.load is not None:
            load_result = await _maybe_await(segment.load(frame, context))

        profile_results = self._profiler.profile(frame)
        drift_reports: list[DriftReport] = []
        baseline = context.run_config.baseline_frames.get(segment.name)
        if baseline is not None and not baseline.empty and not frame.empty:
            drift_reports = self._drift_detector.compare(baseline, frame)

        if segment.catalog_dataset is not None:
            version = self._partition_versioner.next_version(
                f"{segment.catalog_dataset}:{context.run_config.partition_key}"
            )
            entry = CatalogEntry(
                name=segment.catalog_dataset,
                version=f"v{version}",
                created_at=datetime.utcnow(),
                schema_signature=dataframe_signature(frame),
                row_count=int(frame.shape[0]),
                source_run_id=context.run_config.run_id,
                extras={"partition": context.run_config.partition_key},
            )
            self._data_catalog.register(entry)

        return SegmentResult(
            data=frame,
            profiles=profile_results,
            drift_reports=drift_reports,
            load_result=load_result,
        )

    async def restart_segment(self, run_id: str, segment_name: str) -> PipelineRunResult:
        """Re-run the pipeline starting from a particular segment."""

        config = self._run_configs.get(run_id)
        if config is None:
            raise KeyError(f"Unknown run_id {run_id}")
        restart_config = replace(config, restart_from=segment_name)
        return await self.run(restart_config, allow_rerun=True)


class PipelineScheduler:
    """Simple asynchronous scheduler with dynamic worker scaling."""

    def __init__(
        self,
        pipeline: ETLPipeline,
        *,
        resource_scaler: Callable[[int], int] | None = None,
        poll_interval: timedelta = timedelta(seconds=1),
    ) -> None:
        self._pipeline = pipeline
        self._resource_scaler = resource_scaler or (lambda pending: max(1, min(8, 1 + pending)))
        self._poll_interval = poll_interval
        self._queue: asyncio.Queue[PipelineRunConfig] = asyncio.Queue()
        self._workers: list[asyncio.Task[None]] = []
        self._running = False

    async def submit(self, config: PipelineRunConfig) -> None:
        await self._queue.put(config)
        await self._maybe_scale()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self._maybe_scale()

    async def shutdown(self) -> None:
        self._running = False
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def _worker(self) -> None:
        try:
            while self._running:
                config = await self._queue.get()
                try:
                    await self._pipeline.run(config)
                finally:
                    self._queue.task_done()
        except asyncio.CancelledError:  # pragma: no cover - cooperative cancellation
            return

    async def _maybe_scale(self) -> None:
        if not self._running:
            return
        desired_workers = self._resource_scaler(self._queue.qsize())
        while len(self._workers) < desired_workers:
            worker = asyncio.create_task(self._worker())
            self._workers.append(worker)
        # shrink workers lazily when queue drains
        while len(self._workers) > desired_workers > 0:
            worker = self._workers.pop()
            worker.cancel()

    async def run_forever(self) -> None:
        await self.start()
        try:
            while self._running:
                await asyncio.sleep(self._poll_interval.total_seconds())
                await self._maybe_scale()
        finally:
            await self.shutdown()

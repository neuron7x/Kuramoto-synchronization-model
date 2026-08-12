# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Data quality gates for ingestion pipelines."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)
from typing_extensions import Literal

from core.data.validation import (
    TimeSeriesValidationConfig,
    TimeSeriesValidationError,
    validate_timeseries_frame,
)


class QualityGateError(TimeSeriesValidationError):
    """Raised when a batch violates a non-recoverable quality gate."""


class RangeCheck(BaseModel):
    """Declarative boundary constraints for numeric columns."""

    model_config = ConfigDict(frozen=True, strict=True)

    column: StrictStr = Field(
        ..., min_length=1, description="Column subject to the range guard"
    )
    min_value: StrictFloat | StrictInt | None = Field(
        default=None,
        description="Lower bound allowed for the column. ``None`` disables the guard.",
    )
    max_value: StrictFloat | StrictInt | None = Field(
        default=None,
        description="Upper bound allowed for the column. ``None`` disables the guard.",
    )
    inclusive_min: StrictBool = Field(
        default=True, description="Treat the lower bound as inclusive"
    )
    inclusive_max: StrictBool = Field(
        default=True, description="Treat the upper bound as inclusive"
    )

    @model_validator(mode="after")
    def _ensure_bounds(self) -> "RangeCheck":
        if self.min_value is None and self.max_value is None:
            raise QualityGateError(
                "RangeCheck must define at least a minimum or maximum bound"
            )
        if (
            self.min_value is not None
            and self.max_value is not None
            and float(self.min_value) > float(self.max_value)
        ):
            raise QualityGateError("RangeCheck minimum bound exceeds maximum bound")
        return self


class TemporalContract(BaseModel):
    """Guarantees about the temporal span of an ingestion batch."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, strict=True)

    earliest: pd.Timestamp | None = Field(
        default=None,
        description="Earliest timestamp permitted in the batch",
    )
    latest: pd.Timestamp | None = Field(
        default=None,
        description="Latest timestamp permitted in the batch",
    )
    expected_start: pd.Timestamp | None = Field(
        default=None,
        description="Exact timestamp the batch must start at (within tolerance)",
    )
    expected_end: pd.Timestamp | None = Field(
        default=None,
        description="Exact timestamp the batch must end at (within tolerance)",
    )
    tolerance: pd.Timedelta = Field(
        default=pd.Timedelta(0),
        description="Tolerance applied when comparing expected start/end",
    )
    max_lag: pd.Timedelta | None = Field(
        default=None,
        description="Maximum allowed delay between now and the last timestamp",
    )

    @field_validator(
        "earliest", "latest", "expected_start", "expected_end", mode="before"
    )
    @classmethod
    def _coerce_timestamp(cls, value: object) -> pd.Timestamp | None:
        if value is None:
            return None
        if isinstance(value, pd.Timestamp):
            return value
        try:
            return pd.Timestamp(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive path
            raise QualityGateError(
                f"Unable to parse timestamp value: {value!r}"
            ) from exc

    @field_validator("tolerance", mode="before")
    @classmethod
    def _coerce_timedelta(cls, value: object) -> pd.Timedelta:
        if isinstance(value, pd.Timedelta):
            return value
        if isinstance(value, timedelta):
            return pd.Timedelta(value)
        if value is None:
            return pd.Timedelta(0)
        try:
            return pd.Timedelta(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive path
            raise QualityGateError(
                f"Unable to parse timedelta value: {value!r}"
            ) from exc

    @field_validator("max_lag", mode="before")
    @classmethod
    def _coerce_optional_timedelta(cls, value: object) -> pd.Timedelta | None:
        if value is None:
            return None
        if isinstance(value, pd.Timedelta):
            return value
        if isinstance(value, timedelta):
            return pd.Timedelta(value)
        try:
            return pd.Timedelta(value)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive path
            raise QualityGateError(
                f"Unable to parse timedelta value: {value!r}"
            ) from exc

    @model_validator(mode="after")
    def _validate_expectations(self) -> "TemporalContract":
        if (
            self.expected_start
            and self.earliest
            and self.expected_start < self.earliest
        ):
            raise QualityGateError(
                "expected_start must not be before the earliest bound"
            )
        if self.expected_end and self.latest and self.expected_end > self.latest:
            raise QualityGateError("expected_end must not exceed the latest bound")
        return self


class QualityGateConfig(BaseModel):
    """Composite quality gate configuration for ingestion payloads."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True, strict=True)

    validation_schema: TimeSeriesValidationConfig = Field(
        ..., description="Underlying schema contract", alias="schema"
    )
    price_column: StrictStr = Field(
        default="close",
        min_length=1,
        description="Column used for anomaly detection thresholds",
    )
    anomaly_threshold: StrictFloat = Field(
        default=6.0,
        gt=0,
        description="Z-score at which a point is considered a spike",
    )
    anomaly_window: StrictInt = Field(
        default=20,
        ge=2,
        description="Window used to compute rolling statistics for z-score",
    )
    range_checks: Sequence[RangeCheck] = Field(
        default_factory=tuple,
        description="Per-column boundary guards",
    )
    temporal_contract: TemporalContract | None = Field(
        default=None,
        description="Optional temporal guarantees enforced on the batch",
    )
    max_quarantine_fraction: StrictFloat = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Maximum tolerated share of quarantined rows before blocking the batch",
    )

    @model_validator(mode="after")
    def _validate_price_column(self) -> "QualityGateConfig":
        available = {
            self.validation_schema.timestamp_column,
            *(col.name for col in self.validation_schema.value_columns),
        }
        if self.price_column not in available:
            raise QualityGateError(
                f"price_column '{self.price_column}' is not declared in the validation schema"
            )
        seen: set[str] = set()
        duplicates: set[str] = set()
        for check in self.range_checks:
            if check.column in seen:
                duplicates.add(check.column)
            seen.add(check.column)
        if duplicates:
            joined = ", ".join(sorted(duplicates))
            raise QualityGateError(f"Duplicate range checks defined for: {joined}")
        return self


@dataclass(slots=True)
class QualityReport:
    """Outcome of the quality gate validation."""

    clean: pd.DataFrame
    quarantined: pd.DataFrame
    duplicates: pd.DataFrame
    spikes: pd.DataFrame
    range_violations: Dict[str, pd.DataFrame] = field(default_factory=dict)
    contract_breaches: Tuple[str, ...] = field(default_factory=tuple)
    blocked: bool = False

    def raise_if_blocked(self) -> None:
        """Raise a :class:`QualityGateError` when the batch is unusable."""

        if not self.blocked:
            return
        reasons: List[str] = []
        if self.contract_breaches:
            reasons.extend(self.contract_breaches)
        if self.range_violations:
            for column, payload in self.range_violations.items():
                reasons.append(
                    f"{payload.shape[0]} rows in column '{column}' violate configured bounds"
                )
        if not reasons and not self.quarantined.empty:
            reasons.append("Quarantine ratio exceeded configured threshold")
        detail = "; ".join(reasons) or "Batch blocked by quality gate"
        raise QualityGateError(detail)

    def summarise(self, gate: "QualityGateConfig" | None = None) -> "QualitySummary":
        """Return structured quality metrics for observability and reporting."""

        return summarise_quality(self, gate)


@dataclass(frozen=True, slots=True)
class ValidatorOutcome:
    """Status of a validator grouped by policy category."""

    name: str
    category: Literal["syntax", "semantics", "security"]
    status: Literal["pass", "warn", "fail"]
    detail: str


@dataclass(frozen=True, slots=True)
class QualitySummary:
    """Structured quality metrics emitted after running a gate."""

    total_rows: int
    clean_rows: int
    quarantined_rows: int
    duplicate_rows: int
    spike_rows: int
    range_violation_rows: Mapping[str, int]
    contract_breaches: Tuple[str, ...]
    blocked: bool
    quarantine_ratio: float
    duplicate_ratio: float
    spike_ratio: float
    sanitised_rows: int
    sanitised_ratio: float
    validator_outcomes: Tuple[ValidatorOutcome, ...]
    range_limits: Mapping[str, Mapping[str, float | bool | None]]
    anomaly_threshold: float | None
    anomaly_window: int | None

    def to_dict(self) -> Dict[str, object]:
        """Convert the summary into JSON-serialisable primitives."""

        return {
            "total_rows": self.total_rows,
            "clean_rows": self.clean_rows,
            "quarantined_rows": self.quarantined_rows,
            "duplicate_rows": self.duplicate_rows,
            "spike_rows": self.spike_rows,
            "range_violation_rows": dict(self.range_violation_rows),
            "contract_breaches": list(self.contract_breaches),
            "blocked": self.blocked,
            "quarantine_ratio": self.quarantine_ratio,
            "duplicate_ratio": self.duplicate_ratio,
            "spike_ratio": self.spike_ratio,
            "sanitised_rows": self.sanitised_rows,
            "sanitised_ratio": self.sanitised_ratio,
            "validator_outcomes": [
                {
                    "name": outcome.name,
                    "category": outcome.category,
                    "status": outcome.status,
                    "detail": outcome.detail,
                }
                for outcome in self.validator_outcomes
            ],
            "range_limits": {
                column: dict(limits) for column, limits in self.range_limits.items()
            },
            "anomaly_threshold": self.anomaly_threshold,
            "anomaly_window": self.anomaly_window,
        }


def summarise_quality(
    report: QualityReport, gate: "QualityGateConfig" | None = None
) -> QualitySummary:
    """Derive aggregate metrics and validator outcomes for a quality report."""

    clean_rows = int(report.clean.shape[0])
    quarantined_rows = int(report.quarantined.shape[0])
    clean_counter: Counter[tuple[object, ...]] = Counter(
        tuple(row) for row in report.clean.itertuples(index=False, name=None)
    )
    quarantined_counter: Counter[tuple[object, ...]] = Counter(
        tuple(row) for row in report.quarantined.itertuples(index=False, name=None)
    )
    overlap = sum(
        min(clean_counter[key], quarantined_counter[key])
        for key in clean_counter.keys() & quarantined_counter.keys()
    )
    total_rows = clean_rows + quarantined_rows - overlap
    duplicate_rows = int(report.duplicates.shape[0])
    spike_rows = int(report.spikes.shape[0])
    denominator = max(total_rows, 1)
    range_violation_rows = {
        column: int(payload.shape[0])
        for column, payload in report.range_violations.items()
    }

    range_limits: Dict[str, Dict[str, float | bool | None]] = {}
    anomaly_threshold: float | None = None
    anomaly_window: int | None = None
    validator_outcomes: List[ValidatorOutcome] = []

    if gate is not None:
        anomaly_threshold = float(gate.anomaly_threshold)
        anomaly_window = int(gate.anomaly_window)
        for check in gate.range_checks:
            range_limits[check.column] = {
                "min_value": (
                    float(check.min_value) if check.min_value is not None else None
                ),
                "max_value": (
                    float(check.max_value) if check.max_value is not None else None
                ),
                "inclusive_min": bool(check.inclusive_min),
                "inclusive_max": bool(check.inclusive_max),
            }
        syntax_detail = (
            f"Schema enforced on '{gate.validation_schema.timestamp_column}' with"
            f" {len(gate.validation_schema.value_columns)} value columns"
        )
        validator_outcomes.append(
            ValidatorOutcome(
                name="schema", category="syntax", status="pass", detail=syntax_detail
            )
        )
    else:
        validator_outcomes.append(
            ValidatorOutcome(
                name="schema",
                category="syntax",
                status="warn",
                detail="Quality gate disabled; schema guarantees were not evaluated",
            )
        )

    semantics_status: Literal["pass", "warn", "fail"] = "pass"
    semantics_notes: List[str] = []

    if report.contract_breaches:
        semantics_status = "fail"
        semantics_notes.extend(report.contract_breaches)
    if report.range_violations:
        semantics_status = "fail"
        for column, payload in report.range_violations.items():
            semantics_notes.append(
                f"{payload.shape[0]} rows in '{column}' breached configured bounds"
            )
    if spike_rows > 0:
        if semantics_status != "fail":
            semantics_status = "warn"
        semantics_notes.append(
            f"{spike_rows} anomalous points quarantined by z-score guard"
        )

    if report.blocked:
        blocked_note = "Batch blocked by quality gate"
        if (
            not report.contract_breaches
            and not report.range_violations
            and spike_rows == 0
            and not report.quarantined.empty
        ):
            blocked_note = (
                "Batch blocked by quality gate after sanitised share exceeded policy"
                " threshold"
            )
        if blocked_note not in semantics_notes:
            semantics_notes.append(blocked_note)
        if semantics_status == "pass":
            semantics_status = "warn"

    validator_outcomes.append(
        ValidatorOutcome(
            name="anomaly-and-contract",
            category="semantics",
            status=semantics_status,
            detail=(
                "; ".join(semantics_notes)
                if semantics_notes
                else "All semantic checks passed"
            ),
        )
    )

    security_status: Literal["pass", "warn", "fail"] = "pass"
    security_detail = "No duplicate timestamps detected"
    if duplicate_rows > 0:
        security_status = "warn"
        security_detail = f"{duplicate_rows} duplicate rows quarantined"
    if clean_rows:
        timestamp_column = None
        if (
            gate is not None
            and gate.validation_schema.timestamp_column in report.clean.columns
        ):
            timestamp_column = gate.validation_schema.timestamp_column
        elif (
            report.clean.columns.size > 0
            and report.clean.columns[0] in report.clean.columns
        ):
            timestamp_column = report.clean.columns[0]
        if (
            timestamp_column is not None
            and report.clean[timestamp_column].duplicated().any()
        ):
            security_status = "fail"
            security_detail = "Duplicate timestamps remained in the clean dataset"

    validator_outcomes.append(
        ValidatorOutcome(
            name="duplicate-timestamps",
            category="security",
            status=security_status,
            detail=security_detail,
        )
    )

    return QualitySummary(
        total_rows=total_rows,
        clean_rows=clean_rows,
        quarantined_rows=quarantined_rows,
        duplicate_rows=duplicate_rows,
        spike_rows=spike_rows,
        range_violation_rows=range_violation_rows,
        contract_breaches=report.contract_breaches,
        blocked=report.blocked,
        quarantine_ratio=quarantined_rows / denominator,
        duplicate_ratio=duplicate_rows / denominator,
        spike_ratio=spike_rows / denominator,
        sanitised_rows=quarantined_rows,
        sanitised_ratio=quarantined_rows / denominator,
        validator_outcomes=tuple(validator_outcomes),
        range_limits=range_limits,
        anomaly_threshold=anomaly_threshold,
        anomaly_window=anomaly_window,
    )


def _zscore(series: pd.Series, window: int) -> pd.Series:
    rolling = series.rolling(window=window, min_periods=window)
    mean = rolling.mean().shift(1)
    std = rolling.std(ddof=0).shift(1)
    return (series - mean) / std.replace(0, np.nan)


def quarantine_anomalies(
    frame: pd.DataFrame,
    *,
    threshold: float,
    window: int,
    price_column: str,
) -> Dict[str, pd.DataFrame]:
    """Split the frame into clean rows and anomalies based on z-score."""

    if frame.empty:
        return {"clean": frame, "spikes": frame, "duplicates": frame}
    duplicates = frame[frame.index.duplicated(keep=False)]
    deduped = frame[~frame.index.duplicated(keep="first")]
    scores = _zscore(deduped[price_column], window)
    spikes = deduped[np.abs(scores) > threshold]
    clean = deduped.drop(spikes.index, errors="ignore")
    return {"clean": clean, "spikes": spikes, "duplicates": duplicates}


def _apply_range_checks(
    frame: pd.DataFrame, checks: Iterable[RangeCheck], timestamp_col: str
) -> Dict[str, pd.DataFrame]:
    violations: Dict[str, pd.DataFrame] = {}
    for check in checks:
        if check.column not in frame.columns:
            raise QualityGateError(
                f"Range check column '{check.column}' is not present in the validated payload"
            )
        series = frame[check.column]
        mask = pd.Series(False, index=frame.index)
        if check.min_value is not None:
            min_value = float(check.min_value)
            mask |= (
                series <= min_value if not check.inclusive_min else series < min_value
            )
        if check.max_value is not None:
            max_value = float(check.max_value)
            mask |= (
                series >= max_value if not check.inclusive_max else series > max_value
            )
        mask &= series.notna()
        if mask.any():
            payload = frame.loc[mask].copy()
            violations[check.column] = payload.set_index(timestamp_col, drop=False)
    return violations


def _enforce_temporal_contract(
    timestamps: pd.Series, contract: TemporalContract
) -> Tuple[Tuple[str, ...], bool]:
    breaches: List[str] = []
    blocked = False
    if timestamps.empty:
        return tuple(breaches), blocked
    first = timestamps.iloc[0]
    last = timestamps.iloc[-1]
    tz = getattr(last, "tz", None)

    def _align_contract_timestamp(
        value: pd.Timestamp | None, *, field: str
    ) -> pd.Timestamp | None:
        if value is None:
            return None
        value_tz = getattr(value, "tz", None)
        if tz is None:
            if value_tz is not None:
                raise QualityGateError(
                    "Temporal contract uses timezone-aware value for"
                    f" '{field}' but the ingested timestamps are tz-naive"
                )
            return value
        if value_tz is None:
            return value.tz_localize(tz)
        if value_tz != tz:
            return value.tz_convert(tz)
        return value

    earliest = _align_contract_timestamp(contract.earliest, field="earliest")
    latest = _align_contract_timestamp(contract.latest, field="latest")
    expected_start = _align_contract_timestamp(
        contract.expected_start, field="expected_start"
    )
    expected_end = _align_contract_timestamp(
        contract.expected_end, field="expected_end"
    )
    if earliest is not None and first < earliest:
        breaches.append(
            f"First timestamp {first} is earlier than allowed earliest {earliest}"
        )
        blocked = True
    if latest is not None and last > latest:
        breaches.append(f"Last timestamp {last} exceeds allowed latest {latest}")
        blocked = True
    if expected_start is not None:
        delta = abs(first - expected_start)
        if delta > contract.tolerance:
            breaches.append(
                f"Batch starts at {first} but expected {expected_start} ± {contract.tolerance}"
            )
            blocked = True
    if expected_end is not None:
        delta = abs(last - expected_end)
        if delta > contract.tolerance:
            breaches.append(
                f"Batch ends at {last} but expected {expected_end} ± {contract.tolerance}"
            )
            blocked = True
    if contract.max_lag is not None:
        reference = pd.Timestamp.now(tz=tz)
        lag = reference - last
        if lag > contract.max_lag:
            breaches.append(
                f"Last timestamp is stale by {lag}, exceeding allowed lag {contract.max_lag}"
            )
            blocked = True
    return tuple(breaches), blocked


def validate_and_quarantine(
    frame: pd.DataFrame, gate: QualityGateConfig
) -> QualityReport:
    """Validate a DataFrame and quarantine anomalies according to the configured gates."""

    config = gate.validation_schema
    timestamp_col = config.timestamp_column
    duplicates = frame[frame[timestamp_col].duplicated(keep=False)]
    working = frame.drop_duplicates(subset=timestamp_col, keep="first").copy()
    for column in config.value_columns:
        if column.dtype:
            working[column.name] = working[column.name].astype(column.dtype)
    validated = validate_timeseries_frame(working, config)

    buckets = quarantine_anomalies(
        validated.set_index(timestamp_col),
        threshold=float(gate.anomaly_threshold),
        window=int(gate.anomaly_window),
        price_column=gate.price_column,
    )

    clean = buckets["clean"].reset_index()
    quarantined = pd.concat(
        [buckets["spikes"], buckets["duplicates"]]
    ).drop_duplicates()
    quarantined = pd.concat(
        [quarantined, duplicates.set_index(timestamp_col)], axis=0
    ).drop_duplicates()
    quarantined = quarantined.reset_index()

    range_violations = _apply_range_checks(validated, gate.range_checks, timestamp_col)
    if range_violations:
        violation_index = pd.Index([])
        for payload in range_violations.values():
            violation_index = violation_index.union(payload.index)
        combined_range = (
            pd.concat(range_violations.values(), axis=0)
            .reset_index(drop=True)
            .loc[:, validated.columns]
            .drop_duplicates()
        )
        if not clean.empty:
            clean = (
                clean.set_index(timestamp_col)
                .drop(index=violation_index, errors="ignore")
                .reset_index()
            )
        combined_range_indexed = combined_range.set_index(timestamp_col)
        if not quarantined.empty:
            quarantined = (
                pd.concat(
                    [quarantined.set_index(timestamp_col), combined_range_indexed],
                    axis=0,
                )
                .drop_duplicates()
                .reset_index()
            )
        else:
            quarantined = combined_range_indexed.reset_index()
    contract_breaches: Tuple[str, ...] = tuple()
    contract_block = False
    if gate.temporal_contract is not None:
        contract_breaches, contract_block = _enforce_temporal_contract(
            validated[timestamp_col], gate.temporal_contract
        )

    blocked = contract_block or bool(range_violations)
    total_rows = max(validated.shape[0], 1)
    if not blocked and not quarantined.empty:
        ratio = quarantined.shape[0] / total_rows
        if ratio > float(gate.max_quarantine_fraction):
            blocked = True

    report = QualityReport(
        clean=clean,
        quarantined=quarantined,
        duplicates=duplicates.reset_index(drop=True),
        spikes=buckets["spikes"].reset_index(),
        range_violations=range_violations,
        contract_breaches=contract_breaches,
        blocked=blocked,
    )
    return report


__all__ = [
    "QualityGateConfig",
    "QualityGateError",
    "QualityReport",
    "QualitySummary",
    "RangeCheck",
    "TemporalContract",
    "ValidatorOutcome",
    "quarantine_anomalies",
    "summarise_quality",
    "validate_and_quarantine",
]

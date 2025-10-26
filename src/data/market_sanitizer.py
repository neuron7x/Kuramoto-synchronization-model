"""Market data sanitisation utilities for ingestion pipelines.

The :class:`MarketDataSanitizer` enforces defensive checks before ticks enter
the shared ingestion cache.  It normalises structural fields (timestamps,
symbols, venues), detects statistical anomalies, monitors temporal integrity
and records provenance metadata so downstream systems can reason about data
quality decisions.  Suppliers that repeatedly violate the guard rails are
automatically quarantined to prevent cascading corruption.

The implementation intentionally favours transparency over opacity: every
decision is captured as a :class:`SanitizationIssue` with rich metadata so that
SRE and quant teams can audit sanitisation runs post-factum.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum, auto
from typing import Any, Callable, Mapping, MutableMapping, Sequence

import pandas as pd

from core.data.catalog import normalize_symbol, normalize_venue

from .versioning import LineageRecord

__all__ = [
    "MarketDataSanitizer",
    "SanitizationIssue",
    "SanitizationIssueKind",
    "SanitizedTickBatch",
]


def _as_timezone(value: datetime, target: timezone) -> datetime:
    """Normalise ``value`` to *target* timezone."""

    if value.tzinfo is None:
        return value.replace(tzinfo=target)
    return value.astimezone(target)


class SanitizationIssueKind(Enum):
    """Categorise data quality problems detected during sanitisation."""

    OUTLIER = auto()
    STALE_TICK = auto()
    GAP = auto()
    OVERLAP = auto()
    SUPPLIER_QUARANTINED = auto()


@dataclass(frozen=True, slots=True)
class SanitizationIssue:
    """Describe a single problem discovered while sanitising market data."""

    kind: SanitizationIssueKind
    message: str
    index: int | None = None
    supplier: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SanitizedTickBatch:
    """Result bundle returned by :class:`MarketDataSanitizer.sanitize`."""

    data: pd.DataFrame
    dropped: pd.DataFrame
    issues: tuple[SanitizationIssue, ...]
    checksum: str
    lineage: LineageRecord
    quarantined_suppliers: frozenset[str]


class MarketDataSanitizer:
    """Cleanse and annotate raw tick frames prior to persistence."""

    def __init__(
        self,
        *,
        symbol_aliases: Mapping[str, str] | None = None,
        target_timezone: timezone = timezone.utc,
        price_mad_threshold: float = 6.0,
        max_staleness: timedelta | None = timedelta(seconds=5),
        expected_frequency: pd.Timedelta | None = None,
        gap_tolerance: pd.Timedelta | None = None,
        overlap_tolerance: pd.Timedelta | None = None,
        quarantine_threshold: int = 10,
        checksum_factory: Callable[[pd.DataFrame], str] | None = None,
        clock: Callable[[], datetime] | None = None,
        created_by: str = "market-data-sanitizer",
    ) -> None:
        if price_mad_threshold <= 0:
            raise ValueError("price_mad_threshold must be positive")
        if quarantine_threshold <= 0:
            raise ValueError("quarantine_threshold must be positive")

        self._symbol_aliases = {k.upper(): v for k, v in (symbol_aliases or {}).items()}
        self._timezone = target_timezone
        self._price_threshold = price_mad_threshold
        self._max_staleness = max_staleness
        self._expected_frequency = expected_frequency
        self._gap_tolerance = gap_tolerance or pd.Timedelta(0)
        self._overlap_tolerance = overlap_tolerance or pd.Timedelta(0)
        self._quarantine_threshold = quarantine_threshold
        self._checksum_factory = checksum_factory or self._default_checksum
        tz = self._timezone
        self._clock = clock or (lambda: datetime.now(tz))
        self._created_by = created_by
        self._supplier_issue_counts: MutableMapping[str, int] = {}
        self._quarantined_suppliers: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    def sanitize(
        self,
        frame: pd.DataFrame,
        *,
        ingestion_time: datetime | None = None,
        parent_versions: Sequence[str] | None = None,
    ) -> SanitizedTickBatch:
        """Return a sanitised copy of ``frame`` and capture integrity metadata."""

        if frame.empty:
            empty = frame.copy()
            checksum = self._checksum_factory(empty)
            lineage = self._build_lineage(checksum, parent_versions)
            return SanitizedTickBatch(
                data=empty,
                dropped=empty,
                issues=(),
                checksum=checksum,
                lineage=lineage,
                quarantined_suppliers=frozenset(self._quarantined_suppliers),
            )

        working = frame.copy(deep=True)
        required_columns = {"timestamp", "price", "symbol", "venue"}
        missing = required_columns - set(working.columns)
        if missing:
            missing_cols = ", ".join(sorted(missing))
            raise ValueError(f"frame is missing required columns: {missing_cols}")

        ingestion_ts = _as_timezone(
            ingestion_time or self._clock(),
            self._timezone,
        )

        issues: list[SanitizationIssue] = []
        drop_mask = pd.Series(False, index=working.index, dtype=bool)

        # ------------------------------------------------------------------
        # Structural normalisation
        working["timestamp"] = self._normalise_timestamps(working["timestamp"])
        working.sort_values("timestamp", inplace=True)
        working.reset_index(drop=True, inplace=True)
        drop_mask = pd.Series(False, index=working.index, dtype=bool)

        instrument_type_hint = None
        if "instrument_type" in working.columns:
            unique_values = working["instrument_type"].dropna().unique()
            if len(unique_values) == 1:
                instrument_type_hint = unique_values[0]
        working["symbol"] = working["symbol"].map(
            lambda value: self._canonical_symbol(value, instrument_type_hint)
        )
        working["venue"] = working["venue"].map(normalize_venue)

        numeric_columns = [col for col in ("price", "volume") if col in working.columns]
        for column in numeric_columns:
            coerced = pd.to_numeric(working[column], errors="coerce")
            if coerced.isna().any():
                raise ValueError(f"{column} column contains non-numeric values")
            working[column] = coerced.astype(float)

        # ------------------------------------------------------------------
        # Detect stale ticks
        if self._max_staleness is not None:
            staleness = ingestion_ts - working["timestamp"]
            stale_mask = staleness > self._max_staleness
            for idx in working.index[stale_mask]:
                issues.append(
                    self._build_issue(
                        SanitizationIssueKind.STALE_TICK,
                        idx,
                        working,
                        message="tick timestamp is older than allowed staleness",
                    )
                )
            drop_mask |= stale_mask

        # ------------------------------------------------------------------
        # Detect price outliers (robust MAD estimator)
        prices = working.loc[~drop_mask, "price"].astype(float)
        if not prices.empty:
            median = float(prices.median())
            deviations = (prices - median).abs()
            mad = float(deviations.median())
            if mad == 0.0:
                mad = float(prices.std(ddof=0))
            if mad > 0.0:
                scaled = deviations / (mad * 1.4826)
                outlier_mask = scaled > self._price_threshold
                outliers = prices.index[outlier_mask]
                for idx in outliers:
                    issues.append(
                        self._build_issue(
                            SanitizationIssueKind.OUTLIER,
                            idx,
                            working,
                            message="price outlier detected via MAD threshold",
                            metadata={
                                "price": float(working.at[idx, "price"]),
                                "median": median,
                                "threshold": self._price_threshold,
                            },
                        )
                    )
                drop_mask.loc[outliers] = True

        # ------------------------------------------------------------------
        # Detect overlaps (non-monotonic timestamps)
        diffs = working["timestamp"].diff()
        overlap_mask = (diffs <= -self._overlap_tolerance).fillna(False)
        if overlap_mask.any():
            overlapping_rows = working.index[overlap_mask]
            for idx in overlapping_rows:
                issues.append(
                    self._build_issue(
                        SanitizationIssueKind.OVERLAP,
                        idx,
                        working,
                        message="timestamp overlaps or moves backwards",
                    )
                )
            drop_mask |= overlap_mask

        # ------------------------------------------------------------------
        # Detect suspicious gaps (but keep the data)
        gap_reports = self._detect_gaps(working, drop_mask)
        issues.extend(gap_reports)

        dropped = working.loc[drop_mask].copy()
        cleaned = working.loc[~drop_mask].copy()

        # Enforce supplier quarantine
        quarantined_issues = self._update_quarantine(issues)
        if quarantined_issues:
            issues.extend(quarantined_issues)
        if self._quarantined_suppliers and "supplier" in cleaned.columns:
            quarantine_mask = cleaned["supplier"].isin(self._quarantined_suppliers)
            if quarantine_mask.any():
                affected_suppliers = (
                    cleaned.loc[quarantine_mask, "supplier"].dropna().unique().tolist()
                )
                for supplier in affected_suppliers:
                    issues.append(
                        SanitizationIssue(
                            kind=SanitizationIssueKind.SUPPLIER_QUARANTINED,
                            message="supplier remains quarantined; dropping incoming data",
                            index=None,
                            supplier=str(supplier),
                            metadata={"issue_count": self._supplier_issue_counts.get(str(supplier), 0)},
                        )
                    )
                quarantined_rows = cleaned.loc[quarantine_mask].copy()
                dropped = pd.concat([dropped, quarantined_rows], ignore_index=True)
                cleaned = cleaned.loc[~quarantine_mask].copy()

        cleaned.sort_values("timestamp", inplace=True)
        cleaned.reset_index(drop=True, inplace=True)

        checksum = self._checksum_factory(cleaned)
        lineage = self._build_lineage(checksum, parent_versions)

        return SanitizedTickBatch(
            data=cleaned,
            dropped=dropped.reset_index(drop=True),
            issues=tuple(issues),
            checksum=checksum,
            lineage=lineage,
            quarantined_suppliers=frozenset(self._quarantined_suppliers),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    def _normalise_timestamps(self, series: pd.Series) -> pd.Series:
        converted = pd.to_datetime(series, utc=True, errors="coerce")
        if converted.isna().any():
            raise ValueError("timestamp column contains invalid values")
        converted = converted.dt.tz_convert(self._timezone)
        return converted

    def _canonical_symbol(self, value: Any, instrument_type_hint: Any | None) -> str:
        if not isinstance(value, str):
            raise ValueError("symbol column must contain strings")
        upper = value.strip().upper()
        mapped = self._symbol_aliases.get(upper, upper)
        return normalize_symbol(mapped, instrument_type_hint=instrument_type_hint)

    def _build_issue(
        self,
        kind: SanitizationIssueKind,
        index: int,
        frame: pd.DataFrame,
        *,
        message: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> SanitizationIssue:
        supplier = frame.at[index, "supplier"] if "supplier" in frame.columns else None
        payload = dict(metadata or {})
        payload.setdefault("timestamp", frame.at[index, "timestamp"].isoformat())
        return SanitizationIssue(
            kind=kind,
            message=message,
            index=int(index),
            supplier=supplier,
            metadata=payload,
        )

    def _detect_gaps(
        self,
        frame: pd.DataFrame,
        drop_mask: pd.Series,
    ) -> list[SanitizationIssue]:
        candidates = frame.loc[~drop_mask, "timestamp"].diff().dropna()
        if candidates.empty:
            return []

        positive = candidates[candidates > pd.Timedelta(0)]
        if positive.empty:
            return []

        baseline = self._expected_frequency or positive.median()
        if pd.isna(baseline) or baseline <= pd.Timedelta(0):
            baseline = None

        threshold = None
        if baseline is not None:
            threshold = baseline + self._gap_tolerance
        elif self._gap_tolerance > pd.Timedelta(0):
            threshold = self._gap_tolerance

        if threshold is None:
            return []

        gaps = positive[positive > threshold]
        issues: list[SanitizationIssue] = []
        for idx in gaps.index:
            metadata = {"gap": gaps.loc[idx].total_seconds(), "threshold": threshold.total_seconds()}
            issues.append(
                SanitizationIssue(
                    kind=SanitizationIssueKind.GAP,
                    message="timestamp gap exceeds tolerance",
                    index=int(idx),
                    supplier=None,
                    metadata=metadata,
                )
            )
        return issues

    def _update_quarantine(
        self,
        issues: Sequence[SanitizationIssue],
    ) -> list[SanitizationIssue]:
        new_issues: list[SanitizationIssue] = []
        for issue in issues:
            if issue.supplier is None:
                continue
            count = self._supplier_issue_counts.get(issue.supplier, 0) + 1
            self._supplier_issue_counts[issue.supplier] = count
            if count >= self._quarantine_threshold and issue.supplier not in self._quarantined_suppliers:
                self._quarantined_suppliers.add(issue.supplier)
                new_issues.append(
                    SanitizationIssue(
                        kind=SanitizationIssueKind.SUPPLIER_QUARANTINED,
                        message="supplier quarantined after repeated data quality failures",
                        index=None,
                        supplier=issue.supplier,
                        metadata={"issue_count": count},
                    )
                )
        return new_issues

    def _default_checksum(self, frame: pd.DataFrame) -> str:
        ordered = frame.sort_index(axis=1)
        payload = ordered.to_json(date_unit="ns", orient="split", index=False).encode("utf-8")
        import hashlib

        return hashlib.sha256(payload).hexdigest()

    def _build_lineage(
        self,
        checksum: str,
        parent_versions: Sequence[str] | None,
    ) -> LineageRecord:
        parents = tuple(parent_versions or ())
        return LineageRecord(
            parent_versions=parents,
            data_fingerprint=checksum,
            created_by=self._created_by,
        )


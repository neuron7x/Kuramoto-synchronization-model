# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""
Data Pipeline & Quality Assurance Automation

Autonomous data pipeline that:
- Auto-validates and cleans incoming data
- Implements intelligent retry mechanisms
- Processes dead letter queues automatically
- Ensures data quality without human intervention
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


class DataQualityLevel(str, Enum):
    """Data quality assessment levels."""
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    UNACCEPTABLE = "unacceptable"


@dataclass
class DataQualityMetrics:
    """Metrics for data quality assessment."""
    
    completeness: float  # Percentage of non-null values
    consistency: float  # Consistency with expected patterns
    timeliness: float  # Data freshness score
    accuracy: float  # Data accuracy score
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @property
    def overall_quality(self) -> float:
        """Calculate overall quality score."""
        return (self.completeness + self.consistency + self.timeliness + self.accuracy) / 4.0
    
    @property
    def quality_level(self) -> DataQualityLevel:
        """Determine quality level."""
        score = self.overall_quality
        if score >= 0.95:
            return DataQualityLevel.EXCELLENT
        elif score >= 0.85:
            return DataQualityLevel.GOOD
        elif score >= 0.70:
            return DataQualityLevel.ACCEPTABLE
        elif score >= 0.50:
            return DataQualityLevel.POOR
        else:
            return DataQualityLevel.UNACCEPTABLE


@dataclass
class DataRecord:
    """Represents a data record in the pipeline."""
    
    data: Any
    source: str
    timestamp: datetime
    retry_count: int = 0
    validation_errors: List[str] = field(default_factory=list)
    quality_metrics: Optional[DataQualityMetrics] = None


@dataclass
class PipelineStats:
    """Statistics for data pipeline operations."""
    
    total_processed: int = 0
    successful: int = 0
    failed: int = 0
    retried: int = 0
    auto_cleaned: int = 0
    dlq_processed: int = 0
    avg_quality_score: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class DataPipelineAutomation:
    """
    Autonomous data pipeline automation system.
    
    Features:
    1. Automatic data validation and cleaning
    2. Intelligent retry mechanisms with exponential backoff
    3. Dead letter queue automatic processing
    4. Real-time quality monitoring
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        dlq_max_size: int = 10000,
        auto_clean: bool = True,
        quality_threshold: float = 0.7,
    ):
        """
        Initialize data pipeline automation.
        
        Args:
            max_retries: Maximum retry attempts for failed records
            dlq_max_size: Maximum size of dead letter queue
            auto_clean: Whether to automatically clean data
            quality_threshold: Minimum acceptable quality score
        """
        self.max_retries = max_retries
        self.dlq_max_size = dlq_max_size
        self.auto_clean = auto_clean
        self.quality_threshold = quality_threshold
        
        self._dlq: Deque[DataRecord] = deque(maxlen=dlq_max_size)
        self._stats = PipelineStats()
        self._quality_history: List[DataQualityMetrics] = []
        
    async def process_data(
        self,
        data: Any,
        source: str,
        validator: Optional[Callable[[Any], bool]] = None,
    ) -> Optional[Any]:
        """
        Process data through the pipeline with automatic validation and retry.
        
        Args:
            data: Raw data to process
            source: Data source identifier
            validator: Optional custom validator function
            
        Returns:
            Processed data or None if failed
        """
        record = DataRecord(
            data=data,
            source=source,
            timestamp=datetime.now(timezone.utc),
        )
        
        self._stats.total_processed += 1
        
        # Step 1: Validate data
        if not await self._validate_data(record, validator):
            if record.retry_count < self.max_retries:
                return await self._retry_processing(record, validator)
            else:
                self._add_to_dlq(record)
                self._stats.failed += 1
                return None
        
        # Step 2: Clean data if enabled
        if self.auto_clean:
            cleaned_data = await self._auto_clean_data(record.data)
            if cleaned_data is not None:
                record.data = cleaned_data
                self._stats.auto_cleaned += 1
        
        # Step 3: Assess quality
        quality_metrics = await self._assess_quality(record.data)
        record.quality_metrics = quality_metrics
        self._quality_history.append(quality_metrics)
        
        # Step 4: Check quality threshold
        if quality_metrics.overall_quality < self.quality_threshold:
            logger.warning(
                f"Data quality below threshold: {quality_metrics.overall_quality:.2f} "
                f"< {self.quality_threshold}"
            )
            if record.retry_count < self.max_retries:
                return await self._retry_processing(record, validator)
            else:
                self._add_to_dlq(record)
                self._stats.failed += 1
                return None
        
        self._stats.successful += 1
        return record.data
    
    async def _validate_data(
        self,
        record: DataRecord,
        validator: Optional[Callable[[Any], bool]],
    ) -> bool:
        """Validate data record."""
        try:
            # Basic validation
            if record.data is None:
                record.validation_errors.append("Data is None")
                return False
            
            # DataFrame-specific validation
            if isinstance(record.data, pd.DataFrame):
                if record.data.empty:
                    record.validation_errors.append("DataFrame is empty")
                    return False
                
                # Check for required columns
                if hasattr(record.data, 'columns'):
                    required_cols = {'close', 'volume'}  # Example required columns
                    missing = required_cols - set(record.data.columns)
                    if missing and len(record.data.columns) > 0:
                        # Only warn if there are columns but missing required ones
                        logger.debug(f"Missing columns in DataFrame: {missing}")
            
            # Custom validator
            if validator is not None:
                if not validator(record.data):
                    record.validation_errors.append("Custom validation failed")
                    return False
            
            return True
            
        except Exception as e:
            record.validation_errors.append(f"Validation error: {e}")
            logger.error(f"Data validation failed for {record.source}: {e}")
            return False
    
    async def _auto_clean_data(self, data: Any) -> Optional[Any]:
        """Automatically clean data."""
        try:
            if isinstance(data, pd.DataFrame):
                cleaned = data.copy()
                
                # Remove duplicate rows
                cleaned = cleaned.drop_duplicates()
                
                # Fill missing values with forward fill
                cleaned = cleaned.fillna(method='ffill')
                
                # Remove infinite values
                cleaned = cleaned.replace([float('inf'), float('-inf')], pd.NA)
                cleaned = cleaned.fillna(method='bfill')
                
                return cleaned
            
            return data
            
        except Exception as e:
            logger.error(f"Auto-clean failed: {e}")
            return None
    
    async def _assess_quality(self, data: Any) -> DataQualityMetrics:
        """Assess data quality."""
        try:
            if isinstance(data, pd.DataFrame):
                # Completeness: percentage of non-null values
                completeness = 1.0 - data.isnull().sum().sum() / (data.shape[0] * data.shape[1])
                
                # Consistency: check for reasonable value ranges
                consistency = 1.0  # Default to perfect
                if 'close' in data.columns:
                    # Check for negative prices
                    if (data['close'] < 0).any():
                        consistency -= 0.3
                
                # Timeliness: check data freshness
                timeliness = 1.0
                if hasattr(data, 'index') and isinstance(data.index, pd.DatetimeIndex):
                    if len(data.index) > 0:
                        latest_time = data.index[-1]
                        age_hours = (datetime.now(timezone.utc) - latest_time.tz_localize(timezone.utc)).total_seconds() / 3600
                        if age_hours > 24:
                            timeliness = max(0.0, 1.0 - (age_hours - 24) / 168)  # Decay over a week
                
                # Accuracy: detect outliers
                accuracy = 1.0
                for col in data.select_dtypes(include=[float, int]).columns:
                    q1 = data[col].quantile(0.25)
                    q3 = data[col].quantile(0.75)
                    iqr = q3 - q1
                    outliers = ((data[col] < (q1 - 3 * iqr)) | (data[col] > (q3 + 3 * iqr))).sum()
                    outlier_ratio = outliers / len(data)
                    if outlier_ratio > 0.05:
                        accuracy -= min(0.3, outlier_ratio)
                
                return DataQualityMetrics(
                    completeness=max(0.0, min(1.0, completeness)),
                    consistency=max(0.0, min(1.0, consistency)),
                    timeliness=max(0.0, min(1.0, timeliness)),
                    accuracy=max(0.0, min(1.0, accuracy)),
                )
            
            # Default metrics for non-DataFrame data
            return DataQualityMetrics(
                completeness=1.0,
                consistency=1.0,
                timeliness=1.0,
                accuracy=1.0,
            )
            
        except Exception as e:
            logger.error(f"Quality assessment failed: {e}")
            return DataQualityMetrics(
                completeness=0.0,
                consistency=0.0,
                timeliness=0.0,
                accuracy=0.0,
            )
    
    async def _retry_processing(
        self,
        record: DataRecord,
        validator: Optional[Callable[[Any], bool]],
    ) -> Optional[Any]:
        """Retry processing with exponential backoff."""
        record.retry_count += 1
        self._stats.retried += 1
        
        # Exponential backoff
        wait_time = 2 ** record.retry_count
        logger.info(f"Retrying data processing for {record.source}, attempt {record.retry_count}/{self.max_retries}")
        
        await asyncio.sleep(min(wait_time, 60))  # Cap at 60 seconds
        
        return await self.process_data(record.data, record.source, validator)
    
    def _add_to_dlq(self, record: DataRecord) -> None:
        """Add failed record to dead letter queue."""
        self._dlq.append(record)
        logger.warning(f"Added record from {record.source} to DLQ. Errors: {record.validation_errors}")
    
    async def process_dlq(self) -> int:
        """
        Process dead letter queue automatically.
        
        Returns:
            Number of records successfully recovered
        """
        recovered = 0
        failed = []
        
        while self._dlq:
            record = self._dlq.popleft()
            
            # Reset retry count for DLQ processing
            record.retry_count = 0
            record.validation_errors = []
            
            result = await self.process_data(record.data, f"{record.source}_dlq", None)
            
            if result is not None:
                recovered += 1
                self._stats.dlq_processed += 1
            else:
                # Failed again, add back to DLQ
                failed.append(record)
        
        # Add failed records back to DLQ
        self._dlq.extend(failed)
        
        if recovered > 0:
            logger.info(f"DLQ processing: recovered {recovered} records, {len(failed)} still failed")
        
        return recovered
    
    def get_stats(self) -> Dict[str, Any]:
        """Get current pipeline statistics."""
        avg_quality = 0.0
        if self._quality_history:
            avg_quality = sum(m.overall_quality for m in self._quality_history[-100:]) / min(len(self._quality_history), 100)
        
        success_rate = 0.0
        if self._stats.total_processed > 0:
            success_rate = self._stats.successful / self._stats.total_processed
        
        return {
            "total_processed": self._stats.total_processed,
            "successful": self._stats.successful,
            "failed": self._stats.failed,
            "retried": self._stats.retried,
            "auto_cleaned": self._stats.auto_cleaned,
            "dlq_processed": self._stats.dlq_processed,
            "dlq_size": len(self._dlq),
            "success_rate": success_rate,
            "avg_quality_score": avg_quality,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Get pipeline health status."""
        stats = self.get_stats()
        
        status = "healthy"
        if stats["success_rate"] < 0.9:
            status = "degraded"
        if stats["success_rate"] < 0.7 or stats["dlq_size"] > self.dlq_max_size * 0.8:
            status = "critical"
        
        return {
            "status": status,
            "success_rate": stats["success_rate"],
            "avg_quality": stats["avg_quality_score"],
            "dlq_size": stats["dlq_size"],
            "dlq_capacity": f"{(stats['dlq_size'] / self.dlq_max_size) * 100:.1f}%",
        }


__all__ = [
    "DataPipelineAutomation",
    "DataQualityLevel",
    "DataQualityMetrics",
    "DataRecord",
    "PipelineStats",
]

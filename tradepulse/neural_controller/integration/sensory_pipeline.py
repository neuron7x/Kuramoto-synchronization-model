from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict

from ..core.params import PredictiveConfig, SensoryConfig, TemporalGatingConfig
from ..core.predictive import PredictiveCoder, PredictiveState
from ..core.sensory import SensoryFilter
from ..core.sensory_schema import SCHEMA_VERSION, SensorySchema
from ..core.temporal_gater import TemporalGater

log = logging.getLogger(__name__)


@dataclass
class SensoryPipelineResult:
    prediction_error: float
    timing_sensory_ms: float
    timing_predictive_ms: float
    predictive_state: PredictiveState | None


class SensoryPipeline:
    """Pipeline for sensory normalization, filtering, and prediction error."""

    def __init__(
        self,
        *,
        sensory: SensoryConfig | None = None,
        sensory_schema: SensorySchema | None = None,
        predictive: PredictiveConfig | None = None,
        temporal_gating: TemporalGatingConfig | None = None,
    ) -> None:
        self.sensory = SensoryFilter(sensory or SensoryConfig())
        self.sensory_schema = sensory_schema or SensorySchema.default()
        self.predictive = PredictiveCoder(predictive or PredictiveConfig())
        gating_cfg = temporal_gating or TemporalGatingConfig()
        self.sensory_gater = TemporalGater(
            frequency=gating_cfg.sensory_frequency,
            cadence=gating_cfg.cadence,
            ema_alpha=gating_cfg.ema_alpha,
        )
        self.predictive_gater = TemporalGater(
            frequency=gating_cfg.predictive_frequency,
            cadence=gating_cfg.cadence,
            ema_alpha=gating_cfg.ema_alpha,
        )
        self._last_prediction_error = 0.0
        self._last_predictive_state: PredictiveState | None = None

    @property
    def last_prediction_error(self) -> float:
        return self._last_prediction_error

    @property
    def last_predictive_state(self) -> PredictiveState | None:
        return self._last_predictive_state

    def snapshot(self) -> PredictiveState:
        return self.predictive.snapshot()

    def _validate_schema_metadata(
        self,
        schema_version: int | None,
        expected_fields: object,
    ) -> None:
        if schema_version is not None and schema_version != SCHEMA_VERSION:
            log.critical(
                "Sensory schema version mismatch",  # noqa: TRY400 - structured logging
                extra={
                    "event": "neuro.schema_version_mismatch",
                    "schema_version": schema_version,
                    "expected": SCHEMA_VERSION,
                },
            )
            raise ValueError(
                "Unsupported sensory schema version "
                f"{schema_version!r}; expected {SCHEMA_VERSION}."
            )
        if expected_fields is None:
            return
        if not isinstance(expected_fields, (list, tuple, set)):
            log.critical(
                "Sensory schema fields metadata is invalid",
                extra={
                    "event": "neuro.schema_fields_invalid",
                    "expected_fields": expected_fields,
                },
            )
            raise ValueError("Sensory schema expected_fields must be a collection.")
        expected = tuple(expected_fields)
        schema_fields = {channel.name for channel in self.sensory_schema.channels}
        if set(expected) != schema_fields:
            log.critical(
                "Sensory schema fields mismatch",
                extra={
                    "event": "neuro.schema_fields_mismatch",
                    "expected_fields": expected,
                    "schema_fields": sorted(schema_fields),
                },
            )
            raise ValueError(
                "Sensory schema fields mismatch "
                f"{expected!r}; expected {sorted(schema_fields)!r}."
            )

    def _compute_prediction_error(self, obs: Dict[str, float]) -> float:
        state = self.predictive.step(obs)
        self._last_predictive_state = state
        if not state.error:
            return 0.0
        magnitude = sum(abs(v) for v in state.error.values()) / len(state.error)
        return self.predictive.cfg.error_gain * magnitude

    def apply(
        self,
        obs: Dict[str, Any],
        *,
        schema_version: int | None = None,
        expected_fields: object = None,
    ) -> SensoryPipelineResult:
        self._validate_schema_metadata(schema_version, expected_fields)
        start = time.perf_counter()
        schema_output = self.sensory_schema.validate(obs)
        sensory_filtered, _ = self.sensory_gater.step(
            lambda: self.sensory.transform(schema_output).filtered
        )
        timing_sensory_ms = (time.perf_counter() - start) * 1000.0
        obs.update(schema_output.normalized)
        obs["sensory_confidence"] = schema_output.sensory_confidence
        obs.update(sensory_filtered)

        start = time.perf_counter()
        prediction_error, _ = self.predictive_gater.step(
            lambda: self._compute_prediction_error(obs)
        )
        self._last_prediction_error = float(prediction_error)
        timing_predictive_ms = (time.perf_counter() - start) * 1000.0
        obs["prediction_error"] = float(prediction_error)

        return SensoryPipelineResult(
            prediction_error=float(prediction_error),
            timing_sensory_ms=timing_sensory_ms,
            timing_predictive_ms=timing_predictive_ms,
            predictive_state=self._last_predictive_state,
        )

"""Serotonin tonic/phasic controller with hysteresis driven hold logic."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional

import yaml


@dataclass(frozen=True)
class SerotoninConfig:
    """Configuration container for :class:`SerotoninController`."""

    tonic_beta: float
    phasic_beta: float
    stress_gain: float
    drawdown_gain: float
    novelty_gain: float
    stress_threshold: float
    release_threshold: float
    hysteresis: float
    cooldown_ticks: int
    chronic_window: int
    desensitization_rate: float
    desensitization_decay: float
    max_desensitization: float
    floor_min: float
    floor_max: float
    floor_gain: float
    cooldown_extension: int

    def to_dict(self) -> Dict[str, float | int]:
        return {
            "tonic_beta": self.tonic_beta,
            "phasic_beta": self.phasic_beta,
            "stress_gain": self.stress_gain,
            "drawdown_gain": self.drawdown_gain,
            "novelty_gain": self.novelty_gain,
            "stress_threshold": self.stress_threshold,
            "release_threshold": self.release_threshold,
            "hysteresis": self.hysteresis,
            "cooldown_ticks": self.cooldown_ticks,
            "chronic_window": self.chronic_window,
            "desensitization_rate": self.desensitization_rate,
            "desensitization_decay": self.desensitization_decay,
            "max_desensitization": self.max_desensitization,
            "floor_min": self.floor_min,
            "floor_max": self.floor_max,
            "floor_gain": self.floor_gain,
            "cooldown_extension": self.cooldown_extension,
        }


def _ensure_float(
    name: str,
    value: object,
    *,
    min_value: Optional[float] = None,
    max_value: Optional[float] = None,
) -> float:
    if not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if min_value is not None and result < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    if max_value is not None and result > max_value:
        raise ValueError(f"{name} must be <= {max_value}")
    return result


def _ensure_int(name: str, value: object, *, min_value: Optional[int] = None) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}")
    return value


class SerotoninController:
    """Model chronic serotonin dynamics with hysteretic hold decisions."""

    def __init__(
        self,
        config_path: str = "configs/serotonin.yaml",
        logger: Optional[Callable[[str, float], None]] = None,
        *,
        enable_performance_tracking: bool = False,
    ) -> None:
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(path)
        with path.open("r", encoding="utf-8") as handle:
            raw_cfg = yaml.safe_load(handle)
        self._config = self._validate_config(raw_cfg or {})
        self.config_path = str(path)
        self._logger = logger or (lambda name, value: None)

        # dynamic state
        self.tonic_level = 0.0
        self.phasic_level = 0.0
        self.level = 0.0
        self._hold = False
        self._cooldown = 0
        self._chronic_ticks = 0
        self._desensitization = 0.0
        self.temperature_floor = self._config.floor_min

        # performance tracking (optional)
        self._enable_perf_tracking = enable_performance_tracking
        self._step_count = 0
        self._total_step_time = 0.0
        self._hold_count = 0

    # ------------------------------------------------------------------ utils
    def _log(self, name: str, value: float) -> None:
        try:
            self._logger(name, float(value))
        except Exception:  # pragma: no cover - defensive
            pass

    def _validate_config(self, raw: Mapping[str, object]) -> SerotoninConfig:
        required_keys = {
            "tonic_beta",
            "phasic_beta",
            "stress_gain",
            "drawdown_gain",
            "novelty_gain",
            "stress_threshold",
            "release_threshold",
            "hysteresis",
            "cooldown_ticks",
            "chronic_window",
            "desensitization_rate",
            "desensitization_decay",
            "max_desensitization",
            "floor_min",
            "floor_max",
            "floor_gain",
            "cooldown_extension",
        }
        missing = required_keys - set(raw.keys())
        if missing:
            raise ValueError(f"Missing serotonin config keys: {sorted(missing)}")
        tonic_beta = _ensure_float(
            "tonic_beta", raw["tonic_beta"], min_value=0.0, max_value=1.0
        )
        phasic_beta = _ensure_float(
            "phasic_beta", raw["phasic_beta"], min_value=0.0, max_value=1.0
        )
        stress_gain = _ensure_float("stress_gain", raw["stress_gain"], min_value=0.0)
        drawdown_gain = _ensure_float(
            "drawdown_gain", raw["drawdown_gain"], min_value=0.0
        )
        novelty_gain = _ensure_float("novelty_gain", raw["novelty_gain"], min_value=0.0)
        stress_threshold = _ensure_float(
            "stress_threshold", raw["stress_threshold"], min_value=0.0, max_value=1.5
        )
        release_threshold = _ensure_float(
            "release_threshold",
            raw["release_threshold"],
            min_value=0.0,
            max_value=stress_threshold,
        )
        hysteresis = _ensure_float(
            "hysteresis", raw["hysteresis"], min_value=0.0, max_value=1.0
        )
        cooldown_ticks = _ensure_int(
            "cooldown_ticks", raw["cooldown_ticks"], min_value=0
        )
        chronic_window = _ensure_int(
            "chronic_window", raw["chronic_window"], min_value=1
        )
        desensitization_rate = _ensure_float(
            "desensitization_rate", raw["desensitization_rate"], min_value=0.0
        )
        desensitization_decay = _ensure_float(
            "desensitization_decay",
            raw["desensitization_decay"],
            min_value=0.0,
            max_value=1.0,
        )
        max_desensitization = _ensure_float(
            "max_desensitization",
            raw["max_desensitization"],
            min_value=0.0,
            max_value=0.99,
        )
        floor_min = _ensure_float(
            "floor_min", raw["floor_min"], min_value=0.0, max_value=1.0
        )
        floor_max = _ensure_float(
            "floor_max", raw["floor_max"], min_value=floor_min, max_value=1.0
        )
        floor_gain = _ensure_float(
            "floor_gain", raw["floor_gain"], min_value=0.0, max_value=4.0
        )
        cooldown_extension = _ensure_int(
            "cooldown_extension", raw["cooldown_extension"], min_value=0
        )
        return SerotoninConfig(
            tonic_beta=tonic_beta,
            phasic_beta=phasic_beta,
            stress_gain=stress_gain,
            drawdown_gain=drawdown_gain,
            novelty_gain=novelty_gain,
            stress_threshold=stress_threshold,
            release_threshold=release_threshold,
            hysteresis=hysteresis,
            cooldown_ticks=cooldown_ticks,
            chronic_window=chronic_window,
            desensitization_rate=desensitization_rate,
            desensitization_decay=desensitization_decay,
            max_desensitization=max_desensitization,
            floor_min=floor_min,
            floor_max=floor_max,
            floor_gain=floor_gain,
            cooldown_extension=cooldown_extension,
        )

    # ----------------------------------------------------------------- helpers
    def reset(self) -> None:
        """Reset controller to initial state."""
        self.tonic_level = 0.0
        self.phasic_level = 0.0
        self.level = 0.0
        self._hold = False
        self._cooldown = 0
        self._chronic_ticks = 0
        self._desensitization = 0.0
        self.temperature_floor = self._config.floor_min

    def step_batch(
        self,
        stress_sequence: list[float],
        drawdown_sequence: list[float],
        novelty_sequence: list[float],
        *,
        dt: float = 1.0,
    ) -> list[Mapping[str, float]]:
        """Process multiple steps efficiently in batch.

        More efficient than calling step() in a loop when processing
        historical data or running simulations.

        Args:
            stress_sequence: Sequence of stress values
            drawdown_sequence: Sequence of drawdown values
            novelty_sequence: Sequence of novelty values
            dt: Time delta for each step

        Returns:
            List of result dictionaries, one per step
        """
        if not (
            len(stress_sequence) == len(drawdown_sequence) == len(novelty_sequence)
        ):
            raise ValueError("All input sequences must have the same length")

        results = []
        for stress, drawdown, novelty in zip(
            stress_sequence, drawdown_sequence, novelty_sequence
        ):
            result = self.step(stress, drawdown, novelty, dt=dt)
            results.append(result)

        return results

    # ------------------------------------------------------------------- state
    @property
    def hold(self) -> bool:
        # Hold is True if in active hold state OR in cooldown period after exiting hold
        return self._hold or self._cooldown > 0

    def check_cooldown(self, serotonin_signal: Optional[float] = None) -> bool:
        if serotonin_signal is not None:
            self.level = float(max(0.0, min(1.5, serotonin_signal)))
            cfg = self._config
            threshold = cfg.stress_threshold
            # Apply hysteresis to check_cooldown as well
            if self._hold:
                # Use release threshold minus hysteresis to exit
                exit_threshold = max(0.0, cfg.release_threshold) - cfg.hysteresis / 2.0
                if self.level <= exit_threshold:
                    self._hold = False
                    self._cooldown = cfg.cooldown_ticks
            else:
                # Use stress threshold plus hysteresis to enter
                entry_threshold = threshold + cfg.hysteresis / 2.0
                if self.level >= entry_threshold:
                    self._hold = True
        return self.hold

    # ------------------------------------------------------------------- update
    def step(
        self,
        stress: float,
        drawdown: float,
        novelty: float,
        *,
        dt: float = 1.0,
    ) -> Mapping[str, float]:
        if dt <= 0:
            raise ValueError("dt must be positive")

        # Performance tracking
        if self._enable_perf_tracking:
            import time

            start_time = time.perf_counter()

        stress = float(max(0.0, stress))
        drawdown = float(max(0.0, drawdown))
        novelty = float(max(0.0, novelty))

        cfg = self._config
        exited_hold_this_step = False
        # EMA dynamics for tonic and phasic components
        # Tonic: slow integration of chronic stress
        tonic_alpha = 1.0 - (1.0 - cfg.tonic_beta) ** dt
        self.tonic_level += tonic_alpha * (cfg.stress_gain * stress - self.tonic_level)

        # Phasic: fast response to acute transients (drawdown and novelty events)
        phasic_alpha = 1.0 - (1.0 - cfg.phasic_beta) ** dt
        phasic_drive = max(
            0.0, cfg.drawdown_gain * drawdown + cfg.novelty_gain * novelty
        )
        self.phasic_level += phasic_alpha * (phasic_drive - self.phasic_level)

        raw_level = max(0.0, min(2.0, self.tonic_level + self.phasic_level))
        # chronic stress accumulation and desensitisation
        if raw_level >= cfg.stress_threshold - cfg.hysteresis:
            self._chronic_ticks += 1
            if self._chronic_ticks >= cfg.chronic_window:
                self._desensitization = min(
                    cfg.max_desensitization,
                    self._desensitization + cfg.desensitization_rate,
                )
                self._chronic_ticks = 0
        else:
            self._chronic_ticks = 0
            self._desensitization *= 1.0 - cfg.desensitization_decay

        effective_level = raw_level * (1.0 - self._desensitization)
        self.level = min(1.5, max(0.0, effective_level))

        # hysteretic hold logic with cooldown extension under acute spikes
        threshold = cfg.stress_threshold
        release = max(0.0, cfg.release_threshold)

        # Apply hysteresis: higher threshold to enter, lower threshold to exit
        if self._hold:
            # Exit hold when level drops below release threshold minus hysteresis margin
            exit_threshold = release - cfg.hysteresis / 2.0
            if self.level <= exit_threshold:
                self._hold = False
                exited_hold_this_step = True
                # Initialize cooldown when EXITING hold state
                self._cooldown = cfg.cooldown_ticks
                # Extend cooldown if level is still elevated near threshold
                if self.level >= threshold:
                    self._cooldown = cfg.cooldown_ticks + cfg.cooldown_extension
        else:
            # Enter hold when level exceeds threshold plus hysteresis margin
            entry_threshold = threshold + cfg.hysteresis / 2.0
            if self.level >= entry_threshold:
                self._hold = True
            # If level spikes well above threshold while not in hold, prepare extended cooldown
            elif self.level >= threshold + cfg.hysteresis and self._cooldown == 0:
                # Pre-set cooldown for when/if we enter hold
                pass  # Will be handled when entering hold

        # Cooldown only decrements when NOT in active hold state. Count the
        # exit tick toward the cooldown duration so recovery happens within the
        # configured window instead of holding for an extra step after release
        # (which would keep ``hold`` latched even when serotonin has subsided).
        if not exited_hold_this_step and not self._hold and self._cooldown > 0:
            self._cooldown = max(0, self._cooldown - int(max(1, round(dt))))

        floor_span = max(0.0, cfg.floor_max - cfg.floor_min)
        floor = cfg.floor_min + floor_span * min(1.0, self.level * cfg.floor_gain)
        floor *= 1.0 - self._desensitization
        self.temperature_floor = min(cfg.floor_max, max(cfg.floor_min, floor))

        hold_flag = self.hold
        self._log("tacl.5ht.level", self.level)
        self._log("tacl.5ht.hold", 1.0 if hold_flag else 0.0)
        self._log("tacl.5ht.cooldown", float(self._cooldown))

        # Update performance metrics
        if self._enable_perf_tracking:
            self._step_count += 1
            self._total_step_time += time.perf_counter() - start_time
            if hold_flag:
                self._hold_count += 1

        return {
            "level": self.level,
            "hold": float(hold_flag),
            "cooldown": float(self._cooldown),
            "temperature_floor": self.temperature_floor,
            "desensitization": self._desensitization,
        }

    # ------------------------------------------------------------------ export
    def to_dict(self) -> Mapping[str, float]:
        return {
            "tonic_level": self.tonic_level,
            "phasic_level": self.phasic_level,
            "level": self.level,
            "hold": float(self.hold),
            "cooldown": float(self._cooldown),
            "temperature_floor": self.temperature_floor,
            "desensitization": self._desensitization,
        }

    @property
    def config(self) -> SerotoninConfig:
        return self._config

    # ----------------------------------------------------------------- utilities
    def get_state_summary(self) -> str:
        """Get a human-readable summary of current controller state.

        Returns:
            Formatted string with key state information for debugging.
        """
        entry = self._config.stress_threshold + self._config.hysteresis / 2
        exit_th = self._config.release_threshold - self._config.hysteresis / 2
        return (
            f"SerotoninController State:\n"
            f"  Level: {self.level:.3f} "
            f"(tonic: {self.tonic_level:.3f}, phasic: {self.phasic_level:.3f})\n"
            f"  Hold: {self.hold} (_hold: {self._hold}, cooldown: {self._cooldown})\n"
            f"  Desensitization: {self._desensitization:.3f}\n"
            f"  Temperature Floor: {self.temperature_floor:.3f}\n"
            f"  Thresholds: entry={entry:.3f}, exit={exit_th:.3f}"
        )

    def should_take_action(self, risk_level: str = "moderate") -> bool:
        """Determine if system should take new trading actions based on current state.

        Practical helper for integration with trading logic. Takes into account
        both the hold state and the serotonin level for risk-adjusted decisions.

        Args:
            risk_level: Risk tolerance level - "conservative", "moderate", or "aggressive"

        Returns:
            True if it's safe to take new actions, False if should hold/rest.
        """
        if self.hold:
            return False

        # Risk-adjusted thresholds
        thresholds = {
            "conservative": 0.3,  # Very cautious
            "moderate": 0.5,  # Balanced approach
            "aggressive": 0.7,  # Willing to take more risk
        }

        threshold = thresholds.get(risk_level, 0.5)
        return self.level < threshold

    def get_position_size_multiplier(self) -> float:
        """Calculate recommended position size multiplier based on serotonin state.

        Practical utility for position sizing. Returns a value between 0.0 and 1.0
        that can be multiplied with base position size.

        Returns:
            Multiplier in [0.0, 1.0] where 0.0 = no positions, 1.0 = full size
        """
        if self.hold:
            return 0.0

        # Linear scaling from full size at level=0 to zero at stress_threshold
        threshold = self._config.stress_threshold
        if self.level >= threshold:
            return 0.0

        # Scale down as stress increases
        multiplier = 1.0 - (self.level / threshold)
        return max(0.0, min(1.0, multiplier))

    def estimate_recovery_time(self) -> int:
        """Estimate ticks until controller exits hold state.

        Practical utility for planning and UI updates. Provides rough estimate
        based on current state and typical decay rates.

        Returns:
            Estimated number of ticks until recovery (0 if not in hold).
        """
        if not self.hold:
            return 0

        if self._hold:
            # Still in active hold, need to drop below exit threshold
            exit_threshold = (
                self._config.release_threshold - self._config.hysteresis / 2.0
            )
            if self.level <= exit_threshold:
                return self._cooldown

            # Estimate steps to reach exit threshold based on decay
            # Assuming zero stress input, estimate exponential decay
            level_diff = self.level - exit_threshold
            decay_per_step = self._config.tonic_beta * 0.5  # Conservative estimate

            if decay_per_step > 0:
                steps_to_exit = int(level_diff / decay_per_step) + 1
                return steps_to_exit + self._config.cooldown_ticks
            else:
                return self._config.cooldown_ticks + 10  # Fallback estimate
        else:
            # In cooldown phase
            return self._cooldown

    def validate_state(self) -> tuple[bool, list[str]]:
        """Validate internal state consistency.

        Practical debugging utility to detect state corruption or configuration issues.

        Returns:
            Tuple of (is_valid, list of issues found)
        """
        issues = []

        # Check level bounds
        if not (0.0 <= self.level <= 1.5):
            issues.append(f"Level {self.level:.3f} outside bounds [0.0, 1.5]")

        if not (0.0 <= self.tonic_level <= 2.0):
            issues.append(
                f"Tonic level {self.tonic_level:.3f} outside bounds [0.0, 2.0]"
            )

        if not (0.0 <= self.phasic_level <= 2.0):
            issues.append(
                f"Phasic level {self.phasic_level:.3f} outside bounds [0.0, 2.0]"
            )

        # Check desensitization
        if not (0.0 <= self._desensitization <= self._config.max_desensitization):
            issues.append(
                f"Desensitization {self._desensitization:.3f} outside valid range"
            )

        # Check cooldown consistency
        if self._cooldown < 0:
            issues.append(f"Negative cooldown: {self._cooldown}")

        max_cooldown = self._config.cooldown_ticks + self._config.cooldown_extension + 1
        if not self._hold and self._cooldown > max_cooldown:
            issues.append(f"Cooldown {self._cooldown} exceeds maximum expected value")

        # Check hold state consistency
        if self.hold != (self._hold or self._cooldown > 0):
            msg = (
                f"Hold property inconsistent: "
                f"hold={self.hold}, _hold={self._hold}, cooldown={self._cooldown}"
            )
            issues.append(msg)

        return len(issues) == 0, issues

    def get_performance_stats(self) -> Mapping[str, float]:
        """Get performance statistics (if tracking enabled).

        Returns:
            Dictionary with performance metrics, or empty dict if tracking disabled.
        """
        if not self._enable_perf_tracking or self._step_count == 0:
            return {}

        avg_step_time = self._total_step_time / self._step_count
        hold_rate = self._hold_count / self._step_count

        steps_per_sec = (
            self._step_count / self._total_step_time
            if self._total_step_time > 0
            else 0.0
        )
        return {
            "total_steps": float(self._step_count),
            "avg_step_time_ms": avg_step_time * 1000.0,
            "total_time_s": self._total_step_time,
            "steps_per_second": steps_per_sec,
            "hold_rate": hold_rate,
            "hold_count": float(self._hold_count),
        }

    def reset_performance_stats(self) -> None:
        """Reset performance tracking counters."""
        self._step_count = 0
        self._total_step_time = 0.0
        self._hold_count = 0

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


def _ensure_float(name: str, value: object, *, min_value: Optional[float] = None, max_value: Optional[float] = None) -> float:
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
        tonic_beta = _ensure_float("tonic_beta", raw["tonic_beta"], min_value=0.0, max_value=1.0)
        phasic_beta = _ensure_float("phasic_beta", raw["phasic_beta"], min_value=0.0, max_value=1.0)
        stress_gain = _ensure_float("stress_gain", raw["stress_gain"], min_value=0.0)
        drawdown_gain = _ensure_float("drawdown_gain", raw["drawdown_gain"], min_value=0.0)
        novelty_gain = _ensure_float("novelty_gain", raw["novelty_gain"], min_value=0.0)
        stress_threshold = _ensure_float("stress_threshold", raw["stress_threshold"], min_value=0.0, max_value=1.5)
        release_threshold = _ensure_float("release_threshold", raw["release_threshold"], min_value=0.0, max_value=stress_threshold)
        hysteresis = _ensure_float("hysteresis", raw["hysteresis"], min_value=0.0, max_value=1.0)
        cooldown_ticks = _ensure_int("cooldown_ticks", raw["cooldown_ticks"], min_value=0)
        chronic_window = _ensure_int("chronic_window", raw["chronic_window"], min_value=1)
        desensitization_rate = _ensure_float("desensitization_rate", raw["desensitization_rate"], min_value=0.0)
        desensitization_decay = _ensure_float("desensitization_decay", raw["desensitization_decay"], min_value=0.0, max_value=1.0)
        max_desensitization = _ensure_float("max_desensitization", raw["max_desensitization"], min_value=0.0, max_value=0.99)
        floor_min = _ensure_float("floor_min", raw["floor_min"], min_value=0.0, max_value=1.0)
        floor_max = _ensure_float("floor_max", raw["floor_max"], min_value=floor_min, max_value=1.0)
        floor_gain = _ensure_float("floor_gain", raw["floor_gain"], min_value=0.0, max_value=4.0)
        cooldown_extension = _ensure_int("cooldown_extension", raw["cooldown_extension"], min_value=0)
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
        self.tonic_level = 0.0
        self.phasic_level = 0.0
        self.level = 0.0
        self._hold = False
        self._cooldown = 0
        self._chronic_ticks = 0
        self._desensitization = 0.0
        self.temperature_floor = self._config.floor_min

    # ------------------------------------------------------------------- state
    @property
    def hold(self) -> bool:
        return self._hold or self._cooldown > 0

    def check_cooldown(self, serotonin_signal: Optional[float] = None) -> bool:
        if serotonin_signal is not None:
            self.level = float(max(0.0, min(1.5, serotonin_signal)))
            self._hold = self.level >= self._config.stress_threshold
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
        stress = float(max(0.0, stress))
        drawdown = float(max(0.0, drawdown))
        novelty = float(max(0.0, novelty))

        cfg = self._config
        # EMA dynamics for tonic and phasic components
        tonic_alpha = 1.0 - (1.0 - cfg.tonic_beta) ** dt
        phasic_alpha = 1.0 - (1.0 - cfg.phasic_beta) ** dt
        self.tonic_level += tonic_alpha * (cfg.stress_gain * stress - self.tonic_level)
        phasic_drive = max(0.0, cfg.drawdown_gain * drawdown + cfg.novelty_gain * novelty)
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
        if self._hold:
            if self.level <= release:
                self._hold = False
        else:
            if self.level >= threshold:
                self._hold = True
                self._cooldown = max(self._cooldown, cfg.cooldown_ticks)

        if self.level >= threshold + cfg.hysteresis:
            self._cooldown = max(self._cooldown, cfg.cooldown_ticks + cfg.cooldown_extension)

        if self._cooldown > 0:
            self._cooldown = max(0, self._cooldown - int(max(1, round(dt))))

        floor_span = max(0.0, cfg.floor_max - cfg.floor_min)
        floor = cfg.floor_min + floor_span * min(1.0, self.level * cfg.floor_gain)
        floor *= 1.0 - self._desensitization
        self.temperature_floor = min(cfg.floor_max, max(cfg.floor_min, floor))

        hold_flag = self.hold
        self._log("tacl.5ht.level", self.level)
        self._log("tacl.5ht.hold", 1.0 if hold_flag else 0.0)
        self._log("tacl.5ht.cooldown", float(self._cooldown))

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


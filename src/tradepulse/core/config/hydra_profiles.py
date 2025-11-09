"""Hydra profile helpers that provide standardized experiment handling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from omegaconf import DictConfig, OmegaConf
from omegaconf.errors import InterpolationResolutionError
from pydantic import ValidationError

from .cli_models import ExperimentConfig

__all__ = [
    "ExperimentProfileError",
    "ExperimentProfileRegistry",
    "available_experiment_profiles",
    "validate_experiment_profile",
]


class ExperimentProfileError(ValueError):
    """Raised when a Hydra experiment profile cannot be validated."""


@dataclass(slots=True)
class ExperimentProfileRegistry:
    """Registry that knows about available Hydra experiment profiles."""

    profiles: Mapping[str, Path]

    @classmethod
    def discover(cls, conf_root: Path | None = None) -> "ExperimentProfileRegistry":
        """Build a registry by scanning the Hydra configuration tree."""

        base_path = conf_root or Path(__file__).resolve().parents[2] / "conf"
        experiment_dir = base_path / "experiment"
        if not experiment_dir.exists():
            msg = f"Hydra experiment configuration directory not found: {experiment_dir}"
            raise ExperimentProfileError(msg)

        profiles: dict[str, Path] = {}
        for path in experiment_dir.glob("*.yaml"):
            stem = path.stem
            if stem.startswith("_") or stem == "base":
                continue
            profiles[stem] = path
        return cls(profiles=profiles)

    def names(self) -> list[str]:
        """Return the sorted list of registered profile names."""

        return sorted(self.profiles)

    def ensure(self, profile_name: str) -> None:
        """Raise ``ExperimentProfileError`` if ``profile_name`` is unknown."""

        if profile_name not in self.profiles:
            available = ", ".join(self.names()) or "<none>"
            msg = (
                f"Unknown experiment profile '{profile_name}'. "
                f"Available profiles: {available}."
            )
            raise ExperimentProfileError(msg)


def available_experiment_profiles(conf_root: Path | None = None) -> list[str]:
    """Convenience wrapper that lists available experiment profiles."""

    registry = ExperimentProfileRegistry.discover(conf_root=conf_root)
    return registry.names()


def validate_experiment_profile(cfg: DictConfig) -> ExperimentConfig:
    """Validate the ``experiment`` section of a Hydra configuration."""

    if not isinstance(cfg, DictConfig):
        msg = "validate_experiment_profile expects a DictConfig instance"
        raise ExperimentProfileError(msg)

    if "experiment" not in cfg:
        msg = "Hydra configuration is missing the 'experiment' section"
        raise ExperimentProfileError(msg)

    try:
        container = OmegaConf.to_container(cfg.experiment, resolve=True)
    except InterpolationResolutionError:
        container = OmegaConf.to_container(cfg.experiment, resolve=False)

    try:
        return ExperimentConfig.model_validate(container)
    except ValidationError as exc:
        msg = "Hydra experiment profile failed validation"
        raise ExperimentProfileError(msg) from exc

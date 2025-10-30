"""Core runtime helpers shared across the ``scripts`` package."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import locale
import logging
import os
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from core.utils.determinism import apply_thread_determinism

DEFAULT_SEED = 1337
DEFAULT_LOCALE = "C"
_LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


class UTCFormatter(logging.Formatter):
    """Format timestamps using ISO-8601 in UTC regardless of host settings."""

    def formatTime(
        self, record: logging.LogRecord, datefmt: str | None = None
    ) -> str:  # noqa: N802
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat(timespec="seconds")


@dataclass(frozen=True)
class LoadedEnvironment:
    """Representation of key/value pairs sourced from ``.env`` style files."""

    variables: Mapping[str, str]
    source: Path


def configure_deterministic_runtime(
    *, seed: int | None = None, locale_name: str | None = None
) -> None:
    """Apply deterministic defaults for random seed and locale."""

    resolved_seed = (
        seed
        if seed is not None
        else int(os.getenv("SCRIPTS_RANDOM_SEED", DEFAULT_SEED))
    )
    resolved_locale = locale_name or os.getenv("SCRIPTS_LOCALE", DEFAULT_LOCALE)

    apply_thread_determinism()

    os.environ["PYTHONHASHSEED"] = str(resolved_seed)
    random.seed(resolved_seed)

    try:  # pragma: no cover - numpy is optional in many environments
        import numpy as np  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover - import guard is trivial
        pass
    else:  # pragma: no branch - simple deterministic seeding
        np.random.seed(resolved_seed)

    try:
        locale.setlocale(locale.LC_ALL, resolved_locale)
    except locale.Error:
        locale.setlocale(locale.LC_ALL, "")


def configure_logging(level: int) -> None:
    """Initialise the logging stack with UTC ISO-8601 timestamps."""

    handler = logging.StreamHandler()
    handler.setFormatter(UTCFormatter(_LOG_FORMAT))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def parse_env_file(path: Path) -> LoadedEnvironment | None:
    """Parse a dotenv style file without leaking secret values."""

    if not path.exists():
        return None

    variables: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key:
            continue
        variables[key] = value

    return LoadedEnvironment(variables=variables, source=path)


def apply_environment(overrides: Mapping[str, str]) -> None:
    """Update :data:`os.environ` without exposing secrets in the logs."""

    for key, value in overrides.items():
        os.environ[key] = value


__all__ = [
    "DEFAULT_LOCALE",
    "DEFAULT_SEED",
    "LoadedEnvironment",
    "UTCFormatter",
    "apply_environment",
    "configure_deterministic_runtime",
    "configure_logging",
    "parse_env_file",
]

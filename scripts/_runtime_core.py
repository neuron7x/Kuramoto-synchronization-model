"""Core runtime helpers shared across the ``scripts`` package."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import locale
import logging
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

from core.utils.determinism import apply_thread_determinism
from core.localization import LocaleFormatRules, negotiate_locale, validate_timezone

DEFAULT_SEED = 1337
DEFAULT_LOCALE = "C"
DEFAULT_TIMEZONE = "UTC"
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


def _iter_locale_candidates(tag: str) -> Iterable[str]:
    base = tag.strip()
    if not base:
        return []
    candidates = [base]
    underscored = base.replace("-", "_")
    if underscored != base:
        candidates.append(underscored)
    suffixes = [".UTF-8", ".utf8"]
    for candidate in list(candidates):
        for suffix in suffixes:
            candidates.append(f"{candidate}{suffix}")
    return candidates


def _set_process_locale(preferred: Iterable[str]) -> str:
    for candidate in preferred:
        try:
            locale.setlocale(locale.LC_ALL, candidate)
        except locale.Error:
            continue
        else:
            return candidate
    locale.setlocale(locale.LC_ALL, "")
    return locale.setlocale(locale.LC_ALL)


def _set_timezone_env(tz: str) -> str:
    os.environ["TZ"] = tz
    if hasattr(time, "tzset"):
        try:
            time.tzset()
        except OSError:  # pragma: no cover - tzset failures are platform specific
            logging.getLogger(__name__).warning("failed to apply timezone '%s'", tz)
    return tz


def get_localization_rules(
    preferred_locales: Iterable[str] | None = None,
    *,
    currency_override: str | None = None,
) -> LocaleFormatRules:
    """Expose localisation metadata for downstream services."""

    locales = list(preferred_locales or [])
    rules = negotiate_locale(locales or None, currency_override=currency_override)
    return rules


def configure_deterministic_runtime(
    *, seed: int | None = None, locale_name: str | None = None
) -> LocaleFormatRules:
    """Apply deterministic defaults for random seed, locale, and timezone."""

    resolved_seed = (
        seed
        if seed is not None
        else int(os.getenv("SCRIPTS_RANDOM_SEED", DEFAULT_SEED))
    )
    preferred_locales = []
    if locale_name:
        preferred_locales.append(locale_name)
    env_locale = os.getenv("SCRIPTS_LOCALE")
    if env_locale:
        preferred_locales.append(env_locale)

    apply_thread_determinism()

    os.environ["PYTHONHASHSEED"] = str(resolved_seed)
    random.seed(resolved_seed)

    try:  # pragma: no cover - numpy is optional in many environments
        import numpy as np  # type: ignore
    except ModuleNotFoundError:  # pragma: no cover - import guard is trivial
        pass
    else:  # pragma: no branch - simple deterministic seeding
        np.random.seed(resolved_seed)

    rules = get_localization_rules(preferred_locales or None)

    applied_locale = _set_process_locale(
        list(_iter_locale_candidates(rules.locale))
        or _iter_locale_candidates(DEFAULT_LOCALE)
    )
    os.environ["LC_ALL"] = applied_locale

    tz = validate_timezone(rules.timezone) if rules.timezone else DEFAULT_TIMEZONE
    _set_timezone_env(tz)

    return rules


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
    "DEFAULT_TIMEZONE",
    "LoadedEnvironment",
    "UTCFormatter",
    "apply_environment",
    "configure_deterministic_runtime",
    "configure_logging",
    "get_localization_rules",
    "parse_env_file",
]

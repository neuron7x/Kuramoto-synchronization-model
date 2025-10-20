"""Runtime helpers for negotiating locale-aware formatting rules."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_LOGGER = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "configs" / "localization" / "locales.yaml"

_FALLBACK_CATALOG: dict[str, Any] = {
    "defaults": {
        "locale_priority": ["en-US"],
        "currency": "USD",
        "timezone": "UTC",
        "datetime": {
            "year": "numeric",
            "month": "2-digit",
            "day": "2-digit",
            "hour": "2-digit",
            "minute": "2-digit",
            "second": "2-digit",
            "hourCycle": "h23",
            "timeZoneName": "short",
        },
    },
    "locales": {
        "en-US": {
            "currency": "USD",
            "timezone": "UTC",
            "symbols": {"decimal": ".", "group": ","},
            "formats": {
                "number": {"minimumFractionDigits": 0, "maximumFractionDigits": 2, "useGrouping": True},
                "currency": {"minimumFractionDigits": 2, "maximumFractionDigits": 2},
                "percent": {"minimumFractionDigits": 2, "maximumFractionDigits": 2},
                "datetime": {
                    "year": "numeric",
                    "month": "2-digit",
                    "day": "2-digit",
                    "hour": "2-digit",
                    "minute": "2-digit",
                    "second": "2-digit",
                    "hourCycle": "h23",
                    "timeZoneName": "short",
                },
            },
        }
    },
    "currency_overrides": {},
}


LocalizationCatalog = Mapping[str, Any]


@dataclass(frozen=True)
class LocaleFormatRules:
    """Resolved localisation rules for a specific locale."""

    locale: str
    currency: str
    timezone: str
    number: Mapping[str, Any]
    currency_format: Mapping[str, Any]
    percent: Mapping[str, Any]
    datetime: Mapping[str, Any]
    symbols: Mapping[str, str]
    currency_overrides: Mapping[str, str]

    def resolve_currency(self, asset_code: str | None = None, override: str | None = None) -> str:
        """Return the currency code that should be used for the given context."""

        if override:
            return override
        if asset_code:
            code = self.currency_overrides.get(asset_code)
            if code:
                return code
        return self.currency

    def as_dict(self) -> dict[str, Any]:
        """Serialise the locale rules for settings models and telemetry."""

        return {
            "locale": self.locale,
            "currency": self.currency,
            "timezone": self.timezone,
            "number": dict(self.number),
            "currency_format": dict(self.currency_format),
            "percent": dict(self.percent),
            "datetime": dict(self.datetime),
            "symbols": dict(self.symbols),
            "currency_overrides": dict(self.currency_overrides),
        }


def _read_catalog(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        _LOGGER.warning("localization catalog missing at %s", path)
        return None
    except OSError as exc:  # pragma: no cover - unlikely but defensive
        _LOGGER.error("failed to read localization catalog at %s: %s", path, exc)
        return None

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        _LOGGER.error("invalid localization catalog at %s: %s", path, exc)
        return None

    return data


def _merge_catalog(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "defaults": dict(base.get("defaults", {})),
        "locales": {},
        "currency_overrides": dict(base.get("currency_overrides", {})),
    }
    merged["currency_overrides"].update(override.get("currency_overrides", {}))

    default_locales = base.get("locales", {})
    override_locales = override.get("locales", {})
    for locale_name, locale_data in default_locales.items():
        merged["locales"][locale_name] = json.loads(json.dumps(locale_data))
    for locale_name, locale_data in override_locales.items():
        merged["locales"][locale_name] = json.loads(json.dumps(locale_data))

    merged_defaults = merged["defaults"]
    merged_defaults.update(override.get("defaults", {}))
    if "locale_priority" in merged_defaults:
        priority = merged_defaults["locale_priority"]
        if isinstance(priority, Sequence):
            merged_defaults["locale_priority"] = [str(item) for item in priority if str(item)]
        else:
            merged_defaults["locale_priority"] = [str(priority)]
    return merged


@lru_cache(maxsize=None)
def get_localization_catalog(config_path: str | Path | None = None) -> LocalizationCatalog:
    """Load localisation metadata from disk with caching."""

    path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG_PATH
    disk_catalog = _read_catalog(path)
    if disk_catalog is None:
        return _FALLBACK_CATALOG
    return _merge_catalog(_FALLBACK_CATALOG, disk_catalog)


def _normalise_locale_tag(tag: str) -> str:
    return tag.replace("_", "-").strip()


def _iter_candidates(preferred: Sequence[str] | None, defaults: Sequence[str]) -> Sequence[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for bucket in (preferred or []), defaults:
        for tag in bucket:
            normalised = _normalise_locale_tag(str(tag))
            if not normalised or normalised in seen:
                continue
            seen.add(normalised)
            ordered.append(normalised)
    return ordered


def _select_locale(catalog: Mapping[str, Any], preferred: Sequence[str] | None) -> tuple[str, Mapping[str, Any]]:
    defaults = catalog.get("defaults", {})
    priority = defaults.get("locale_priority", [])
    candidates = _iter_candidates(preferred, priority)
    locales = catalog.get("locales", {})
    for candidate in candidates:
        if candidate in locales:
            return candidate, locales[candidate]
        legacy = candidate.replace("-", "_")
        if legacy in locales:
            return legacy, locales[legacy]
    if locales:
        key, value = next(iter(locales.items()))
        return str(key), value
    return "en-US", _FALLBACK_CATALOG["locales"]["en-US"]


def _merge_datetime_options(defaults: Mapping[str, Any], overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = dict(defaults)
    if overrides:
        merged.update(overrides)
    return merged


def negotiate_locale(
    preferred_locales: Sequence[str] | None = None,
    *,
    currency_override: str | None = None,
    catalog: LocalizationCatalog | None = None,
    asset_currency_map: Mapping[str, str] | None = None,
) -> LocaleFormatRules:
    """Resolve localisation rules for the requested locale preferences."""

    catalog = catalog or get_localization_catalog()
    defaults = catalog.get("defaults", {})
    selected_locale, entry = _select_locale(catalog, preferred_locales)

    formats: Mapping[str, Any] = entry.get("formats", {})  # type: ignore[assignment]
    default_datetime = defaults.get("datetime", {})
    timezone = entry.get("timezone") or defaults.get("timezone") or "UTC"

    symbols = entry.get("symbols", {})
    if not isinstance(symbols, Mapping):
        symbols = {}

    overrides: MutableMapping[str, str] = {}
    overrides.update(catalog.get("currency_overrides", {}))
    if asset_currency_map:
        overrides.update({str(k): str(v) for k, v in asset_currency_map.items() if str(k)})

    resolved_currency = currency_override or entry.get("currency") or defaults.get("currency", "USD")

    return LocaleFormatRules(
        locale=_normalise_locale_tag(selected_locale),
        currency=str(resolved_currency),
        timezone=str(timezone),
        number=dict(formats.get("number", {})),
        currency_format=dict(formats.get("currency", {})),
        percent=dict(formats.get("percent", {})),
        datetime=_merge_datetime_options(default_datetime, formats.get("datetime")),
        symbols={str(k): str(v) for k, v in symbols.items()},
        currency_overrides=dict(overrides),
    )


def validate_timezone(timezone: str) -> str:
    """Ensure the provided timezone exists; fall back to UTC if not."""

    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        _LOGGER.warning("timezone '%s' not found; falling back to UTC", timezone)
        return "UTC"
    return timezone


__all__ = [
    "LocaleFormatRules",
    "LocalizationCatalog",
    "get_localization_catalog",
    "negotiate_locale",
    "validate_timezone",
]

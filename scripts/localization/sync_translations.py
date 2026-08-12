#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Synchronise GeoSync dashboard localization assets."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Set

import yaml
from jsonschema import Draft202012Validator

from core.compat import utc_now

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCALES_YAML = REPO_ROOT / "configs" / "localization" / "locales.yaml"
TRANSLATIONS_DIR = REPO_ROOT / "ui" / "dashboard" / "src" / "i18n" / "locales"
METADATA_JSON = REPO_ROOT / "ui" / "dashboard" / "src" / "i18n" / "locales.metadata.json"
SCHEMA_PATH = REPO_ROOT / "schemas" / "localization" / "translation.schema.json"
COVERAGE_REPORT = REPO_ROOT / "reports" / "localization" / "coverage.json"
DEFAULT_VENDOR_DIR = REPO_ROOT / "scripts" / "localization" / "vendor"


@dataclass
class LocaleCoverage:
    locale: str
    missing: Set[str]
    extra: Set[str]

    @property
    def coverage(self) -> float | None:
        # Note: This property is not currently used. Coverage is calculated directly
        # in the main() function using the formula on line 199.
        if len(self.missing) == 0 and len(self.extra) == 0:
            return 1.0
        return None


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--locales-config",
        type=Path,
        default=DEFAULT_LOCALES_YAML,
        help="Path to locales.yaml",
    )
    parser.add_argument(
        "--translations-dir",
        type=Path,
        default=TRANSLATIONS_DIR,
        help="Path to locale JSON bundles",
    )
    parser.add_argument(
        "--metadata-output",
        type=Path,
        default=METADATA_JSON,
        help="Generated metadata JSON path",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=SCHEMA_PATH,
        help="JSON schema for translation bundles",
    )
    parser.add_argument(
        "--coverage-report",
        type=Path,
        default=COVERAGE_REPORT,
        help="Output coverage report path",
    )
    parser.add_argument(
        "--vendor-dir",
        type=Path,
        default=DEFAULT_VENDOR_DIR,
        help="Directory with vendor-provided locale JSON overrides",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate only; fail if changes would be produced",
    )
    return parser.parse_args(argv)


def load_yaml(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def dump_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        result = {key: deep_merge(base.get(key), override[key]) for key in override}
        for key, value in base.items():
            if key not in result:
                result[key] = value
        return result
    return deepcopy(override)


def flatten_keys(node: Any, prefix: str = "") -> Set[str]:
    if isinstance(node, Mapping):
        keys: Set[str] = set()
        for key, value in node.items():
            next_prefix = f"{prefix}.{key}" if prefix else key
            keys.update(flatten_keys(value, next_prefix))
        return keys
    return {prefix}


def camelise(key: str) -> str:
    parts = key.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])


def transform_metadata(raw: Dict[str, Any]) -> Dict[str, Any]:
    locales = {}
    for code, payload in raw.get("locales", {}).items():
        entry = {}
        for key, value in payload.items():
            if key == "formats":
                entry["formats"] = {camelise(k): v for k, v in value.items()}
            elif key == "tone":
                entry["tone"] = {
                    "voice": value.get("voice"),
                    "guidelines": {
                        "do": value.get("guidelines", {}).get("do", []),
                        "dont": value.get("guidelines", {}).get("dont", []),
                    },
                }
            elif key == "privacy_regimes":
                entry["privacyRegimes"] = value
            elif key == "default_currency":
                entry["defaultCurrency"] = value
            elif key == "review_cadence":
                entry["reviewCadence"] = value
            else:
                entry[camelise(key)] = value
        locales[code] = entry
    return {
        "defaultLocale": raw.get("default_locale"),
        "fallbackLocale": raw.get("fallback_locale", raw.get("default_locale")),
        "locales": locales,
    }


def load_translations(translations_dir: Path) -> Dict[str, Dict[str, Any]]:
    translations = {}
    for path in sorted(translations_dir.glob("*.json")):
        translations[path.stem] = load_json(path)
    return translations


def apply_vendor_overrides(translations: Dict[str, Dict[str, Any]], vendor_dir: Path) -> bool:
    if not vendor_dir.exists():
        return False
    changed = False
    for path in sorted(vendor_dir.glob("*.json")):
        locale = path.stem
        vendor_payload = load_json(path)
        if locale not in translations:
            translations[locale] = vendor_payload
            changed = True
            continue
        merged = deep_merge(translations[locale], vendor_payload)
        if merged != translations[locale]:
            translations[locale] = merged
            changed = True
    return changed


def validate_translation(
    payload: Dict[str, Any], validator: Draft202012Validator, path: Path
) -> None:
    errors = sorted(validator.iter_errors(payload), key=lambda err: err.path)
    if errors:
        formatted = "\n".join(
            f"- {'/'.join(map(str, error.path))}: {error.message}" for error in errors
        )
        raise ValueError(f"Schema validation failed for {path}:\n{formatted}")


def compute_coverage(base_keys: Set[str], locale: str, keys: Set[str]) -> LocaleCoverage:
    missing = base_keys - keys
    extra = keys - base_keys
    return LocaleCoverage(locale=locale, missing=missing, extra=extra)


def write_translations(
    translations: Dict[str, Dict[str, Any]], translations_dir: Path, check: bool
) -> bool:
    wrote = False
    for locale, payload in translations.items():
        path = translations_dir / f"{locale}.json"
        if check:
            if not path.exists() or json.loads(path.read_text(encoding="utf-8")) != payload:
                return True
            continue
        dump_json(path, payload)
        wrote = True
    return wrote


def main(argv: Iterable[str]) -> int:
    args = parse_args(argv)
    locales_config = load_yaml(args.locales_config)
    translations = load_translations(args.translations_dir)
    vendor_changed = apply_vendor_overrides(translations, args.vendor_dir)

    schema = load_json(args.schema)
    validator = Draft202012Validator(schema)

    if locales_config.get("default_locale") not in translations:
        raise RuntimeError(
            f"Default locale '{locales_config.get('default_locale')}' is missing from translations"
        )

    base_locale = locales_config["default_locale"]
    base_keys = flatten_keys(translations[base_locale])

    coverage: Dict[str, Any] = {"locales": {}, "generatedAt": None}
    issues = []

    for locale, payload in translations.items():
        validate_translation(payload, validator, args.translations_dir / f"{locale}.json")
        locale_keys = flatten_keys(payload)
        stats = compute_coverage(base_keys, locale, locale_keys)
        coverage["locales"][locale] = {
            "missing": sorted(stats.missing),
            "extra": sorted(stats.extra),
            "coverageRatio": (
                round((len(base_keys) - len(stats.missing)) / len(base_keys), 4)
                if base_keys
                else 1.0
            ),
        }
        if stats.missing or stats.extra:
            issues.append((locale, stats))

    metadata_payload = transform_metadata(locales_config)

    if args.check:
        pending_changes = vendor_changed or write_translations(
            translations, args.translations_dir, check=True
        )
        metadata_changed = (
            not args.metadata_output.exists()
            or json.loads(args.metadata_output.read_text(encoding="utf-8")) != metadata_payload
        )
        if args.coverage_report.exists():
            existing_coverage = json.loads(args.coverage_report.read_text(encoding="utf-8"))
            existing_coverage["generatedAt"] = None
        else:
            existing_coverage = None
        coverage_changed = existing_coverage != coverage
        if issues:
            for locale, stats in issues:
                if stats.missing:
                    print(
                        f"Locale {locale} missing keys: {', '.join(sorted(stats.missing))}",
                        file=sys.stderr,
                    )
                if stats.extra:
                    print(
                        f"Locale {locale} has unexpected keys: {', '.join(sorted(stats.extra))}",
                        file=sys.stderr,
                    )
        if issues or pending_changes or metadata_changed or coverage_changed:
            return 1
        return 0

    write_translations(translations, args.translations_dir, check=False)
    dump_json(args.metadata_output, metadata_payload)
    coverage["generatedAt"] = utc_now().isoformat().replace("+00:00", "Z")
    dump_json(args.coverage_report, coverage)

    if issues:
        for locale, stats in issues:
            if stats.missing:
                print(f"[warn] Locale {locale} missing keys: {', '.join(sorted(stats.missing))}")
            if stats.extra:
                print(
                    f"[warn] Locale {locale} has unexpected keys: {', '.join(sorted(stats.extra))}"
                )
        raise SystemExit(1)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

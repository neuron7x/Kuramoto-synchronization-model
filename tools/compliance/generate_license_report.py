#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Generate third-party license report from CycloneDX SBOM."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

HEADER = """# Third-Party Notices

This document is generated from the `sbom/cyclonedx-sbom.json` file and lists the
third-party dependencies bundled with GeoSync, including their discovered
licenses. Regenerate this report after updating dependencies by running:

```bash
python tools/compliance/generate_license_report.py
```
"""


@lru_cache(maxsize=None)
def _fetch_license_from_pypi(name: str, version: str) -> list[str]:
    if not version or version in {"Unspecified", "latest"}:
        return []

    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urlopen(url, timeout=10) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return []

    info = payload.get("info", {})
    resolved: list[str] = []

    license_field = info.get("license")
    if isinstance(license_field, str):
        license_value = license_field.strip()
        if license_value and license_value.upper() not in {"UNKNOWN", "SEE LICENSE"}:
            resolved.append(license_value)

    for classifier in info.get("classifiers", []) or []:
        if isinstance(classifier, str) and classifier.startswith("License ::"):
            resolved.append(classifier.split("::")[-1].strip())

    return sorted(set(filter(None, resolved)))


def extract_license_names(entry: dict[str, Any]) -> list[str]:
    licenses: list[str] = []
    for license_block in entry.get("licenses", []) or []:
        license_info = license_block.get("license")
        if isinstance(license_info, dict):
            name = license_info.get("name") or license_info.get("id")
            if name:
                licenses.append(str(name))
        expression = license_block.get("expression")
        if expression:
            licenses.append(str(expression))
    if not licenses:
        component_name = entry.get("name", "")
        version = entry.get("version") or ""
        licenses = _fetch_license_from_pypi(str(component_name), str(version))
    if not licenses:
        licenses.append("UNKNOWN")
    return sorted(set(filter(None, licenses)))


# Backwards compatibility for older imports expecting the private helper name.
_extract_license_names = extract_license_names


def build_rows(components: list[dict[str, Any]]) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for component in components:
        component_type = component.get("type")
        if component_type not in {"library", "framework", "application"}:
            continue
        name = component.get("name") or "UNKNOWN"
        version = component.get("version") or "Unspecified"
        purl = component.get("purl") or ""
        license_names = "; ".join(extract_license_names(component))
        rows.append((str(name), str(version), license_names, str(purl)))
    rows.sort(key=lambda item: (item[0].lower(), item[1]))
    return rows


def render_table(rows: list[tuple[str, str, str, str]]) -> str:
    lines = [
        "| Name | Version | License(s) | Package URL |",
        "| --- | --- | --- | --- |",
    ]
    for name, version, licenses, purl in rows:
        safe_purl = purl if purl else ""
        lines.append(f"| {name} | {version} | {licenses} | {safe_purl} |")
    return "\n".join(lines)


def main() -> None:
    sbom_path = Path("sbom/cyclonedx-sbom.json")
    if not sbom_path.is_file():
        raise SystemExit(f"Missing SBOM artifact: {sbom_path}")

    data = json.loads(sbom_path.read_text(encoding="utf-8"))
    components = data.get("components") or []
    rows = build_rows(components)

    report_dir = Path("docs/legal")
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "THIRD_PARTY_NOTICES.md"
    report_body = HEADER + "\n" + render_table(rows) + "\n"
    report_path.write_text(report_body, encoding="utf-8")

    print(f"Wrote third-party notice to {report_path}")


if __name__ == "__main__":
    main()

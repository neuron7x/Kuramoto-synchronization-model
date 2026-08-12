from __future__ import annotations

import argparse
import datetime as dt
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-xml", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    coverage_xml = Path(args.coverage_xml)
    output = Path(args.output)

    payload = {
        "schema_version": "1.0",
        "coverage_xml": str(coverage_xml),
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "line_rate": None,
        "branch_rate": None,
        "modules": {"core": None, "backtest": None, "execution": None},
        "verdict": "blocked",
        "notes": [],
    }

    if not coverage_xml.exists():
        payload["notes"].append("coverage.xml missing")
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 1

    try:
        root = ET.parse(coverage_xml).getroot()
    except ET.ParseError:
        payload["notes"].append("coverage.xml malformed")
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 1

    lr = root.attrib.get("line-rate")
    br = root.attrib.get("branch-rate")
    if lr is None:
        payload["notes"].append("global line-rate missing")
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 0

    payload["line_rate"] = float(lr)
    payload["branch_rate"] = float(br) if br is not None else None

    packages = root.find("packages")
    module_rates = {"core": [], "backtest": [], "execution": []}
    if packages is not None:
        for pkg in packages.findall("package"):
            name = (pkg.attrib.get("name") or "").lower()
            rate = pkg.attrib.get("line-rate")
            if rate is None:
                continue
            for m in module_rates:
                if m in name:
                    module_rates[m].append(float(rate))
    has_modules = any(module_rates[m] for m in module_rates)
    if has_modules:
        for m, vals in module_rates.items():
            payload["modules"][m] = sum(vals) / len(vals) if vals else None
        payload["verdict"] = "accepted"
        payload["notes"].append("module-level rates derived from package names")
    else:
        payload["verdict"] = "downgraded"
        payload["notes"].append("global coverage parsed; module-level coverage unavailable")

    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

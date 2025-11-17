"""Enforce coverage guardrails for reliability-critical modules."""

from __future__ import annotations

import argparse
import sys
import tomllib
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True)
class CoverageTarget:
    """Coverage expectation for a single source file."""

    path: Path
    min_line_rate: float


@dataclass(frozen=True)
class CoverageSnapshot:
    """Line and branch coverage metrics extracted from coverage.xml."""

    line_rate: float
    branch_rate: float | None = None


def _load_targets(config_path: Path) -> list[CoverageTarget]:
    document = tomllib.loads(config_path.read_text(encoding="utf-8"))
    try:
        entries = document["targets"]
    except KeyError as exc:
        raise ValueError("Coverage config must define a 'targets' array.") from exc

    targets: list[CoverageTarget] = []
    for entry in entries:
        try:
            raw_path = entry["path"]
            raw_min_line_rate = entry["min_line_rate"]
        except KeyError as exc:
            raise ValueError(
                "Each coverage target requires 'path' and 'min_line_rate'."
            ) from exc

        min_line_rate = float(raw_min_line_rate)
        if not 0.0 <= min_line_rate <= 100.0:
            raise ValueError(
                f"min_line_rate for {raw_path!r} must be between 0 and 100 (got {min_line_rate})."
            )

        targets.append(CoverageTarget(path=Path(raw_path), min_line_rate=min_line_rate))
    return targets


def _resolve_filename(filename: str, sources: Iterable[Path]) -> list[Path]:
    relative = Path(filename)
    resolved: list[Path] = [relative]

    for base in sources:
        if not base:
            continue
        candidate = (base / relative).resolve()
        try:
            resolved.append(candidate.relative_to(Path.cwd()))
        except ValueError:
            resolved.append(candidate)
    return resolved


def _load_coverage_map(report_path: Path) -> Mapping[str, CoverageSnapshot]:
    tree = ET.parse(report_path)
    root = tree.getroot()

    sources_element = root.find("sources")
    sources = (
        [Path(elem.text or "") for elem in sources_element.findall("source")]
        if sources_element is not None
        else []
    )

    coverage_by_path: dict[str, CoverageSnapshot] = {}
    packages_element = root.find("packages")
    if packages_element is None:
        return coverage_by_path

    for package in packages_element.findall("package"):
        classes = package.find("classes")
        if classes is None:
            continue
        for cls in classes.findall("class"):
            filename = cls.get("filename")
            if filename is None:
                continue
            line_rate = float(cls.get("line-rate", "0")) * 100.0
            branch_attr = cls.get("branch-rate")
            branch_rate = (
                float(branch_attr) * 100.0 if branch_attr is not None else None
            )
            snapshot = CoverageSnapshot(line_rate=line_rate, branch_rate=branch_rate)

            for candidate in _resolve_filename(filename, sources):
                key = candidate.as_posix()
                coverage_by_path[key] = snapshot
    return coverage_by_path


def _evaluate_targets(
    targets: Iterable[CoverageTarget],
    coverage_map: Mapping[str, CoverageSnapshot],
    report_path: Path,
) -> int:
    success = True
    print("Reliability coverage guardrail results:\n")
    for target in targets:
        key_variants = {
            target.path.as_posix(),
            target.path.resolve().as_posix(),
        }
        metrics = None
        for variant in key_variants:
            metrics = coverage_map.get(variant)
            if metrics is not None:
                break
        if metrics is None:
            success = False
            print(
                f"✗ {target.path.as_posix()} — no coverage data found in {report_path}"
            )
            continue

        line_rate = metrics.line_rate
        threshold = target.min_line_rate
        if line_rate + 1e-9 < threshold:
            success = False
            print(
                f"✗ {target.path.as_posix()} — line coverage {line_rate:.2f}% < required {threshold:.2f}%"
            )
            continue

        print(
            f"✓ {target.path.as_posix()} — line coverage {line_rate:.2f}% (threshold {threshold:.2f}%)"
        )

    return 0 if success else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate that reliability-critical modules maintain the expected coverage levels.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/quality/critical_surface.toml"),
        help="Path to the coverage guardrail configuration (default: configs/quality/critical_surface.toml).",
    )
    parser.add_argument(
        "--coverage",
        type=Path,
        default=Path("coverage.xml"),
        help="Path to the coverage XML report produced by pytest-cov (default: coverage.xml).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        targets = _load_targets(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error loading coverage targets: {exc}", file=sys.stderr)
        return 2

    try:
        coverage_map = _load_coverage_map(args.coverage)
    except (FileNotFoundError, ET.ParseError) as exc:
        print(f"Error reading coverage report {args.coverage}: {exc}", file=sys.stderr)
        return 2

    return _evaluate_targets(targets, coverage_map, args.coverage)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

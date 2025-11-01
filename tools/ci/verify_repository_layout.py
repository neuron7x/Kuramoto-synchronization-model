# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Repository layout verification for Stage A of the PR validation pipeline."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


ARTIFACT_DIR = Path(".ci_artifacts")


@dataclass(frozen=True)
class LayoutResult:
    missing: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing


REQUIRED_PATHS: tuple[Path, ...] = (
    Path("core"),
    Path("tacl"),
    Path("infra/terraform"),
    Path("ui/dashboard"),
    Path("ci/release_gates.yml"),
    Path("tacl/link_activator_test_scenarios.yaml"),
)


def evaluate_layout(base_dir: Path, required: Sequence[Path] = REQUIRED_PATHS) -> LayoutResult:
    """Return a ``LayoutResult`` describing which critical paths are missing."""

    missing = []
    for relative in required:
        candidate = base_dir / relative
        if not candidate.exists():
            missing.append(relative.as_posix())
    return LayoutResult(missing=tuple(sorted(missing)))


def write_artifacts(result: LayoutResult, *, artifact_dir: Path = ARTIFACT_DIR) -> None:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = {"passed": result.passed, "missing": list(result.missing)}
    (artifact_dir / "repository_structure.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = ["# Repository structure validation", ""]
    if result.passed:
        lines.append("- ✅ All required paths are present.")
    else:
        lines.append("- ❌ Missing critical paths:")
        lines.extend(f"  - {entry}" for entry in result.missing)
    (artifact_dir / "repository_structure.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify mandatory repository structure")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path.cwd(),
        help="Repository root to inspect (defaults to current working directory)",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = evaluate_layout(args.root)
    write_artifacts(result)
    if not result.passed:
        print("Missing required repository paths:")
        for entry in result.missing:
            print(f" - {entry}")
        return 1
    return 0


def main() -> int:  # pragma: no cover - thin CLI wrapper
    return run()


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())

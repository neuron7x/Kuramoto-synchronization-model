"""Validate that all GitHub Actions are pinned to immutable commit SHAs."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Tuple

import yaml

SHA_PATTERN = r"^[0-9a-fA-F]{40}$"


def _iter_uses_nodes(node) -> Iterable[str]:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "uses":
                if isinstance(value, str):
                    yield value
            else:
                yield from _iter_uses_nodes(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_uses_nodes(item)


def _extract_uses_from_yaml(workflow: Path) -> list[str]:
    documents = list(yaml.safe_load_all(workflow.read_text()))
    uses: list[str] = []
    for doc in documents:
        uses.extend(_iter_uses_nodes(doc))
    return uses


def _extract_uses_from_lines(workflow: Path) -> list[str]:
    import re

    uses: list[str] = []
    in_block = False
    block_indent = 0
    for line in workflow.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue

        indent = len(line) - len(line.lstrip(" "))
        if in_block and indent <= block_indent:
            in_block = False

        if in_block:
            continue

        if re.match(r"^\s*[\w-]+:\s*[>|]", line):
            in_block = True
            block_indent = indent
            continue

        match = re.match(r"^\s*-?\s*uses:\s*(.+)", line)
        if match:
            uses.append(match.group(1).strip())
    return uses


def _normalise_use(value: str) -> tuple[str, str | None] | None:
    candidate = value.strip()
    candidate = candidate.split("#", 1)[0].strip()

    if candidate.startswith("./") or candidate.startswith("../"):
        return None
    if candidate.startswith("docker://"):
        return None
    if "@" not in candidate:
        return (candidate, None)

    target, ref = candidate.split("@", 1)
    return target.strip(), ref.strip()


def find_unpinned_actions(workflows: Iterable[Path]) -> List[Tuple[Path, str]]:
    """Return a list of (workflow_path, uses_value) for unpinned actions."""
    findings: List[Tuple[Path, str]] = []

    for workflow in workflows:
        if not workflow.is_file():
            continue
        try:
            uses_values = _extract_uses_from_yaml(workflow)
        except Exception:
            uses_values = _extract_uses_from_lines(workflow)

        for uses_value in uses_values:
            parsed = _normalise_use(uses_value)
            if parsed is None:
                continue
            target, ref = parsed
            if ref is None or (
                not Path(target).is_absolute() and not _ref_is_sha(ref)
            ):
                findings.append((workflow, uses_value))
    return findings


def _ref_is_sha(ref: str) -> bool:
    import re

    return re.fullmatch(SHA_PATTERN, ref) is not None


def _discover_workflow_files(root: Path) -> list[Path]:
    candidates = sorted(root.glob("**/*.yml")) + sorted(root.glob("**/*.yaml"))
    return [path for path in candidates if "archive" not in path.parts]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fail if any GitHub Action reference is not pinned to a commit SHA.",
    )
    parser.add_argument(
        "--workflows",
        type=Path,
        default=Path(".github/workflows"),
        help="Path containing workflow YAML files.",
    )
    parser.add_argument(
        "--fail-on-unpinned",
        action="store_true",
        help="Exit with non-zero status when unpinned actions are found.",
    )
    args = parser.parse_args()

    workflow_files = _discover_workflow_files(args.workflows)
    findings = find_unpinned_actions(workflow_files)

    if findings:
        print("Found unpinned GitHub Actions references:")
        for path, ref in findings:
            print(f"  - {path}: {ref}")
        if args.fail_on_unpinned:
            return 1
    else:
        print("All GitHub Actions are pinned to commit SHAs.")

    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Dynamic traceability helpers for BBB-NVU tests."""

from __future__ import annotations

import ast
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS_DIR = ROOT / "tests"
GENERATED_MATRIX = ROOT / "docs" / "generated_traceability_matrix.csv"
TraceabilityRow = tuple[str, str, int]


def requirement_decorators(test_file: Path) -> list[TraceabilityRow]:
    """Return (requirement_id, test_name, line) tuples from @requirement decorators."""
    tree = ast.parse(test_file.read_text(encoding="utf-8"), filename=str(test_file))
    rows: list[TraceabilityRow] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Name)
                and decorator.func.id == "requirement"
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
                and isinstance(decorator.args[0].value, str)
            ):
                rel = test_file.relative_to(ROOT).as_posix()
                rows.append((decorator.args[0].value, f"{rel}::{node.name}", node.lineno))
    return sorted(rows)


def collect_traceability() -> list[TraceabilityRow]:
    """Collect dynamic traceability rows from tests."""
    rows: list[TraceabilityRow] = []
    for test_file in sorted(TESTS_DIR.glob("test_*.py")):
        rows.extend(requirement_decorators(test_file))
    return sorted(rows)


def write_generated_matrix(path: Path = GENERATED_MATRIX) -> None:
    """Write the generated traceability CSV."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["requirement_id", "test", "line"])
        writer.writerows(collect_traceability())


def _read_csv_row(row: dict[str, str | None]) -> TraceabilityRow:
    requirement_id = row.get("requirement_id")
    test = row.get("test")
    line = row.get("line")
    if requirement_id is None or test is None or line is None:
        raise ValueError("traceability matrix row has missing fields")
    return requirement_id, test, int(line)


def read_generated_matrix(path: Path = GENERATED_MATRIX) -> list[TraceabilityRow]:
    """Read generated traceability rows from disk."""
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return sorted(_read_csv_row(row) for row in reader)


if __name__ == "__main__":
    write_generated_matrix()

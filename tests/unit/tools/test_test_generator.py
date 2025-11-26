"""Tests for the automated test generation utilities."""

from __future__ import annotations

import importlib
import sys
import textwrap
from pathlib import Path
from types import ModuleType
from typing import Dict, Iterable, Tuple

import pytest

from tools.testing.test_generator import (
    analyze_component,
    analyze_module,
    generate_unit_tests,
)


@pytest.fixture()
def sample_module(tmp_path: Path) -> Iterable[Tuple[str, Path]]:
    """Provide a temporary module with predictable behaviour for analysis."""

    package_name = "autogen_pkg"
    module_name = f"{package_name}.pricing"
    package_dir = tmp_path / package_name
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    module_path = package_dir / "pricing.py"
    module_path.write_text(
        textwrap.dedent(
            '''
            """Sample pricing utilities."""

            from __future__ import annotations

            def normalize_prices(data: list[float]) -> list[float]:
                """Normalize the sequence so that its sum equals 1."""

                total = sum(data)
                normalized: list[float] = []
                for value in data:
                    if total == 0:
                        normalized.append(0.0)
                    else:
                        normalized.append(value / total)
                return normalized

            class PriceScaler:
                """Rescales prices by a constant multiplier."""

                def __init__(self, multiplier: float) -> None:
                    self._multiplier = multiplier

                def scale(self, price: float) -> float:
                    return price * self._multiplier
            '''
        ),
        encoding="utf-8",
    )

    sys.path.insert(0, str(tmp_path))
    importlib.invalidate_caches()
    yield module_name, module_path

    sys.path.remove(str(tmp_path))
    for key in list(sys.modules):
        if key == module_name or key.startswith(f"{package_name}."):
            sys.modules.pop(key, None)
    sys.modules.pop(package_name, None)


def test_analyze_module_returns_structured_components(
    sample_module: Tuple[str, Path],
) -> None:
    module_name, module_path = sample_module
    analysis = analyze_module(module_name)

    assert analysis.module == module_name
    assert analysis.path == module_path

    component_names = {component.name for component in analysis.components}
    assert component_names == {"normalize_prices", "PriceScaler"}

    normalize = analyze_component(module_name, "normalize_prices")
    assert normalize.kind == "function"
    assert "conditional branching" in normalize.explanation
    assert "iterates over sequences" in normalize.explanation

    scaler = analyze_component(module_name, "PriceScaler")
    assert scaler.kind == "class"
    assert "inherits from object" in scaler.explanation
    assert "Key behaviours" in scaler.explanation


def test_generate_unit_tests_produces_runnable_pytest_file(
    sample_module: Tuple[str, Path], tmp_path: Path
) -> None:
    module_name, _ = sample_module
    output_dir = tmp_path / "generated"
    output_path = generate_unit_tests(module_name, output_dir)

    assert output_path.exists()

    compiled = compile(
        output_path.read_text(encoding="utf-8"), str(output_path), "exec"
    )
    namespace: Dict[str, ModuleType | object] = {}
    exec(compiled, namespace)

    test_functions = [
        value
        for key, value in namespace.items()
        if key.startswith("test_") and callable(value)
    ]
    assert test_functions, "expected generated test functions"

    for test in test_functions:
        test()

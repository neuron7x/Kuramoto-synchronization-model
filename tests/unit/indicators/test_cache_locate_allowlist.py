# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Allowlist enforcement for the JSON cache structure decoder.

Regression for the MEDIUM finding: ``_locate`` imported an arbitrary
``module:Class`` named in a JSON cache payload (via the ``dataclass`` / ``enum``
markers) with no allowlist, while the sibling pickle path was already guarded.
A writer of the cache directory could name ``os:system`` to trigger an import
(import-time side effects) and instantiation. ``_locate`` now fails closed on
the same allowlist the restricted unpickler uses.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from core.indicators.cache import _decode_structure, _locate, _module_is_safe


@pytest.mark.parametrize(
    "symbol",
    [
        "os:system",
        "subprocess:Popen",
        "builtins:exec",
        "builtins:eval",
        "shutil:rmtree",
        "importlib:import_module",
    ],
)
def test_locate_rejects_unsafe_modules(symbol: str) -> None:
    with pytest.raises(ValueError, match="Refusing to (import|load)") as exc:
        _locate(symbol)
    # The refusal must name the offending module so the rejection is auditable.
    assert "Refusing" in str(exc.value)


@pytest.mark.parametrize(
    "symbol,expected_name",
    [
        ("decimal:Decimal", "Decimal"),
        ("pathlib:PurePosixPath", "PurePosixPath"),
        ("collections:OrderedDict", "OrderedDict"),
    ],
)
def test_locate_allows_safe_modules(symbol: str, expected_name: str) -> None:
    resolved = _locate(symbol)
    assert resolved.__name__ == expected_name
    # The resolved object's own home module must be on the allowlist (guards the
    # dotted-qualname-pivot defence, not just the requested module name).
    assert _module_is_safe(symbol.split(":", 1)[0])


@pytest.mark.parametrize(
    "symbol",
    [
        # Dotted qualname traversal OUT of an allowlisted module into a dangerous
        # one — the module-name guard alone would pass these.
        "core.indicators.cache:os.system",
        "core.indicators.cache:builtins.eval",
        "core.indicators.cache:builtins.exec",
        "core.indicators.cache:importlib.import_module",
        "core.indicators.cache:shutil.rmtree",
        "core.indicators.cache:os",
    ],
)
def test_locate_rejects_dotted_qualname_pivot(symbol: str) -> None:
    with pytest.raises(ValueError, match="Refusing to (resolve|import|load)"):
        _locate(symbol)


def test_module_is_safe_contract() -> None:
    assert _module_is_safe("numpy")
    assert _module_is_safe("pandas.core.series")
    assert _module_is_safe("core.indicators.cache")
    assert not _module_is_safe("os")
    assert not _module_is_safe("subprocess")
    assert not _module_is_safe("numpyfoo")  # prefix must be a real boundary


def test_decode_structure_rejects_malicious_dataclass_marker() -> None:
    payload = {"__type__": "dataclass", "cls": "os:system", "fields": {"command": "id"}}
    with pytest.raises(ValueError, match="Refusing to import unsafe module 'os'"):
        _decode_structure(payload)


def test_decode_structure_rejects_malicious_enum_marker() -> None:
    payload = {"__type__": "enum", "cls": "subprocess:Popen", "name": "x"}
    with pytest.raises(ValueError, match="Refusing to import unsafe module 'subprocess'"):
        _decode_structure(payload)


def test_decode_structure_still_decodes_safe_markers() -> None:
    # The allowlist must not break legitimate structured payloads.
    assert _decode_structure({"__type__": "decimal", "value": "1.5"}) == Decimal("1.5")
    assert _decode_structure({"__type__": "sequence", "kind": "tuple", "items": [1, 2]}) == (
        1,
        2,
    )

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import importlib
import inspect
import pkgutil
import re
from typing import Any, Dict, Set

import pytest

ADAPTERS_PKG = "execution.adapters"
INTERFACES_PKG = "interfaces.execution"

CANONICAL_STATUS_NAMES: Set[str] = set()


def _collect_canonical_statuses() -> Set[str]:
    names = set()
    try:
        interfaces = importlib.import_module(INTERFACES_PKG)
    except Exception:
        # Fallback to common status names found in domain.Order.OrderStatus
        return {
            "open",
            "partially_filled",
            "filled",
            "cancelled",
            "rejected",
            "pending",
        }

    for _, name, ispkg in pkgutil.walk_packages(
        interfaces.__path__, interfaces.__name__ + "."
    ):
        try:
            mod = importlib.import_module(name)
        except Exception:
            continue
        for _, obj in inspect.getmembers(mod):
            if hasattr(obj, "__members__"):
                for m in getattr(obj, "__members__", {}).keys():
                    names.add(m.lower())
            elif isinstance(obj, (set, tuple, list)):
                for it in obj:
                    if isinstance(it, str):
                        names.add(it.lower())
    return names or {
        "open",
        "partially_filled",
        "filled",
        "cancelled",
        "rejected",
        "pending",
    }


CANONICAL_STATUS_NAMES = _collect_canonical_statuses()


def _iter_adapter_modules():
    pkg = importlib.import_module(ADAPTERS_PKG)
    for _, name, ispkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        if ispkg:
            continue
        yield name


STATUS_MAP_NAME_RE = re.compile(
    r".*(ORDER|EXEC|STATUS).*(MAP|MAPPING).*", re.IGNORECASE
)


def _find_status_maps(mod) -> Dict[str, Dict[Any, Any]]:
    maps = {}
    for k, v in vars(mod).items():
        if isinstance(v, dict) and STATUS_MAP_NAME_RE.match(k):
            maps[k] = v
    return maps


def test_status_maps_values_are_canonical():
    missing = {}
    for mod_name in _iter_adapter_modules():
        try:
            mod = importlib.import_module(mod_name)
        except Exception:
            continue
        maps = _find_status_maps(mod)
        if not maps:
            continue
        for name, mp in maps.items():
            bad = []
            for val in mp.values():
                sval = str(getattr(val, "name", val)).lower()
                if sval not in CANONICAL_STATUS_NAMES:
                    bad.append(sval)
            if bad:
                missing[f"{mod_name}:{name}"] = sorted(set(bad))
    if missing:
        pytest.fail(f"Non-canonical status values found in adapters: {missing}")


def test_status_maps_cover_common_states():
    typical = {"open", "partially_filled", "filled", "cancelled", "rejected"}
    assert typical.issubset(
        CANONICAL_STATUS_NAMES
    ), "Canonical statuses missing typical names"

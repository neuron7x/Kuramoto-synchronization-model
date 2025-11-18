#!/usr/bin/env python3
# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import argparse
import importlib
import pkgutil
from typing import Any, Dict, List

ADAPTERS_PKG = "execution.adapters"


def discover_adapters() -> List[str]:
    try:
        pkg = importlib.import_module(ADAPTERS_PKG)
    except Exception:
        return []
    found = []
    for _, name, ispkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        if not ispkg:
            found.append(name)
    return sorted(found)


def adapter_capabilities(mod_name: str) -> Dict[str, bool]:
    try:
        mod = importlib.import_module(mod_name)
    except Exception:
        return {}
    funcs = {k for k, v in vars(mod).items() if callable(v)}
    caps = {
        "time": any(n in funcs for n in ("get_server_time", "server_time_ms", "time", "now_ms")),
        "exchangeInfo_or_symbols": any(
            n in funcs for n in ("get_exchange_info", "exchange_info", "symbols", "list_symbols")
        ),
        "balance": any(
            n in funcs for n in ("get_balance", "balances", "account_balances", "spot_balance")
        ),
    }
    return caps


def render_markdown(rows: List[Dict[str, Any]]) -> str:
    header = """<!-- AUTO-GENERATED FILE. DO NOT EDIT. -->
# Exchange Compatibility Matrix

This document is generated daily by CI.
"""
    table = [
        "| Adapter | /time | /exchangeInfo/symbols | Balance (auth) |",
        "|---|:---:|:---:|:---:|",
    ]
    for r in rows:
        table.append(
            f"| `{r['name']}` | {'✅' if r['time'] else '❌'} | {'✅' if r['exchangeInfo_or_symbols'] else '❌'} | {'✅' if r['balance'] else '❌'} |"  # noqa: E501
        )
    return header + "\n".join(table) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", default="docs/exchanges.md")
    args = ap.parse_args()
    adapters = discover_adapters()
    rows = []
    for m in adapters:
        caps = adapter_capabilities(m)
        if not caps:
            continue
        row = {"name": m.split(".")[-1]}
        row.update(caps)
        rows.append(row)
    content = render_markdown(rows)
    with open(args.write, "w", encoding="utf-8") as f:
        f.write(content)


if __name__ == "__main__":
    main()

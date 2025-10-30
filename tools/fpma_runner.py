# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import argparse
import json
from pathlib import Path

from tools.vendor.fpma.algos.complexity import scan_complexity
from tools.vendor.fpma.algos.graph import build_dep_graph, export_graphviz


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["graph", "check"])
    p.add_argument("--out-dot", default="tools/dep_graph.dot")
    p.add_argument("--out-json", default="reports/complexity.json")
    args = p.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.cmd == "graph":
        g = build_dep_graph(root)
        dot = export_graphviz(g)
        Path(args.out_dot).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_dot).write_text(dot, encoding="utf-8")
        print(f"Wrote {args.out_dot}")
    else:
        res = scan_complexity(root)
        Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out_json).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(json.dumps(res))


if __name__ == "__main__":
    main()

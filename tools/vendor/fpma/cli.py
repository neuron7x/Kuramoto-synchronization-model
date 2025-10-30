# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import argparse
import json
from pathlib import Path

from .algos.complexity import scan_complexity
from .algos.graph import build_dep_graph, export_graphviz, find_cycles
from .algos.invariants import check_invariants
from .generators.add_fu import add_fu
from .generators.init_repo import init_repo

BANNER = "FPM-A: Fractal Project Method - Algorithmic Edition"


def main():
    parser = argparse.ArgumentParser(prog="fpma", description=BANNER)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser(
        "init", help="Initialize a new fractal monorepo (Bazel-based by default)."
    )
    p_init.add_argument(
        "--name",
        required=True,
        help="Repository name (directory will be created if missing).",
    )
    p_init.add_argument(
        "--license", default="MIT", help="License identifier (default: MIT)."
    )
    p_init.add_argument(
        "--ci", action="store_true", help="Install GitHub Actions workflows."
    )
    p_init.add_argument(
        "--no-bazel", action="store_true", help="Skip Bazel skeleton (not recommended)."
    )

    p_fu = sub.add_parser("add-fu", help="Add a Fractal Unit (FU) to the repo.")
    p_fu.add_argument("--path", required=True, help="Path to repo root.")
    p_fu.add_argument("--name", required=True, help="FU name, e.g., payments")
    p_fu.add_argument(
        "--domain", default="domains", help="Top-level domain folder (domains|libs)."
    )
    p_fu.add_argument(
        "--lang",
        choices=["python", "node"],
        default="python",
        help="Implementation language.",
    )
    p_fu.add_argument(
        "--with-openapi",
        action="store_true",
        help="Include OpenAPI 3.1 contract in api/.",
    )

    p_graph = sub.add_parser(
        "graph", help="Build dependency graph (imports) across FUs."
    )
    p_graph.add_argument("--path", required=True, help="Path to repo root.")
    p_graph.add_argument(
        "--out-dot", default="tools/dep_graph.dot", help="DOT file output path."
    )
    p_graph.add_argument("--stdout", action="store_true", help="Print DOT to stdout.")

    p_check = sub.add_parser(
        "check", help="Run algorithmic checks (invariants, cycles, complexity)."
    )
    p_check.add_argument("--path", required=True, help="Path to repo root.")
    p_check.add_argument(
        "--max-cyc",
        type=int,
        default=10,
        help="Max cyclomatic complexity per function.",
    )
    p_check.add_argument(
        "--fail-on",
        choices=["any", "cycles", "imports", "complexity"],
        default="any",
        help="Failing policy.",
    )
    p_check.add_argument("--json", action="store_true", help="Emit JSON report.")

    args = parser.parse_args()

    if args.cmd == "init":
        init_repo(
            args.name,
            license_id=args.license,
            include_ci=args.ci,
            include_bazel=not args.no_bazel,
        )
        print(f"Initialized FPM-A repo at {args.name}")
        return 0

    if args.cmd == "add-fu":
        add_fu(
            Path(args.path),
            args.name,
            args.domain,
            args.lang,
            with_openapi=args.with_openapi,
        )
        print(f"Added FU: {args.domain}/{args.name}")
        return 0

    if args.cmd == "graph":
        graph = build_dep_graph(Path(args.path))
        dot = export_graphviz(graph)
        out_path = Path(args.path) / args.out_dot
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(dot, encoding="utf-8")
        if args.stdout:
            print(dot)
        else:
            print(f"Wrote {out_path}")
        return 0

    if args.cmd == "check":
        root = Path(args.path)
        graph = build_dep_graph(root)
        cycles = find_cycles(graph)
        inv_violations = list(check_invariants(root, graph))
        cmplx = scan_complexity(root)
        report = {
            "cycles": cycles,
            "invariant_violations": [vars(v) for v in inv_violations],
            "complexity": cmplx,
        }
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            if cycles:
                print("CYCLES DETECTED:")
                for c in cycles:
                    print("  -", " -> ".join(c))
            if inv_violations:
                print("INVARIANT VIOLATIONS:")
                for v in inv_violations:
                    print(f"  - {v.rule}: {v.detail} ({v.path})")
            print("COMPLEXITY SUMMARY:")
            print(
                f"  functions_scanned={report['complexity']['functions_scanned']} max={report['complexity']['max']} avg={report['complexity']['avg']:.2f}"
            )
        fail = False
        if args.fail_on == "cycles" and cycles:
            fail = True
        elif args.fail_on == "imports" and inv_violations:
            fail = True
        elif (
            args.fail_on == "complexity" and report["complexity"]["max"] > args.max_cyc
        ):
            fail = True
        elif args.fail_on == "any" and (
            cycles or inv_violations or report["complexity"]["max"] > args.max_cyc
        ):
            fail = True
        return 1 if fail else 0

    return 0

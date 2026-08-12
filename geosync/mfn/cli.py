# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""MFN integration command-line interface."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from . import pipeline
from .contract import MFN_COMMANDS, MFNContract

DEFAULT_OUT = Path("artifacts") / "runs" / "mfn_integration"
MIN_POINTS = 4


def _points(value: str) -> int:
    try:
        points = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("points must be an integer") from exc
    if points < MIN_POINTS:
        raise argparse.ArgumentTypeError(f"points must be >= {MIN_POINTS}")
    return points


def _print_artifacts(artifacts: dict[str, Path]) -> None:
    print(f"output_bundle={artifacts.get('bundle', DEFAULT_OUT)}")
    for name, path in artifacts.items():
        if name == "bundle":
            continue
        print(f"{name}={path}")
    if "manifest" in artifacts:
        print(f"first_file_to_open={artifacts['manifest']}")


def _run_stage(args: argparse.Namespace, stage: Callable[..., Path], name: str) -> int:
    contract = MFNContract(seed=args.seed)
    if name == "simulate":
        path = stage(args.out, seed=args.seed, points=args.points, contract=contract)
    else:
        path = stage(args.out, contract=contract)
    manifest, sha_manifest = pipeline.write_manifests(args.out, [path])
    _print_artifacts(
        {"bundle": args.out, name: path, "manifest": manifest, "sha256_manifest": sha_manifest}
    )
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    artifacts = pipeline.run_all(args.out, seed=args.seed, points=args.points)
    artifacts["bundle"] = args.out
    _print_artifacts(artifacts)
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    errors = pipeline.validate_bundle(args.bundle)
    if errors:
        for error in errors:
            print(f"mfn-validate: {error}", file=sys.stderr)
        return 1
    print(f"validated_bundle={args.bundle}")
    print(f"first_file_to_open={args.bundle / 'manifest.json'}")
    return 0


def _cmd_api(args: argparse.Namespace) -> int:
    payload = {
        "schema_version": "mfn.api.v1",
        "commands": list(MFN_COMMANDS),
        "default_bundle": str(DEFAULT_OUT),
        "min_points": MIN_POINTS,
        "status": "INSTRUMENTED",
    }
    if args.format == "json":
        import json

        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("MFN API v1")
        print(f"schema_version={payload['schema_version']}")
        print("status=INSTRUMENTED")
        print(f"default_bundle={payload['default_bundle']}")
        print(f"min_points={payload['min_points']}")
        print("commands=" + ",".join(payload["commands"]))
    return 0


def build_parser(*, api_mode: bool = False, validate_mode: bool = False) -> argparse.ArgumentParser:
    """Build the MFN parser."""

    parser = argparse.ArgumentParser(
        prog="mfn-api" if api_mode else "mfn-validate" if validate_mode else "mfn",
        description="Dependency-light MFN integration artifact runner.",
    )
    if api_mode:
        parser.add_argument("--format", choices=("text", "json"), default="text")
        parser.set_defaults(func=_cmd_api)
        return parser
    if validate_mode:
        parser.add_argument("--bundle", type=Path, default=DEFAULT_OUT)
        parser.set_defaults(func=_cmd_validate)
        return parser

    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output bundle directory.")
    parser.add_argument("--seed", type=int, default=1337, help="Deterministic synthetic seed.")
    parser.add_argument("--points", type=_points, default=16, help="Number of simulated observations.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run", help="Run simulate→extract→detect→forecast→compare→report."
    )
    run_parser.set_defaults(func=_cmd_run)

    validate_parser = subparsers.add_parser("validate", help="Validate an MFN output bundle.")
    validate_parser.add_argument("--bundle", type=Path, default=None)
    validate_parser.set_defaults(func=lambda args: _cmd_validate(_with_bundle_default(args)))

    stage_map = {
        "simulate": pipeline.simulate,
        "extract": pipeline.extract,
        "detect": pipeline.detect,
        "forecast": pipeline.forecast,
        "compare": pipeline.compare,
        "report": pipeline.report,
    }
    for name, func in stage_map.items():
        stage_parser = subparsers.add_parser(name, help=f"Run the {name} stage.")
        stage_parser.set_defaults(
            func=lambda args, stage=func, stage_name=name: _run_stage(args, stage, stage_name)
        )
    return parser


def _with_bundle_default(args: argparse.Namespace) -> argparse.Namespace:
    if args.bundle is None:
        args.bundle = args.out
    return args


def _dispatch(args: argparse.Namespace, *, prog: str) -> int:
    try:
        return int(args.func(args))
    except (FileNotFoundError, ValueError, KeyError, TypeError) as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return _dispatch(args, prog="mfn")


def api_main(argv: list[str] | None = None) -> int:
    parser = build_parser(api_mode=True)
    args = parser.parse_args(argv)
    return _dispatch(args, prog="mfn-api")


def validate_main(argv: list[str] | None = None) -> int:
    parser = build_parser(validate_mode=True)
    args = parser.parse_args(argv)
    return _dispatch(args, prog="mfn-validate")


if __name__ == "__main__":
    raise SystemExit(main())

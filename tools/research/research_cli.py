#!/usr/bin/env python3
"""Canonical GeoSync research gateway.

The gateway intentionally does only two things:

* ``run`` is a **provenance stamp only**. It records dataset/config hashes, git
  state, seed, and window into a schema-valid artifact at the ``HYPOTHESIS``
  tier with ``falsification_status="NOT_RUN"``. It runs **no** empirical Ricci
  inference, so ``score``/``uncertainty`` are inert placeholders — never read
  them as a measured result. Promotion past ``HYPOTHESIS`` requires a real,
  hash-pinned session evaluated through the falsification gates (see
  ``research_lines/ricci_microstructure_v1/contract.yaml``).
* ``verify`` validates an artifact path or run directory against the canonical
  JSON schema.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from tools.research.validate_ricci_artifact_schema import DEFAULT_SCHEMA, validate_artifact

DEFAULT_RUN_ID = "RFC-2026-MARKET-RICCI-V1"
DEFAULT_TIMESTAMP_UTC = "1970-01-01T00:00:00Z"
UTC_Z_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _die(message: str) -> NoReturn:
    print(f"geosync-research: {message}", file=sys.stderr)
    raise SystemExit(1)


def _validate_timestamp_utc(timestamp_utc: str) -> str:
    try:
        parsed = datetime.strptime(timestamp_utc, UTC_Z_FORMAT)
    except ValueError:
        _die(f"timestamp must be UTC in YYYY-MM-DDTHH:MM:SSZ form: {timestamp_utc!r}")
    return parsed.strftime(UTC_Z_FORMAT)


def _reject_symlink(path: Path, *, role: str) -> None:
    if path.is_symlink():
        _die(f"refusing symlinked {role}: {path}")


def _is_regular_file(path: Path) -> bool:
    try:
        return path.is_file() and not path.is_symlink()
    except OSError:
        return False


def _sha256_path(path: Path) -> str:
    _reject_symlink(path, role="input path")
    if not path.exists():
        _die(f"missing input path: {path}")
    digest = hashlib.sha256()
    if _is_regular_file(path):
        digest.update(path.read_bytes())
        return digest.hexdigest()
    if not path.is_dir():
        _die(f"unsupported input path type: {path}")
    for child in sorted(path.rglob("*")):
        _reject_symlink(child, role="input tree member")
        if not child.is_file():
            continue
        digest.update(child.relative_to(path).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(child.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _git_sha() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if completed.returncode == 0 and len(value) == 40:
        return value
    return "0" * 40


def _git_dirty() -> bool:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        return True
    return bool(completed.stdout.strip())


def _resolve_artifact_path(path: Path) -> Path:
    if path.is_dir():
        candidate = path / "artifact.json"
        if candidate.is_file():
            return candidate
        json_candidates = sorted(path.glob("*.json"))
        if len(json_candidates) == 1:
            return json_candidates[0]
        _die(f"directory must contain artifact.json or exactly one JSON artifact: {path}")
    return path


def _write_json(path: Path, payload: dict[str, object], *, force: bool = False) -> None:
    if path.exists() and not force:
        _die(f"refusing to overwrite existing artifact without --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _run(args: argparse.Namespace) -> int:
    if args.line != "ricci_microstructure_v1":
        _die(f"unsupported research line: {args.line}")

    timestamp_utc = _validate_timestamp_utc(args.timestamp_utc)
    run_id = args.run_id
    run_dir = args.out / run_id
    artifact_path = run_dir / "artifact.json"
    payload: dict[str, object] = {
        "conforms_to": (
            "https://schemas.neuron7xlab.org/research/research_inference_artifact.schema.json"
        ),
        "schema_version": "1.0.0",
        # research_line is the line identity (e.g. 'ricci_microstructure'); strip the
        # trailing _v<N> revision suffix the CLI uses for the line argument.
        "research_line": args.line.rsplit("_v", 1)[0],
        "run_id": run_id,
        "git_sha": _git_sha(),
        "git_dirty": _git_dirty(),
        "data_sha256": _sha256_path(args.data),
        "config_sha256": _sha256_path(args.config),
        "seed": args.seed,
        "timestamp_utc": timestamp_utc,
        "input_window_sec": args.input_window_sec,
        # Inert placeholders — this gateway computes no empirical inference.
        # score/uncertainty are NOT measured values; falsification is NOT_RUN.
        "score": 0.0,
        "uncertainty": 0.0,
        "decision": "OBSERVE",
        "claim_tier": "HYPOTHESIS",
        "falsification_status": "NOT_RUN",
    }
    _write_json(artifact_path, payload, force=args.force)

    errors = validate_artifact(args.schema, artifact_path)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1

    print(json.dumps({"artifact": artifact_path.as_posix(), "schema_valid": True}, sort_keys=True))
    return 0


def _verify(args: argparse.Namespace) -> int:
    artifact_path = _resolve_artifact_path(args.artifact)
    errors = validate_artifact(args.schema, artifact_path)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(json.dumps({"artifact": artifact_path.as_posix(), "schema_valid": True}, sort_keys=True))
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="geosync-research", description=__doc__)
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Create a canonical Ricci artifact")
    run_parser.add_argument("--line", required=True)
    run_parser.add_argument("--config", type=Path, required=True)
    run_parser.add_argument("--data", type=Path, required=True)
    run_parser.add_argument("--out", type=Path, required=True)
    run_parser.add_argument("--run-id", default=DEFAULT_RUN_ID)
    run_parser.add_argument("--seed", type=int, default=1337)
    run_parser.add_argument("--timestamp-utc", default=DEFAULT_TIMESTAMP_UTC)
    run_parser.add_argument("--input-window-sec", type=int, default=30)
    run_parser.add_argument(
        "--force", action="store_true", help="Overwrite an existing run artifact."
    )
    run_parser.set_defaults(func=_run)

    verify_parser = subparsers.add_parser("verify", help="Validate an artifact or run directory")
    verify_parser.add_argument("artifact", type=Path)
    verify_parser.set_defaults(func=_verify)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

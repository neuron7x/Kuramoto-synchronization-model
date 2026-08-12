#!/usr/bin/env python3
"""GeoSync ricci_microstructure_v1 empirical lane CLI.

Distinct from tools/research/research_cli.py (the canonical RFC-2026 inference
contract CLI, argparse-based, emits HYPOTHESIS/NOT_RUN artifacts). This module is
the EMPIRICAL Ollivier-Ricci-on-L2 lane runner (Typer-based): it ingests real L2
order-book data, runs the surrogate falsification battery, and writes/verifies a
ricci_microstructure_artifact.v1 artifact.

Commands and exit codes:
- ingest: validate real L2 data from a l2_manifest.v1 manifest. Exits 0 on validated output,
  exits 1 on schema/data/provenance failure.
- run: execute a research line from validated data/config. Supports --dry-run, --seed,
  --config, --data and --out. Exits 0 only after artifact schema validation.
- verify: validate one run directory, RUN_ID under artifacts/runs, or artifact JSON path.
  Exits 0 on schema-valid artifact, exits 1 on missing/invalid field.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import NoReturn

try:
    import typer
except Exception:  # pragma: no cover - project dependency should provide Typer
    typer = None

from geosync_research.lines.ricci_microstructure_v1.artifact import verify_artifact
from geosync_research.lines.ricci_microstructure_v1.ingest import ingest_manifest
from geosync_research.lines.ricci_microstructure_v1.runner import run_pipeline

app = typer.Typer(help=__doc__) if typer is not None else None


def _die(message: str) -> NoReturn:
    print(f"geosync-research: {message}", file=sys.stderr)
    raise SystemExit(1)


if typer is not None:

    @app.command()
    def ingest(
        data: Path = typer.Option(..., "--data", help="Path to l2_manifest.v1 JSON."),
        out: Path | None = typer.Option(
            None, "--out", help="Output directory; defaults to manifest dir."
        ),
    ) -> None:
        """Validate real L2 order-book data and materialize deterministic parquet output."""
        try:
            outputs = ingest_manifest(data, out_dir=out)
        except Exception as exc:
            _die(str(exc))
        print(json.dumps({name: path.as_posix() for name, path in outputs.items()}, sort_keys=True))

    @app.command()
    def run(
        line: str = typer.Option(
            ..., "--line", help="Research line; must be ricci_microstructure_v1."
        ),
        config: Path = typer.Option(..., "--config", help="JSON config path."),
        data: Path = typer.Option(..., "--data", help="Validated parquet/csv data path."),
        out: Path = typer.Option(..., "--out", help="Run output root."),
        seed: int = typer.Option(1337, "--seed", help="Deterministic random seed."),
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Plan the run without writing artifacts."
        ),
    ) -> None:
        """Run Ricci microstructure inference, null baselines, statistical gate, and artifact writing."""
        if line != "ricci_microstructure_v1":
            _die(f"unsupported research line: {line}")
        try:
            result = run_pipeline(
                config_path=config, data_path=data, out_root=out, seed=seed, dry_run=dry_run
            )
        except Exception as exc:
            _die(str(exc))
        print(json.dumps(result, sort_keys=True))

    @app.command()
    def verify(
        run_id: str = typer.Argument(..., help="RUN_ID, run directory, or artifact JSON path."),
    ) -> None:
        """Validate a Ricci microstructure artifact against JSON Schema Draft 2020-12."""
        candidate = Path(run_id)
        if not candidate.exists():
            candidate = Path("artifacts/runs") / run_id
        if candidate.is_dir():
            candidate = candidate / "artifact.json"
        try:
            payload = verify_artifact(candidate)
        except Exception as exc:
            _die(str(exc))
        print(
            json.dumps(
                {
                    "artifact": candidate.as_posix(),
                    "schema_valid": True,
                    "falsification_status": payload["falsification_status"],
                },
                sort_keys=True,
            )
        )


def _fallback_main(argv: list[str]) -> int:
    _die("Typer is required for geosync-research; install project dependencies first")


def main(argv: list[str] | None = None) -> int:
    if typer is None:
        return _fallback_main(sys.argv[1:] if argv is None else argv)
    try:
        app(sys.argv[1:] if argv is None else argv)
    except TypeError:
        app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

"""Command line interface for deterministic code generation."""

import json
from dataclasses import asdict
from pathlib import Path

import click

from . import CodegenEngine, load_config  # noqa: F401 - triggers plugin registration


@click.group()
def cli() -> None:
    """TradePulse code generation orchestration CLI."""


def _load_engine(config_path: Path) -> CodegenEngine:
    config = load_config(config_path)
    return CodegenEngine(config)


@cli.command()
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
@click.option("--task", "tasks", multiple=True, help="Specific task(s) to run")
@click.option("--check", is_flag=True, help="Enable diff-only mode without writing to disk")
def generate(config_path: Path, tasks: tuple[str, ...], check: bool) -> None:
    """Execute one or more generation tasks."""

    engine = _load_engine(config_path)
    summaries = engine.run(tasks=tasks, check=check)
    payload = [
        {
            "task": summary.task_name,
            "updated": summary.updated,
            "output": str(summary.output_path),
            "diagnostics": summary.diagnostics,
            "smoke": [asdict(result) for result in summary.smoke],
        }
        for summary in summaries
    ]
    click.echo(json.dumps(payload, indent=2))


@cli.command()
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
@click.option("--task", "tasks", multiple=True, help="Specific task(s) to inspect")
def status(config_path: Path, tasks: tuple[str, ...]) -> None:
    """Inspect cached fingerprints for tasks."""

    engine = _load_engine(config_path)
    selected = set(tasks) if tasks else None
    response = []
    for task in engine.config.tasks:
        if selected and task.name not in selected:
            continue
        cache_file = engine.cache_dir / f"{task.name}.sha256"
        fingerprint = cache_file.read_text(encoding="utf-8") if cache_file.exists() else None
        response.append({"task": task.name, "fingerprint": fingerprint})
    click.echo(json.dumps(response, indent=2))


if __name__ == "__main__":  # pragma: no cover
    cli()

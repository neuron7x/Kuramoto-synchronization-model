"""Click-based entry point for the TradePulse migration toolkit."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import click

from .config import MigrationSettings
from .manager import MigrationManager
from .validators import ValidationSuite


def _load_settings(config_path: str | None) -> MigrationSettings:
    if config_path:
        return MigrationSettings.load(config_path)
    return MigrationSettings.load(None)


def _resolve_suites(paths: Iterable[str]) -> list[ValidationSuite]:
    suites: list[ValidationSuite] = []
    for path in paths:
        suites.append(ValidationSuite.load(Path(path)))
    return suites


@click.group()
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None)
@click.pass_context
def cli(ctx: click.Context, config_path: Path | None) -> None:
    """Perform guarded database migration operations."""

    settings = _load_settings(str(config_path) if config_path else None)
    ctx.obj = {
        "settings": settings,
        "manager": MigrationManager(settings),
    }


@cli.command()
@click.argument("message")
@click.option("--name", "branch_label", default=None)
@click.option("--version-path", default=None)
@click.option("--manual/--autogenerate", default=False)
@click.pass_context
def generate(
    ctx: click.Context,
    message: str,
    branch_label: str | None,
    version_path: str | None,
    manual: bool,
) -> None:
    """Generate a new Alembic revision with guardrails."""

    manager: MigrationManager = ctx.obj["manager"]
    path = manager.generate_revision(
        message=message,
        autogenerate=not manual,
        branch_label=branch_label,
        version_path=version_path,
    )
    click.echo(f"Revision created: {path}")


@cli.command("dry-run")
@click.option("--target", default="head")
@click.pass_context
def dry_run(ctx: click.Context, target: str) -> None:
    """Render the SQL that would be executed for the target revision."""

    manager: MigrationManager = ctx.obj["manager"]
    outcome = manager.dry_run(target=target)
    click.echo(outcome.details["sql"])
    click.echo(f"SQL artifact: {outcome.details['artifact']}")


@cli.command()
@click.option("--target", default="head")
@click.option("--timebox", type=int, default=None)
@click.option("--validation", "validation_paths", multiple=True)
@click.option("--backup/--no-backup", default=None)
@click.option("--dry-run", is_flag=True, default=False)
@click.pass_context
def upgrade(
    ctx: click.Context,
    target: str,
    timebox: int | None,
    validation_paths: tuple[str, ...],
    backup: bool | None,
    dry_run: bool,
) -> None:
    """Upgrade database to the specified revision."""

    manager: MigrationManager = ctx.obj["manager"]
    suites = _resolve_suites(validation_paths)
    result = manager.upgrade(
        target=target,
        timebox_seconds=timebox,
        validation_suites=suites,
        create_backup=backup,
        dry_run=dry_run,
    )
    click.echo(f"Migration success: {result.succeeded}")
    click.echo(result.details)


@cli.command()
@click.argument("target")
@click.pass_context
def downgrade(ctx: click.Context, target: str) -> None:
    """Downgrade database to the target revision."""

    manager: MigrationManager = ctx.obj["manager"]
    result = manager.downgrade(target)
    click.echo(f"Downgrade success: {result.succeeded}")


@cli.command("check-schema")
@click.pass_context
def check_schema(ctx: click.Context) -> None:
    """Validate schema objects such as indexes and triggers."""

    manager: MigrationManager = ctx.obj["manager"]
    report = manager.check_schema()
    click.echo(click.style("Schema check complete", fg="green"))
    click.echo(report)


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current database revision and head."""

    manager: MigrationManager = ctx.obj["manager"]
    current = manager.current()
    click.echo(f"Current revision: {current}")


@cli.command()
@click.option("--target", default="head")
@click.option("--timebox", type=int, default=None)
@click.option("--validation", "validation_paths", multiple=True)
@click.option("--backup/--no-backup", default=None)
@click.option("--apply/--dry-run", "apply_migrations", default=True)
@click.pass_context
def ci(
    ctx: click.Context,
    target: str,
    timebox: int | None,
    validation_paths: tuple[str, ...],
    backup: bool | None,
    apply_migrations: bool,
) -> None:
    """Workflow-friendly command executing dry-run, schema checks, and upgrade validation."""

    manager: MigrationManager = ctx.obj["manager"]
    click.echo("Running dry-run…")
    manager.dry_run(target=target)

    click.echo("Validating schema expectations…")
    schema_report = manager.check_schema()
    click.echo(schema_report)

    suites = _resolve_suites(validation_paths)
    click.echo("Executing upgrade with validations…")
    result = manager.upgrade(
        target=target,
        timebox_seconds=timebox,
        validation_suites=suites,
        create_backup=backup,
        dry_run=not apply_migrations,
    )
    if result.succeeded:
        click.echo(click.style("Migration verified", fg="green"))
    else:
        raise click.ClickException("Migration failed; see artifacts for details")


def main() -> None:
    cli()


if __name__ == "__main__":  # pragma: no cover
    main()

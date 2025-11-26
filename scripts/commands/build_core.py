"""Core module build and release orchestration pipeline."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import argparse
import datetime as dt
import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from packaging.version import InvalidVersion, Version

from core.events import BarEvent, FillEvent, OrderEvent, SignalEvent, TickEvent
from core.messaging.contracts import SchemaContractValidator
from core.messaging.schema_registry import EventSchemaRegistry
from scripts.commands.base import (
    CommandError,
    ensure_tools_exist,
    register,
    run_subprocess,
)

LOGGER = logging.getLogger(__name__)


ReleaseStep = Callable[["BuildPipeline"], None]


@dataclass
class BuildContext:
    """Static configuration shared across release stages."""

    repository_root: Path
    core_path: Path
    schema_registry_dir: Path
    artifact_root: Path
    version_file: Path
    release_type: str | None
    dry_run: bool
    signing_key: str | None
    repository_url: str
    package_name: str
    tag_prefix: str
    skip_publish: bool

    previous_version: Version
    target_version: Version


@dataclass
class BuildState:
    """Mutable release state produced by individual pipeline stages."""

    build_dir: Path | None = None
    dist_files: list[Path] = field(default_factory=list)
    artifact_dir: Path | None = None
    changelog_path: Path | None = None
    tag_name: str | None = None


class BuildPipeline:
    """Transactional execution helper for the build workflow."""

    def __init__(self, context: BuildContext) -> None:
        self.context = context
        self.state = BuildState()
        self._rollbacks: list[Callable[[], None]] = []
        self._cleanups: list[Callable[[], None]] = []

    def run(self, steps: Sequence[ReleaseStep]) -> None:
        try:
            for step in steps:
                LOGGER.info("Running step: %s", step.__name__)
                step(self)
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.error("Build pipeline failed: %s", exc)
            self._perform_rollbacks()
            raise
        else:
            self._perform_cleanups()

    def register_rollback(self, action: Callable[[], None] | None) -> None:
        if action is not None:
            self._rollbacks.insert(0, action)

    def register_cleanup(self, action: Callable[[], None] | None) -> None:
        if action is not None:
            self._cleanups.append(action)

    def _perform_rollbacks(self) -> None:
        LOGGER.info(
            "Initiating automatic rollback across %d step(s)…", len(self._rollbacks)
        )
        for action in self._rollbacks:
            try:
                action()
            except Exception as rollback_error:  # pragma: no cover - defensive
                LOGGER.error("Rollback action failed: %s", rollback_error)

    def _perform_cleanups(self) -> None:
        for action in self._cleanups:
            try:
                action()
            except Exception as cleanup_error:  # pragma: no cover - defensive
                LOGGER.warning("Cleanup action failed: %s", cleanup_error)


def _read_version(version_file: Path) -> Version:
    raw_value = version_file.read_text(encoding="utf-8").strip()
    try:
        return Version(raw_value)
    except InvalidVersion as exc:
        raise CommandError(
            f"Version '{raw_value}' is not a valid semantic version"
        ) from exc


def _bump_version(base: Version, release_type: str) -> Version:
    if release_type == "patch":
        return Version(f"{base.major}.{base.minor}.{base.micro + 1}")
    if release_type == "minor":
        return Version(f"{base.major}.{base.minor + 1}.0")
    if release_type == "major":
        return Version(f"{base.major + 1}.0.0")
    raise CommandError(f"Unsupported release type '{release_type}'")


def _ensure_git_clean(root: Path) -> None:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment guard
        raise CommandError("git executable is required for release automation") from exc
    if result.stdout.strip():
        raise CommandError(
            "Working tree has uncommitted changes. Commit or stash before releasing."
        )


def _ensure_version_ahead(previous: Version, target: Version) -> None:
    if target <= previous:
        raise CommandError(
            f"Target version {target} must be greater than current version {previous}"
        )


def _ensure_tag_absent(root: Path, tag_name: str) -> None:
    try:
        result = subprocess.run(
            ["git", "tag", "--list", tag_name],
            cwd=root,
            check=True,
            stdout=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:  # pragma: no cover - environment guard
        raise CommandError("git executable is required for release automation") from exc
    if result.stdout.strip():
        raise CommandError(
            f"Tag '{tag_name}' already exists. Choose a different version or delete the tag."
        )


def _verify_api_contracts(pipeline: BuildPipeline) -> None:
    context = pipeline.context
    registry = EventSchemaRegistry.from_directory(context.schema_registry_dir)
    validator = SchemaContractValidator(registry)

    model_mapping = {
        "ticks": TickEvent,
        "bars": BarEvent,
        "signals": SignalEvent,
        "orders": OrderEvent,
        "fills": FillEvent,
    }

    for event_type, model in model_mapping.items():
        LOGGER.info("Validating API contract for '%s'", event_type)
        validator.validate_model(event_type, model, version=None)


def _update_version_file(pipeline: BuildPipeline) -> None:
    context = pipeline.context
    previous_text = context.version_file.read_text(encoding="utf-8")
    target_text = f"{context.target_version}\n"
    context.version_file.write_text(target_text, encoding="utf-8")

    def rollback() -> None:
        LOGGER.info("Restoring VERSION file to %s", context.previous_version)
        context.version_file.write_text(previous_text, encoding="utf-8")

    pipeline.register_rollback(rollback)
    if context.dry_run:
        pipeline.register_cleanup(
            lambda: context.version_file.write_text(previous_text, encoding="utf-8")
        )


def _run_linters(pipeline: BuildPipeline) -> None:
    commands: list[Sequence[str]] = [
        ("ruff", "check", str(pipeline.context.core_path)),
        ("black", "--check", str(pipeline.context.core_path)),
        (
            "mypy",
            "--config-file",
            "pyproject.toml",
            str(pipeline.context.core_path),
        ),
    ]

    required = [cmd[0] for cmd in commands]
    ensure_tools_exist(required)

    for command in commands:
        LOGGER.info("Executing %s", command[0])
        run_subprocess(list(command))


def _run_tests(pipeline: BuildPipeline) -> None:
    ensure_tools_exist(["pytest"])
    result = run_subprocess(["pytest", "tests/core", "--maxfail", "1"], check=False)
    if result.returncode != 0:
        raise CommandError("Core test suite failed; aborting release")


def _build_distributions(pipeline: BuildPipeline) -> None:
    context = pipeline.context
    temp_dir = Path(
        tempfile.mkdtemp(prefix="core-build-", dir=str(context.repository_root))
    )
    pipeline.state.build_dir = temp_dir
    pipeline.register_cleanup(lambda: shutil.rmtree(temp_dir, ignore_errors=True))

    try:
        import build  # noqa: F401  # pylint: disable=unused-import
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency guard
        raise CommandError(
            "Python build backend is missing. Install the 'build' package to continue."
        ) from exc

    ensure_tools_exist(["python"])
    run_subprocess(
        [
            "python",
            "-m",
            "build",
            "--wheel",
            "--sdist",
            "--outdir",
            str(temp_dir),
        ],
        cwd=context.core_path,
    )

    pipeline.state.dist_files = sorted(temp_dir.glob("*"))
    if not pipeline.state.dist_files:
        raise CommandError("No build artifacts produced. Check build configuration.")


def _create_minified_archive(pipeline: BuildPipeline) -> None:
    context = pipeline.context
    artifact_dir = context.artifact_root / f"v{context.target_version}"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    pipeline.state.artifact_dir = artifact_dir

    archive_path = artifact_dir / f"core-{context.target_version}.pyz"
    LOGGER.info("Creating optimized zipapp at %s", archive_path)

    def _build_archive() -> None:
        import zipapp

        zipapp.create_archive(
            source=context.core_path,
            target=archive_path,
            compressed=True,
            optimize=2,
        )

    _build_archive()

    def rollback() -> None:
        if archive_path.exists():
            LOGGER.info("Removing generated archive %s", archive_path)
            archive_path.unlink()

    pipeline.register_rollback(rollback)


def _collect_artifacts(pipeline: BuildPipeline) -> None:
    if pipeline.state.artifact_dir is None:
        raise CommandError("Artifact directory is not initialized")

    destination = pipeline.state.artifact_dir
    for artifact in pipeline.state.dist_files:
        target_path = destination / artifact.name
        LOGGER.info("Copying %s -> %s", artifact, target_path)
        shutil.copy2(artifact, target_path)

        def rollback(path: Path = target_path) -> None:
            if path.exists():
                LOGGER.info("Removing artifact %s", path)
                path.unlink()

        pipeline.register_rollback(rollback)


def _sign_artifacts(pipeline: BuildPipeline) -> None:
    context = pipeline.context
    if pipeline.state.artifact_dir is None:
        raise CommandError("Artifacts not prepared for signing")

    if context.dry_run:
        LOGGER.info("Dry-run: skipping cryptographic signing")
        return

    ensure_tools_exist(["gpg"])
    for artifact in pipeline.state.artifact_dir.iterdir():
        if artifact.suffix == ".asc":
            continue
        signature_path = artifact.with_suffix(artifact.suffix + ".asc")
        command: list[str] = ["gpg", "--batch", "--yes", "--armor", "--detach-sign"]
        if context.signing_key:
            command.extend(["--local-user", context.signing_key])
        command.append(str(artifact))
        LOGGER.info("Signing artifact %s", artifact)
        run_subprocess(command)

        def rollback(path: Path = signature_path) -> None:
            if path.exists():
                LOGGER.info("Removing signature %s", path)
                path.unlink()

        pipeline.register_rollback(rollback)


def _generate_changelog(pipeline: BuildPipeline) -> None:
    if pipeline.state.artifact_dir is None:
        raise CommandError("Artifacts directory unavailable for changelog generation")

    ensure_tools_exist(["towncrier"])
    command = [
        "towncrier",
        "build",
        "--yes",
        "--draft",
        "--version",
        str(pipeline.context.target_version),
        "--date",
        dt.date.today().isoformat(),
    ]
    LOGGER.info("Generating changelog via towncrier")
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    changelog_path = pipeline.state.artifact_dir / "CHANGELOG.md"
    changelog_path.write_text(result.stdout, encoding="utf-8")
    pipeline.state.changelog_path = changelog_path

    def rollback() -> None:
        if changelog_path.exists():
            LOGGER.info("Removing generated changelog %s", changelog_path)
            changelog_path.unlink()

    pipeline.register_rollback(rollback)


def _create_git_tag(pipeline: BuildPipeline) -> None:
    context = pipeline.context
    if context.dry_run:
        LOGGER.info("Dry-run: skipping git tagging")
        return

    tag_name = f"{context.tag_prefix}{context.target_version}"
    _ensure_tag_absent(context.repository_root, tag_name)
    message = f"core release {context.target_version}"
    run_subprocess(
        ["git", "tag", "-a", tag_name, "-m", message], cwd=context.repository_root
    )
    pipeline.state.tag_name = tag_name

    def rollback() -> None:
        LOGGER.info("Deleting git tag %s", tag_name)
        run_subprocess(
            ["git", "tag", "-d", tag_name], cwd=context.repository_root, check=False
        )

    pipeline.register_rollback(rollback)


def _publish_to_repository(pipeline: BuildPipeline) -> None:
    context = pipeline.context
    if context.skip_publish:
        LOGGER.info("Publication skipped as requested")
        return
    if pipeline.state.artifact_dir is None:
        raise CommandError("Artifacts are not available for publication")
    if context.dry_run:
        LOGGER.info("Dry-run: skipping publication to %s", context.repository_url)
        return

    ensure_tools_exist(["twine"])
    dist_files = [
        str(path)
        for path in pipeline.state.artifact_dir.iterdir()
        if path.suffix == ".whl" or path.suffixes[-2:] == [".tar", ".gz"]
    ]
    if not dist_files:
        raise CommandError(
            "No wheel or source distribution artifacts found for publishing"
        )

    command = [
        "twine",
        "upload",
        "--repository-url",
        context.repository_url,
        "--skip-existing",
        *dist_files,
    ]
    LOGGER.info("Publishing artifacts to %s", context.repository_url)
    run_subprocess(command)

    def rollback() -> None:
        LOGGER.info("Attempting to yank published version %s", context.target_version)
        yank_command = [
            "twine",
            "yank",
            context.package_name,
            str(context.target_version),
            "--repository-url",
            context.repository_url,
            "--comment",
            "Automated rollback",
        ]
        run_subprocess(yank_command, check=False)

    pipeline.register_rollback(rollback)


def build_parser(
    subparsers: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    parser = subparsers.add_parser(
        "build-core", help="Build, verify, and release the core module"
    )
    parser.set_defaults(command="build-core", handler=handle)
    parser.add_argument(
        "--release-type",
        choices=("patch", "minor", "major"),
        help="Semantic version bump to apply to the VERSION file.",
    )
    parser.add_argument(
        "--new-version",
        help="Explicit semantic version to release (overrides --release-type).",
    )
    parser.add_argument(
        "--repository-url",
        default=os.environ.get(
            "CORE_PACKAGE_REPOSITORY", "https://upload.pypi.org/legacy/"
        ),
        help="Package repository endpoint used for publishing artifacts.",
    )
    parser.add_argument(
        "--package-name",
        default=os.environ.get("CORE_PACKAGE_NAME", "tradepulse-core"),
        help="Package identifier used when performing repository rollbacks.",
    )
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=Path("artifacts/core"),
        help="Directory where build artifacts are stored.",
    )
    parser.add_argument(
        "--schema-registry",
        type=Path,
        default=Path("schemas/events"),
        help="Path to the canonical schema registry for API contract validation.",
    )
    parser.add_argument(
        "--signing-key",
        help="GPG key identifier used for artifact signing.",
    )
    parser.add_argument(
        "--tag-prefix",
        default="core-v",
        help="Prefix used when creating git release tags.",
    )
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Skip publishing artifacts to the configured repository.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Perform validation and artifact generation without mutating remote state.",
    )
    parser.add_argument(
        "--execute",
        dest="dry_run",
        action="store_false",
        help="Perform signing, tagging, and publishing actions.",
    )


@register("build-core")
def handle(args: argparse.Namespace) -> int:
    repository_root = Path.cwd()
    version_file = repository_root / "VERSION"
    if not version_file.exists():
        raise CommandError("VERSION file is missing from repository root")

    previous_version = _read_version(version_file)

    raw_new_version = getattr(args, "new_version", None)
    release_type = getattr(args, "release_type", None)
    if raw_new_version:
        try:
            target_version = Version(raw_new_version)
        except InvalidVersion as exc:
            raise CommandError(
                f"Provided --new-version '{raw_new_version}' is invalid"
            ) from exc
    elif release_type:
        target_version = _bump_version(previous_version, release_type)
    else:
        raise CommandError(
            "Provide either --release-type or --new-version to determine release version"
        )

    _ensure_version_ahead(previous_version, target_version)

    _ensure_git_clean(repository_root)

    artifact_root = getattr(args, "artifact_dir")
    if not artifact_root.is_absolute():
        artifact_root = repository_root / artifact_root

    schema_registry = getattr(args, "schema_registry")
    if not schema_registry.is_absolute():
        schema_registry = repository_root / schema_registry

    context = BuildContext(
        repository_root=repository_root,
        core_path=repository_root / "core",
        schema_registry_dir=schema_registry,
        artifact_root=artifact_root,
        version_file=version_file,
        release_type=release_type,
        dry_run=getattr(args, "dry_run"),
        signing_key=getattr(args, "signing_key", None),
        repository_url=getattr(args, "repository_url"),
        package_name=getattr(args, "package_name"),
        tag_prefix=getattr(args, "tag_prefix"),
        skip_publish=getattr(args, "skip_publish", False),
        previous_version=previous_version,
        target_version=target_version,
    )

    if not context.core_path.exists():
        raise CommandError(f"Core module path not found: {context.core_path}")
    if not context.schema_registry_dir.exists():
        raise CommandError(
            f"Schema registry directory not found: {context.schema_registry_dir}"
        )
    context.artifact_root.mkdir(parents=True, exist_ok=True)

    steps: Sequence[ReleaseStep] = (
        _verify_api_contracts,
        _update_version_file,
        _run_linters,
        _run_tests,
        _build_distributions,
        _create_minified_archive,
        _collect_artifacts,
        _sign_artifacts,
        _generate_changelog,
        _create_git_tag,
        _publish_to_repository,
    )

    pipeline = BuildPipeline(context)
    pipeline.run(steps)

    LOGGER.info("Core module release %s completed successfully", context.target_version)
    return 0

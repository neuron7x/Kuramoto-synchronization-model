# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Build versioning and config provenance for TradePulse.

This module provides version metadata, build information, and configuration
provenance hashing. It ensures reproducibility by tracking the exact
versions and configurations used in any given run.

Key features:
    - Build/version metadata access
    - Config provenance hashing for reproducibility
    - Git commit information extraction
    - Runtime environment fingerprinting
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

LOGGER = logging.getLogger(__name__)

# Default version when package version cannot be determined
DEFAULT_VERSION = "0.0.0-dev"


@dataclass(frozen=True, slots=True)
class GitInfo:
    """Git repository information.

    Attributes:
        commit: Full commit SHA
        short_commit: Short commit SHA (7 chars)
        branch: Current branch name
        tag: Tag name if on a tag, None otherwise
        dirty: True if working tree has uncommitted changes
        commit_date: Commit timestamp
    """

    commit: str
    short_commit: str
    branch: str | None
    tag: str | None
    dirty: bool
    commit_date: datetime | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "commit": self.commit,
            "short_commit": self.short_commit,
            "branch": self.branch,
            "tag": self.tag,
            "dirty": self.dirty,
            "commit_date": self.commit_date.isoformat() if self.commit_date else None,
        }


@dataclass(frozen=True, slots=True)
class BuildMetadata:
    """Complete build metadata.

    Attributes:
        version: Package version string
        git: Git repository information
        python_version: Python interpreter version
        platform: Platform identifier
        build_time: When this metadata was generated
        environment: Build environment identifier (dev/staging/prod)
    """

    version: str
    git: GitInfo | None
    python_version: str
    platform: str
    build_time: datetime
    environment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "version": self.version,
            "git": self.git.to_dict() if self.git else None,
            "python_version": self.python_version,
            "platform": self.platform,
            "build_time": self.build_time.isoformat(),
            "environment": self.environment,
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def _run_git_command(args: list[str], cwd: Path | None = None) -> str | None:
    """Run a git command and return output, or None on failure."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def get_git_info(repo_path: Path | None = None) -> GitInfo | None:
    """Extract git information from the repository.

    Args:
        repo_path: Path to git repository (default: current directory)

    Returns:
        GitInfo if in a git repository, None otherwise
    """
    cwd = repo_path or Path.cwd()

    # Check if in a git repository
    if _run_git_command(["rev-parse", "--git-dir"], cwd) is None:
        return None

    # Get commit SHA
    commit = _run_git_command(["rev-parse", "HEAD"], cwd)
    if not commit:
        return None

    short_commit = commit[:7]

    # Get branch name
    branch = _run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch == "HEAD":
        # Detached HEAD state
        branch = None

    # Get tag if on a tag
    tag = _run_git_command(["describe", "--exact-match", "--tags"], cwd)

    # Check if dirty
    status = _run_git_command(["status", "--porcelain"], cwd)
    dirty = bool(status)

    # Get commit date
    commit_date: datetime | None = None
    date_str = _run_git_command(
        ["show", "-s", "--format=%ci", "HEAD"], cwd
    )
    if date_str:
        try:
            # Parse git date format: "2023-01-15 10:30:45 -0500"
            commit_date = datetime.strptime(
                date_str[:19], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            LOGGER.debug("Failed to parse git commit date: %s", date_str)

    return GitInfo(
        commit=commit,
        short_commit=short_commit,
        branch=branch,
        tag=tag,
        dirty=dirty,
        commit_date=commit_date,
    )


def get_package_version() -> str:
    """Get the installed package version.

    Attempts to read version from:
    1. importlib.metadata
    2. pkg_resources
    3. VERSION file
    4. Fallback to DEFAULT_VERSION

    Returns:
        Version string
    """
    # Try importlib.metadata first (Python 3.8+)
    try:
        from importlib.metadata import version

        return version("tradepulse")
    except Exception:
        pass

    # Try pkg_resources
    try:
        import pkg_resources

        return pkg_resources.get_distribution("tradepulse").version
    except Exception:
        pass

    # Try reading VERSION file
    version_file = Path(__file__).parent.parent / "VERSION"
    if version_file.exists():
        try:
            return version_file.read_text().strip()
        except Exception:
            pass

    return DEFAULT_VERSION


def get_build_metadata(
    environment: str | None = None,
    repo_path: Path | None = None,
) -> BuildMetadata:
    """Get complete build metadata.

    Args:
        environment: Optional environment identifier (dev/staging/prod)
        repo_path: Path to git repository

    Returns:
        BuildMetadata with version and build information
    """
    env = environment or os.environ.get("TRADEPULSE_ENV")

    return BuildMetadata(
        version=get_package_version(),
        git=get_git_info(repo_path),
        python_version=sys.version,
        platform=platform.platform(),
        build_time=datetime.now(timezone.utc),
        environment=env,
    )


@dataclass(frozen=True, slots=True)
class ConfigProvenance:
    """Configuration provenance information for reproducibility.

    Tracks the exact configuration used in a run, enabling
    reproduction and auditing of results.

    Attributes:
        config_hash: SHA-256 hash of the normalized configuration
        config_snapshot: The actual configuration values
        build: Build metadata when config was captured
        timestamp: When provenance was recorded
    """

    config_hash: str
    config_snapshot: Mapping[str, Any]
    build: BuildMetadata
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "config_hash": self.config_hash,
            "config_snapshot": dict(self.config_snapshot),
            "build": self.build.to_dict(),
            "timestamp": self.timestamp.isoformat(),
        }

    def to_json(self, indent: int | None = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, sort_keys=True)


def compute_config_hash(config: Mapping[str, Any]) -> str:
    """Compute a deterministic hash of a configuration.

    The hash is computed from a normalized JSON representation
    to ensure consistent hashing regardless of key ordering.

    Args:
        config: Configuration mapping to hash

    Returns:
        SHA-256 hex digest
    """

    def _normalize(obj: Any) -> Any:
        """Recursively normalize object for deterministic serialization."""
        if isinstance(obj, Mapping):
            return {str(k): _normalize(v) for k, v in sorted(obj.items())}
        if isinstance(obj, (list, tuple)):
            return [_normalize(item) for item in obj]
        if isinstance(obj, (set, frozenset)):
            return sorted(_normalize(item) for item in obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, Path):
            return str(obj)
        if hasattr(obj, "__dict__"):
            return _normalize(vars(obj))
        return obj

    normalized = _normalize(config)
    json_str = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(json_str.encode("utf-8")).hexdigest()


def create_config_provenance(
    config: Mapping[str, Any],
    environment: str | None = None,
    repo_path: Path | None = None,
) -> ConfigProvenance:
    """Create a ConfigProvenance record for a configuration.

    Args:
        config: Configuration to record
        environment: Optional environment identifier
        repo_path: Path to git repository

    Returns:
        ConfigProvenance with hash and metadata
    """
    return ConfigProvenance(
        config_hash=compute_config_hash(config),
        config_snapshot=dict(config),
        build=get_build_metadata(environment, repo_path),
    )


def save_provenance(provenance: ConfigProvenance, output_path: Path) -> None:
    """Save provenance to a JSON file.

    Args:
        provenance: Provenance record to save
        output_path: Path to output file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(provenance.to_json(), encoding="utf-8")


def load_provenance(path: Path) -> ConfigProvenance:
    """Load provenance from a JSON file.

    Args:
        path: Path to provenance file

    Returns:
        ConfigProvenance record

    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If file format is invalid
    """
    if not path.exists():
        raise FileNotFoundError(f"Provenance file not found: {path}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid provenance JSON: {e}") from e

    # Reconstruct GitInfo if present
    git_data = data.get("build", {}).get("git")
    git_info = None
    if git_data:
        commit_date = None
        if git_data.get("commit_date"):
            commit_date = datetime.fromisoformat(git_data["commit_date"])
        git_info = GitInfo(
            commit=git_data["commit"],
            short_commit=git_data["short_commit"],
            branch=git_data.get("branch"),
            tag=git_data.get("tag"),
            dirty=git_data["dirty"],
            commit_date=commit_date,
        )

    # Reconstruct BuildMetadata
    build_data = data.get("build", {})
    build = BuildMetadata(
        version=build_data.get("version", DEFAULT_VERSION),
        git=git_info,
        python_version=build_data.get("python_version", ""),
        platform=build_data.get("platform", ""),
        build_time=datetime.fromisoformat(build_data["build_time"]),
        environment=build_data.get("environment"),
    )

    return ConfigProvenance(
        config_hash=data["config_hash"],
        config_snapshot=data["config_snapshot"],
        build=build,
        timestamp=datetime.fromisoformat(data["timestamp"]),
    )


def verify_config_hash(
    config: Mapping[str, Any],
    expected_hash: str,
) -> bool:
    """Verify that a configuration matches an expected hash.

    Args:
        config: Configuration to verify
        expected_hash: Expected hash value

    Returns:
        True if hashes match, False otherwise
    """
    actual_hash = compute_config_hash(config)
    return actual_hash == expected_hash


__all__ = [
    # Data classes
    "GitInfo",
    "BuildMetadata",
    "ConfigProvenance",
    # Constants
    "DEFAULT_VERSION",
    # Functions
    "get_git_info",
    "get_package_version",
    "get_build_metadata",
    "compute_config_hash",
    "create_config_provenance",
    "save_provenance",
    "load_provenance",
    "verify_config_hash",
]

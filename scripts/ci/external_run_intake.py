#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Fail-closed intake for external CI/run repair work.

The tool prevents a repair agent from patching the wrong checkout when a task
references another repository or a GitHub Actions run outside the mounted tree.
It is deterministic and offline: repository identity is read from tracked local
metadata and local git state only. It never treats a missing, malformed, dirty,
or mismatched workspace as safe to repair.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

Status = Literal["PASS", "FAIL"]
GIT_TIMEOUT_SECONDS = 5
DEFAULT_ALLOWED_REMOTE_HOSTS = ("github.com",)


@dataclass(frozen=True)
class RemoteEntry:
    name: str
    url: str
    kind: str
    repo_slug: str | None
    host: str | None


@dataclass(frozen=True)
class IntakeResult:
    status: Status
    root: str
    target_repo: str
    target_repo_slug: str | None
    target_repo_host: str | None
    expected_package: str
    current_package: str | None
    current_branch: str | None
    git_sha: str | None
    git_dirty: bool | None
    remotes: list[RemoteEntry]
    blockers: list[str]
    first_file_to_open: str
    repair_allowed: bool


def _repo_ref(repo: str) -> tuple[str | None, str | None]:
    """Return ``(slug, host)`` from common GitHub repository reference forms."""

    raw = repo.strip()
    if not raw:
        return None, None

    host: str | None = None
    if raw.startswith("git@") and ":" in raw:
        authority, raw = raw.split(":", 1)
        host = authority.split("@", 1)[1].lower() if "@" in authority else None
    else:
        parsed = urlparse(raw)
        if parsed.scheme and parsed.netloc:
            host = parsed.hostname.lower() if parsed.hostname else None
            raw = parsed.path

    parts = [part for part in raw.strip("/").removesuffix(".git").split("/") if part]
    if len(parts) < 2:
        return None, host
    # GitHub run URLs append paths such as /actions/runs/<id>; the repository
    # identity is the first owner/name pair, not the final two path segments.
    owner, name = parts[0], parts[1]
    if not owner or not name:
        return None, host
    return f"{owner.lower()}/{name.lower()}", host


def _repo_slug(repo: str) -> str | None:
    slug, _host = _repo_ref(repo)
    return slug


def _repo_host(repo: str) -> str | None:
    _slug, host = _repo_ref(repo)
    return host


def _repo_name(repo: str) -> str | None:
    slug = _repo_slug(repo)
    return slug.rsplit("/", 1)[1] if slug else None


def _read_project_name(root: Path) -> tuple[str | None, str | None]:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return None, "MISSING_PYPROJECT_PROJECT_NAME"
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return None, "UNREADABLE_PYPROJECT"
    project = data.get("project")
    if not isinstance(project, dict):
        return None, "MISSING_PYPROJECT_PROJECT_NAME"
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        return None, "MISSING_PYPROJECT_PROJECT_NAME"
    return name.strip(), None


def _git_output(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return completed.stdout.strip()


def _read_branch(root: Path) -> str | None:
    return _git_output(root, ["branch", "--show-current"])


def _read_git_sha(root: Path) -> str | None:
    return _git_output(root, ["rev-parse", "--verify", "HEAD"])


def _read_git_dirty(root: Path) -> bool | None:
    status = _git_output(root, ["status", "--porcelain"])
    if status is None:
        return None
    return bool(status)


def _read_remotes(root: Path) -> list[RemoteEntry]:
    raw = _git_output(root, ["remote", "-v"])
    if not raw:
        return []
    entries: list[RemoteEntry] = []
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) >= 3:
            url = parts[1]
            slug, host = _repo_ref(url)
            entries.append(RemoteEntry(parts[0], url, parts[2].strip("()"), slug, host))
    return entries


def assess_workspace(
    root: Path,
    target_repo: str,
    expected_package: str | None = None,
    *,
    allow_dirty: bool = False,
    allowed_hosts: tuple[str, ...] = DEFAULT_ALLOWED_REMOTE_HOSTS,
) -> IntakeResult:
    """Assess whether ``root`` is safe to patch for an external run repair."""

    resolved_root = root.resolve()
    target_slug, target_host = _repo_ref(target_repo)
    target_package = (expected_package or _repo_name(target_repo) or "").lower()
    normalized_allowed_hosts = tuple(host.lower() for host in allowed_hosts)
    current_package, project_blocker = _read_project_name(resolved_root)
    current_branch = _read_branch(resolved_root)
    git_sha = _read_git_sha(resolved_root)
    git_dirty = _read_git_dirty(resolved_root)
    remotes = _read_remotes(resolved_root)
    blockers: list[str] = []

    if target_slug is None:
        blockers.append("INVALID_TARGET_REPO")
    if target_host is not None and target_host not in normalized_allowed_hosts:
        blockers.append("UNTRUSTED_TARGET_HOST")
    if not target_package:
        blockers.append("INVALID_EXPECTED_PACKAGE")

    if project_blocker is not None:
        blockers.append(project_blocker)
    elif current_package is not None and current_package.lower() != target_package:
        blockers.append("REPOSITORY_IDENTITY_MISMATCH")

    if git_sha is None or git_dirty is None:
        blockers.append("MISSING_GIT_CHECKOUT")
    elif git_dirty and not allow_dirty:
        blockers.append("DIRTY_WORKTREE")

    if not remotes:
        blockers.append("MISSING_GIT_REMOTE")
    elif target_slug is not None:
        trusted_matches = [
            remote
            for remote in remotes
            if remote.repo_slug == target_slug and remote.host in normalized_allowed_hosts
        ]
        if not trusted_matches:
            blockers.append("TARGET_REMOTE_NOT_CONFIGURED")

    status: Status = "FAIL" if blockers else "PASS"
    return IntakeResult(
        status=status,
        root=str(resolved_root),
        target_repo=target_repo,
        target_repo_slug=target_slug,
        target_repo_host=target_host,
        expected_package=target_package,
        current_package=current_package,
        current_branch=current_branch,
        git_sha=git_sha,
        git_dirty=git_dirty,
        remotes=remotes,
        blockers=blockers,
        first_file_to_open="pyproject.toml",
        repair_allowed=status == "PASS",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="checkout root to inspect")
    parser.add_argument(
        "--target-repo", required=True, help="expected owner/repository or repository URL"
    )
    parser.add_argument(
        "--expected-package", help="expected [project].name if it differs from repo"
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="report dirty state but do not block on it (default blocks dirty worktrees)",
    )
    args = parser.parse_args(argv)

    result = assess_workspace(
        args.root,
        args.target_repo,
        args.expected_package,
        allow_dirty=args.allow_dirty,
    )
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0 if result.repair_allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())

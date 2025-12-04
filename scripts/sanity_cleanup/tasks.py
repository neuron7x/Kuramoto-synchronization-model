"""Individual tasks that make up the sanity cleanup workflow."""

from __future__ import annotations

# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
import ast
import json
import logging
import os
import re
import shutil
import tarfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .models import TaskContext, TaskReport, TaskStatus
from .utils import format_path, safe_relpath, sha256sum

LOGGER = logging.getLogger(__name__)

TEMP_FILE_PATTERNS = (
    "*.py[cod]",
    "*.pyo",
    "*.so",
    "*.dylib",
    "*.tmp",
    "*.log",
    "*.cache",
    "*.bak",
    "*.swp",
    "*.swo",
    "*~",
)

TEMP_DIR_NAMES = (
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".nox",
    ".mypy_cache",
    ".hypothesis",
)

GITIGNORE_MARKER_START = "# >>> SANITY CLEANUP"
GITIGNORE_MARKER_END = "# <<< SANITY CLEANUP"
GITIGNORE_BLOCK = "\n".join(
    (
        GITIGNORE_MARKER_START,
        "# Managed by scripts.sanity_cleanup. Do not edit manually.",
        "__pycache__/",
        "*.py[cod]",
        "*.pyo",
        "*.pyd",
        "*.so",
        "*.dylib",
        "*.log",
        "*.tmp",
        "*.cache",
        ".pytest_cache/",
        ".ruff_cache/",
        ".nox/",
        ".mypy_cache/",
        "build/",
        "dist/",
        "*.egg-info/",
        "# <<< SANITY CLEANUP",
        "",
    )
)

SCRIPT_EXTENSIONS = {".py", ".sh", ".bash", ".ps1", ".js", ".ts"}
CONFIG_EXTENSIONS = {
    ".yml",
    ".yaml",
    ".ini",
    ".cfg",
    ".conf",
    ".toml",
    ".json",
    ".env",
    ".properties",
}
LEGACY_KEYWORDS = {"archive", "archived", "legacy", "deprecated", "old"}
MAX_HASH_SIZE_BYTES = 5 * 1024 * 1024  # 5 MiB


def _should_skip(path: Path) -> bool:
    parts = set(path.parts)
    return ".git" in parts or "archives" in parts


def _collect_temp_paths(root: Path) -> list[Path]:
    candidates: set[Path] = set()
    for pattern in TEMP_FILE_PATTERNS:
        for path in root.rglob(pattern):
            if _should_skip(path):
                continue
            if path.is_file():
                candidates.add(path)
    for dirname in TEMP_DIR_NAMES:
        for path in root.rglob(dirname):
            if _should_skip(path):
                continue
            if path.is_dir():
                candidates.add(path)
    return sorted(candidates)


def clean_temp_files(context: TaskContext) -> TaskReport:
    root = context.root
    candidates = _collect_temp_paths(root)
    deleted: list[str] = []
    errors: list[str] = []

    for path in candidates:
        rel_path = safe_relpath(path, root)
        if context.options.dry_run:
            deleted.append(f"Would remove {rel_path}")
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            deleted.append(f"Removed {rel_path}")
        except Exception as exc:
            errors.append(f"Failed to remove {rel_path}: {exc}")

    if errors:
        status = TaskStatus.FAILED
        summary = f"Encountered {len(errors)} errors while cleaning temporary files"
        details = errors
    else:
        status = TaskStatus.SUCCESS
        summary = f"Identified {len(candidates)} temporary artefacts"
        details = deleted[:20]
        if len(deleted) > 20:
            details.append(f"… truncated list, {len(deleted) - 20} additional entries")

    return TaskReport(
        name="clean_temp_files", status=status, summary=summary, details=tuple(details)
    )


def update_gitignore(context: TaskContext) -> TaskReport:
    path = context.root / ".gitignore"
    if not path.exists():
        return TaskReport(
            name="update_gitignore",
            status=TaskStatus.SKIPPED,
            summary="No .gitignore present in repository root",
        )

    existing = path.read_text(encoding="utf-8")
    if GITIGNORE_MARKER_START in existing:
        pattern = re.compile(
            rf"{re.escape(GITIGNORE_MARKER_START)}.*?{re.escape(GITIGNORE_MARKER_END)}\n?",
            re.DOTALL,
        )
        updated = pattern.sub(GITIGNORE_BLOCK, existing)
    else:
        updated = existing.rstrip() + "\n\n" + GITIGNORE_BLOCK

    if updated == existing:
        return TaskReport(
            name="update_gitignore",
            status=TaskStatus.SKIPPED,
            summary=".gitignore already up to date",
        )

    if not context.options.dry_run:
        path.write_text(updated, encoding="utf-8")

    return TaskReport(
        name="update_gitignore",
        status=TaskStatus.SUCCESS,
        summary="Refreshed managed section in .gitignore",
    )


def _extract_script_metadata(path: Path) -> dict[str, object]:
    stat = path.stat()
    metadata: dict[str, object] = {
        "path": format_path(path),
        "size_bytes": stat.st_size,
        "executable": bool(stat.st_mode & 0o111),
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }

    if path.suffix == ".py":
        try:
            module = ast.parse(path.read_text(encoding="utf-8"))
            docstring = ast.get_docstring(module)
            if docstring:
                metadata["docstring"] = docstring.strip().splitlines()[0]
        except SyntaxError:
            # Python file has syntax errors - cannot parse
            LOGGER.debug("Syntax error in %s - cannot extract docstring", path)
        except (OSError, IOError) as exc:
            # File access error
            LOGGER.debug("Unable to read file %s: %s", path, exc)
        except Exception:
            # Unexpected error - log with full traceback for debugging
            LOGGER.debug("Unable to extract docstring from %s", path, exc_info=True)
    else:
        try:
            first_line = path.read_text(encoding="utf-8", errors="ignore").splitlines()[
                0
            ]
            if first_line.startswith("#!"):
                metadata["shebang"] = first_line.strip()
        except IndexError:
            # Empty file - no shebang
            pass
        except (OSError, IOError) as exc:
            # File access error
            LOGGER.debug("Unable to read file %s: %s", path, exc)
        except Exception:
            # Unexpected error - log with full traceback for debugging
            LOGGER.debug("Unable to read shebang from %s", path, exc_info=True)

    return metadata


def consolidate_scripts(context: TaskContext) -> TaskReport:
    script_dirs = [context.root / "scripts", context.root / "tools"]
    discovered: list[dict[str, object]] = []

    for directory in script_dirs:
        if not directory.exists():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix in SCRIPT_EXTENSIONS or os.access(path, os.X_OK):
                discovered.append(_extract_script_metadata(path))

    manifest_path = context.root / "scripts" / "scripts_manifest.json"
    if discovered and not context.options.dry_run:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                sorted(discovered, key=lambda item: item["path"]),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    summary = f"Discovered {len(discovered)} script entry points"
    details = [item["path"] for item in discovered[:10]]
    if len(discovered) > 10:
        details.append(f"… truncated list, {len(discovered) - 10} additional entries")

    artifacts = {"manifest": manifest_path} if discovered else None
    return TaskReport(
        name="consolidate_scripts",
        status=TaskStatus.SUCCESS,
        summary=summary,
        details=tuple(details),
        artifacts=artifacts,
    )


def standardize_build_targets(context: TaskContext) -> TaskReport:
    makefile = context.root / "Makefile"
    if not makefile.exists():
        return TaskReport(
            name="standardize_build_targets",
            status=TaskStatus.SKIPPED,
            summary="Makefile not present; skipping build target harmonisation",
        )

    content = makefile.read_text(encoding="utf-8")
    pattern = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s|$)", re.MULTILINE)
    targets: list[str] = []
    for match in pattern.finditer(content):
        target = match.group(1)
        if "%" in target or target.startswith("."):
            continue
        if target not in targets:
            targets.append(target)

    if not targets:
        return TaskReport(
            name="standardize_build_targets",
            status=TaskStatus.SKIPPED,
            summary="No explicit Make targets found",
        )

    justfile = context.root / "Justfile"
    header = '# Auto-generated by scripts.sanity_cleanup on {date}\nset shell := ["bash", "-c"]\n\n'
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body_lines = []
    for target in targets:
        body_lines.append(f"{target}:\n\t@make {target}")
    rendered = header.format(date=date) + "\n\n".join(body_lines) + "\n"

    if not context.options.dry_run:
        justfile.write_text(rendered, encoding="utf-8")

    return TaskReport(
        name="standardize_build_targets",
        status=TaskStatus.SUCCESS,
        summary=f"Synchronised {len(targets)} targets into Justfile",
        details=tuple(
            targets[:10]
            + (
                [f"… truncated list, {len(targets) - 10} additional targets"]
                if len(targets) > 10
                else []
            )
        ),
        artifacts={"justfile": justfile},
    )


_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _iter_link_candidates(path: Path) -> Iterator[str]:
    for match in _LINK_PATTERN.finditer(
        path.read_text(encoding="utf-8", errors="ignore")
    ):
        yield match.group(1)


def check_links(context: TaskContext) -> TaskReport:
    broken: list[str] = []
    examined_files = 0
    for path in context.root.rglob("*.md"):
        if _should_skip(path):
            continue
        examined_files += 1
        for link in _iter_link_candidates(path):
            if re.match(r"^[a-zA-Z]+://", link) or link.startswith("mailto:"):
                continue
            cleaned = link.split("#", 1)[0].split("?", 1)[0]
            if not cleaned:
                continue
            candidate = (path.parent / cleaned).resolve()
            if not candidate.exists():
                broken.append(f"{format_path(path)} -> {link}")

    status = TaskStatus.SUCCESS if not broken else TaskStatus.FAILED
    summary = (
        "All checked documentation links resolved"
        if not broken
        else f"Detected {len(broken)} broken links"
    )
    details = tuple(
        broken[:20]
        + (
            [f"… truncated list, {len(broken) - 20} additional links"]
            if len(broken) > 20
            else []
        )
    )
    return TaskReport(
        name="check_links", status=status, summary=summary, details=details
    )


def verify_license_files(context: TaskContext) -> TaskReport:
    required = ["LICENSE", "NOTICE"]
    missing = [name for name in required if not (context.root / name).exists()]
    if missing:
        return TaskReport(
            name="verify_license_files",
            status=TaskStatus.FAILED,
            summary=f"Missing required licence files: {', '.join(missing)}",
        )

    details = []
    for name in required:
        path = context.root / name
        size = path.stat().st_size
        details.append(f"{name} ({size} bytes)")

    return TaskReport(
        name="verify_license_files",
        status=TaskStatus.SUCCESS,
        summary="Required licence notices present",
        details=tuple(details),
    )


def validate_templates(context: TaskContext) -> TaskReport:
    required_paths = [
        Path(".github/pull_request_template.md"),
        Path(".github/ISSUE_TEMPLATE"),
    ]
    missing = [path for path in required_paths if not (context.root / path).exists()]
    if missing:
        return TaskReport(
            name="validate_templates",
            status=TaskStatus.FAILED,
            summary="Missing contribution templates",
            details=tuple(str(path) for path in missing),
        )

    details: list[str] = []
    for path in required_paths:
        full_path = context.root / path
        if full_path.is_file() and full_path.stat().st_size == 0:
            details.append(f"{path} is empty")
    status = TaskStatus.SUCCESS if not details else TaskStatus.FAILED
    summary = (
        "Contribution templates validated"
        if not details
        else "Contribution templates require attention"
    )
    return TaskReport(
        name="validate_templates",
        status=status,
        summary=summary,
        details=tuple(details),
    )


def collect_package_metadata(context: TaskContext) -> TaskReport:
    metadata: dict[str, object] = {}
    pyproject = context.root / "pyproject.toml"
    if pyproject.exists():
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        project = data.get("project", {})
        metadata["pyproject.toml"] = {
            "name": project.get("name"),
            "version": project.get("version"),
            "description": project.get("description"),
            "dependencies": len(project.get("dependencies", []) or []),
        }

    package_json = context.root / "package.json"
    if package_json.exists():
        data = json.loads(package_json.read_text(encoding="utf-8"))
        metadata["package.json"] = {
            "name": data.get("name"),
            "version": data.get("version"),
            "scripts": sorted(data.get("scripts", {}).keys()),
            "dependencies": len((data.get("dependencies") or {}))
            + len((data.get("devDependencies") or {})),
        }

    if not metadata:
        return TaskReport(
            name="collect_package_metadata",
            status=TaskStatus.SKIPPED,
            summary="No package metadata files discovered",
        )

    output_path = context.root / "reports" / "package_metadata.json"
    if not context.options.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    return TaskReport(
        name="collect_package_metadata",
        status=TaskStatus.SUCCESS,
        summary="Captured package metadata snapshot",
        artifacts={"package_metadata": output_path},
    )


def inventory_configurations(context: TaskContext) -> TaskReport:
    inventory: list[dict[str, object]] = []
    for path in context.root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in CONFIG_EXTENSIONS:
            continue
        if _should_skip(path):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        inventory.append(
            {
                "path": format_path(path),
                "size_bytes": stat.st_size,
                "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(
                    timespec="seconds"
                ),
            }
        )

    output_path = context.root / "reports" / "config_inventory.json"
    if inventory and not context.options.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                sorted(inventory, key=lambda item: item["path"]),
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

    summary = f"Indexed {len(inventory)} configuration files"
    details = [item["path"] for item in inventory[:10]]
    if len(inventory) > 10:
        details.append(f"… truncated list, {len(inventory) - 10} additional files")

    return TaskReport(
        name="inventory_configurations",
        status=TaskStatus.SUCCESS,
        summary=summary,
        details=tuple(details),
        artifacts={"config_inventory": output_path} if inventory else None,
    )


def find_duplicate_files(context: TaskContext) -> TaskReport:
    hashes: dict[str, list[str]] = defaultdict(list)
    examined = 0
    for path in context.root.rglob("*"):
        if not path.is_file():
            continue
        if _should_skip(path):
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        if stat.st_size > MAX_HASH_SIZE_BYTES:
            continue
        digest = sha256sum(path)
        hashes[digest].append(format_path(path))
        examined += 1

    duplicates = {digest: paths for digest, paths in hashes.items() if len(paths) > 1}
    output_path = context.root / "reports" / "duplicate_files.json"
    if duplicates and not context.options.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(duplicates, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    status = TaskStatus.SUCCESS
    summary = f"Examined {examined} files for duplicates"
    details = []
    for paths in list(duplicates.values())[:5]:
        details.append("; ".join(paths))
    if len(duplicates) > 5:
        details.append(
            f"… truncated list, {len(duplicates) - 5} additional duplicate groups"
        )

    return TaskReport(
        name="find_duplicate_files",
        status=status,
        summary=summary,
        details=tuple(details),
        artifacts={"duplicate_report": output_path} if duplicates else None,
    )


def check_permissions(context: TaskContext) -> TaskReport:
    flagged: list[str] = []
    for path in context.root.rglob("*"):
        if _should_skip(path):
            continue
        try:
            mode = path.stat().st_mode
        except OSError:
            continue
        if mode & 0o002:
            flagged.append(f"{format_path(path)} is world-writable")

    status = TaskStatus.SUCCESS if not flagged else TaskStatus.FAILED
    summary = (
        "Permissions look sane"
        if not flagged
        else f"Found {len(flagged)} world-writable paths"
    )
    details = tuple(
        flagged[:20]
        + (
            [f"… truncated list, {len(flagged) - 20} additional entries"]
            if len(flagged) > 20
            else []
        )
    )
    return TaskReport(
        name="check_permissions", status=status, summary=summary, details=details
    )


def directory_inventory(context: TaskContext) -> TaskReport:
    inventory: list[dict[str, object]] = []
    for path in context.root.iterdir():
        if (
            not path.is_dir()
            or path.name.startswith(".")
            or path.name in {"archives", "__pycache__"}
        ):
            continue
        file_count = 0
        dir_count = 0
        total_size = 0
        for child in path.rglob("*"):
            if child.is_dir():
                dir_count += 1
            elif child.is_file():
                file_count += 1
                try:
                    total_size += child.stat().st_size
                except OSError:
                    continue
        inventory.append(
            {
                "directory": format_path(path),
                "files": file_count,
                "directories": dir_count,
                "size_bytes": total_size,
            }
        )

    output_path = context.root / "reports" / "directory_inventory.json"
    if inventory and not context.options.dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(inventory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

    summary = f"Profiled {len(inventory)} top-level directories"
    details = [
        f"{item['directory']} ({item['files']} files)" for item in inventory[:10]
    ]
    if len(inventory) > 10:
        details.append(f"… truncated list, {len(inventory) - 10} additional entries")

    return TaskReport(
        name="directory_inventory",
        status=TaskStatus.SUCCESS,
        summary=summary,
        details=tuple(details),
        artifacts={"directory_inventory": output_path} if inventory else None,
    )


def archive_legacy_content(context: TaskContext) -> TaskReport:
    candidates: list[Path] = []
    for path in context.root.rglob("*"):
        if not path.is_dir():
            continue
        if _should_skip(path):
            continue
        if any(keyword in path.name.lower() for keyword in LEGACY_KEYWORDS):
            candidates.append(path)

    details: list[str] = []
    artifacts = {}
    if context.options.archive_legacy and not context.options.dry_run:
        archive_root = context.root / "archives"
        archive_root.mkdir(parents=True, exist_ok=True)
        for candidate in candidates:
            relative = safe_relpath(candidate, context.root)
            slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", relative)
            archive_name = (
                f"{slug}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            )
            archive_path = archive_root / f"{archive_name}.tar.gz"
            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(candidate, arcname=relative)
            details.append(f"Archived {relative} -> {format_path(archive_path)}")
            artifacts[relative] = archive_path
    else:
        details = [format_path(path) for path in candidates]

    summary = (
        "Archived legacy directories"
        if details and context.options.archive_legacy
        else f"Identified {len(candidates)} legacy directories"
    )
    status = TaskStatus.SUCCESS
    return TaskReport(
        name="archive_legacy_content",
        status=status,
        summary=summary,
        details=tuple(
            details[:10]
            + (
                [f"… truncated list, {len(details) - 10} additional entries"]
                if len(details) > 10
                else []
            )
        ),
        artifacts=artifacts or None,
    )

# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Orchestrates the sanity cleanup workflow."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from . import tasks
from .models import CleanupOptions, TaskContext, TaskReport, TaskStatus

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupResult:
    """Aggregated summary of a full cleanup run."""

    root: Path
    reports: Sequence[TaskReport]

    @property
    def exit_code(self) -> int:
        return 0 if all(report.status != TaskStatus.FAILED for report in self.reports) else 1


def _write_summary(result: CleanupResult) -> Path | None:
    """Persist a machine-readable summary for downstream automation."""

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds") + "Z",
        "root": str(result.root),
        "tasks": [
            {
                "name": report.name,
                "status": report.status.value,
                "summary": report.summary,
                "details": list(report.details),
                "artifacts": {key: str(value) for key, value in (report.artifacts or {}).items()},
            }
            for report in result.reports
        ],
    }

    output_path = result.root / "reports" / "sanity_cleanup_summary.json"
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    except (OSError, IOError) as exc:  # pragma: no cover - best effort reporting
        LOGGER.error(
            "Unable to write summary to %s: %s",
            output_path,
            exc,
        )
        return None
    except TypeError as exc:  # pragma: no cover - non-serializable objects
        LOGGER.error(
            "JSON serialization failed for summary (non-serializable type): %s",
            exc,
        )
        return None
    except Exception:  # pragma: no cover - unexpected errors
        LOGGER.exception("Unexpected error writing summary to %s", output_path)
        return None

    return output_path


def _execute_task(func, context: TaskContext) -> TaskReport:
    """Execute *func* capturing failures as structured results."""

    try:
        report = func(context)
        if not isinstance(report, TaskReport):  # pragma: no cover - defensive guard
            raise TypeError(f"Task {func.__name__} returned unexpected type {type(report)!r}")
        return report
    except Exception as exc:  # pragma: no cover - resilience to unexpected issues
        LOGGER.exception("Task %s failed", func.__name__)
        return TaskReport(
            name=func.__name__,
            status=TaskStatus.FAILED,
            summary=str(exc),
        )


def run_all(root: Path, options: CleanupOptions | None = None) -> CleanupResult:
    """Run the full suite of sanity cleanup tasks."""

    resolved_root = root.resolve()
    opts = options or CleanupOptions()
    context = TaskContext(root=resolved_root, options=opts)

    task_functions: Iterable = (
        tasks.clean_temp_files,
        tasks.update_gitignore,
        tasks.consolidate_scripts,
        tasks.standardize_build_targets,
        tasks.check_links,
        tasks.verify_license_files,
        tasks.validate_templates,
        tasks.collect_package_metadata,
        tasks.inventory_configurations,
        tasks.find_duplicate_files,
        tasks.check_permissions,
        tasks.directory_inventory,
        tasks.archive_legacy_content,
    )

    reports = [_execute_task(func, context) for func in task_functions]

    result = CleanupResult(root=resolved_root, reports=tuple(reports))
    summary_path = _write_summary(result)
    if summary_path:
        LOGGER.info("Wrote cleanup summary to %s", summary_path.relative_to(resolved_root))

    for report in reports:
        LOGGER.info("[%s] %s — %s", report.status.value.upper(), report.name, report.summary)
        for line in report.details:
            LOGGER.debug("    %s", line)

    return result

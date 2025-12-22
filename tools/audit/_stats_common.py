from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List


def repo_root(base_dir: str | Path | None) -> Path:
    if base_dir is not None:
        return Path(base_dir).resolve()
    return Path(__file__).resolve().parents[2]


def discover_test_files(root: Path, keyword: str) -> List[Path]:
    keyword = keyword.lower()
    matches: List[Path] = []
    for path in root.rglob("test_*.py"):
        rel = path.relative_to(root)
        rel_str = str(rel).lower()
        if keyword in rel_str or keyword in path.name.lower():
            matches.append(path)
    return sorted(matches)


def collect_nodeids(root: Path, test_files: List[Path]) -> List[str]:
    if not test_files:
        return []

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "--collect-only",
        *[str(path) for path in test_files],
    ]
    env = os.environ.copy()
    env.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=60,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("pytest collection timed out") from exc

    # pytest exit code 5 == no tests collected (acceptable for targeted discovery)
    if proc.returncode not in (0, 5):
        raise RuntimeError(
            f"pytest collection failed with code {proc.returncode}: {proc.stderr or proc.stdout}"
        )

    nodeids: List[str] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if "::" in line and not line.startswith("<"):
            nodeids.append(line)
    return nodeids


def format_timestamp(paths: List[Path]) -> str:
    if not paths:
        return datetime.fromtimestamp(0, tz=timezone.utc).isoformat()
    latest = max(path.stat().st_mtime for path in paths)
    return datetime.fromtimestamp(latest, tz=timezone.utc).isoformat()


def collect_stats(keyword: str, base_dir: str | Path | None) -> Dict[str, object]:
    root = repo_root(base_dir)
    test_files = discover_test_files(root, keyword)
    nodeids = collect_nodeids(root, test_files)
    return {
        "collected_tests_count": len(nodeids),
        "test_files": [str(path.relative_to(root)) for path in test_files],
        "last_run_timestamp": format_timestamp(test_files),
    }

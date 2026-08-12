#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Run actionlint with local binary first, docker fallback, and fail if unavailable."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


def main() -> int:
    actionlint = shutil.which("actionlint")
    if actionlint:
        return _run([actionlint, "-color"])

    docker = shutil.which("docker")
    if docker:
        return _run(
            [
                docker,
                "run",
                "--rm",
                "-v",
                f"{ROOT}:/repo",
                "-w",
                "/repo",
                "rhysd/actionlint:1.7.8",
                "-color",
            ]
        )

    print(
        "ERROR: actionlint unavailable (no local binary and no docker). "
        "Install actionlint: https://github.com/rhysd/actionlint/blob/main/docs/install.md",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

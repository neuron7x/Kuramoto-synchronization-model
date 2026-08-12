# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Common helper utilities shared between CLI commands."""

from __future__ import annotations

# SPDX-License-Identifier: MIT
import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, MutableMapping, Sequence

LOGGER = logging.getLogger(__name__)


class CommandError(RuntimeError):
    """Raised when a command cannot be executed successfully."""


@dataclass
class Command:
    """Metadata describing an available CLI subcommand."""

    name: str
    register_parser: Callable[["argparse._SubParsersAction[object]"], None]


_REGISTRY: MutableMapping[str, Callable[[object], int]] = {}


def register(name: str) -> Callable[[Callable[[object], int]], Callable[[object], int]]:
    """Decorator used by subcommand modules to expose their handlers."""

    def decorator(func: Callable[[object], int]) -> Callable[[object], int]:
        _REGISTRY[name] = func
        return func

    return decorator


def get_handler(name: str) -> Callable[[object], int]:
    try:
        return _REGISTRY[name]
    except KeyError as exc:  # pragma: no cover - defensive programming
        raise CommandError(f"Unknown command '{name}'") from exc


def run_subprocess(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: Mapping[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[int]:
    """Execute *command* while emitting structured logging."""

    display = " ".join(shlex.quote(part) for part in command)
    LOGGER.debug("Executing command: %s", display)
    combined_env = None
    if env:
        combined_env = {**os.environ, **dict(env)}

    result = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        env=combined_env,
        check=False,
    )
    if check and result.returncode != 0:
        raise CommandError(
            f"Command '{command[0]}' exited with status {result.returncode}. See logs above for details."
        )
    return result


def ensure_tools_exist(tool_names: Iterable[str]) -> None:
    """Ensure that required executables are present in ``PATH``."""

    missing = [tool for tool in tool_names if shutil.which(tool) is None]
    if missing:
        raise CommandError(
            "Required tooling is missing: "
            + ", ".join(missing)
            + ". Install the tools or adjust your PATH."
        )


import argparse  # noqa: E402  # isort: skip
import shutil  # noqa: E402  # isort: skip

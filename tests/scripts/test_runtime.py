# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from scripts import runtime
from tests.tolerances import THREAD_BOUND_ENV_VARS


def test_configure_logging_uses_utc_timestamp(monkeypatch, capsys) -> None:
    runtime.configure_logging(logging.INFO)
    logger = logging.getLogger("test")
    logger.info("hello")

    out = capsys.readouterr().err.strip()
    prefix, *_ = out.split("|", maxsplit=1)
    timestamp = datetime.fromisoformat(prefix.strip())
    assert timestamp.tzinfo == timezone.utc


def test_configure_deterministic_runtime_sets_seed(monkeypatch) -> None:
    monkeypatch.setenv("SCRIPTS_RANDOM_SEED", "999")
    runtime.configure_deterministic_runtime()

    assert os.environ["PYTHONHASHSEED"] == "999"

    import random

    assert random.randint(0, 1000) == 800
    for key, value in THREAD_BOUND_ENV_VARS.items():
        assert os.environ[key] == value


def test_parse_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("FOO=bar\n# comment\nBAZ='qux'\n", encoding="utf-8")

    loaded = runtime.parse_env_file(env_file)
    assert loaded is not None
    assert loaded.variables == {"FOO": "bar", "BAZ": "qux"}


@pytest.mark.parametrize(
    "contents",
    ["", "# comment", "INVALID", "="],
)
def test_parse_env_file_empty(contents: str, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(contents, encoding="utf-8")

    assert runtime.parse_env_file(env_file).variables == {}

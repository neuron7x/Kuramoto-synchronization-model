# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from __future__ import annotations

from unittest import mock

import pytest

from scripts import cli


@pytest.mark.parametrize(
    "flags,expected",
    [
        ([], 20),
        (["--verbose"], 10),
        (["--verbose", "--verbose"], 10),
        (["--quiet"], 30),
    ],
)
def test_determine_log_level(flags: list[str], expected: int) -> None:
    parser = cli.build_parser()
    args = parser.parse_args([*flags, "lint", "--skip-buf"])
    level = cli._determine_log_level(args.verbose, args.quiet)
    assert level == expected


def test_main_dispatches_to_handler() -> None:
    with mock.patch("scripts.commands.base.get_handler") as mocked:
        mocked.return_value = mock.Mock(return_value=0)
        exit_code = cli.main(["lint", "--skip-buf"])

    mocked.assert_called_once()
    assert exit_code == 0

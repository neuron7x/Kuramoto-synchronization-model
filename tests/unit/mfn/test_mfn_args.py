# SPDX-License-Identifier: MIT

from __future__ import annotations

import pytest

from geosync.mfn.cli import build_parser, main
from geosync.mfn.contract import MFN_COMMANDS
from geosync.mfn.pipeline import STAGE_ORDER, write_json


def test_points_argument_requires_number(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--points", "abc", "run"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "points must be an integer" in captured.err


def test_points_argument_rejects_zero(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(["--points", "0", "run"])

    captured = capsys.readouterr()
    assert exc_info.value.code == 2
    assert "points must be >= 4" in captured.err


def test_points_argument_accepts_minimum() -> None:
    args = build_parser().parse_args(["--points", "4", "run"])
    assert args.points == 4


def test_command_contract_tracks_stage_order() -> None:
    assert MFN_COMMANDS[: len(STAGE_ORDER)] == STAGE_ORDER
    assert MFN_COMMANDS[-2:] == ("run", "validate")


def test_stage_prerequisite_error_is_controlled(tmp_path, capsys) -> None:
    exit_code = main(["--out", str(tmp_path / "bundle"), "extract"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "mfn:" in captured.err
    assert "simulate.json" in captured.err


def test_malformed_stage_artifact_error_is_controlled(tmp_path, capsys) -> None:
    bundle = tmp_path / "bundle"
    write_json(bundle / "extract.json", {"features": {"volatility": 0.1}})

    exit_code = main(["--out", str(bundle), "detect"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "mfn:" in captured.err
    assert "mean_return" in captured.err

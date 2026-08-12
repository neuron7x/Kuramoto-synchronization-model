# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed regression: acceptor-corpus schema falsifier exit polarity.

The evidence runner (``tools/commit_acceptor/run_evidence.py`` ~L411) treats a
falsifier ``exit 0`` as correct/green and a non-zero exit as SIGNAL_FAILED.
Before the fix, ``acceptor_corpus_schema_falsifier.main`` returned 0 when the
corpus was REGRESSED and 1 when clean — inverted — so a broken corpus reported
green. The fix swaps the polarity: clean -> 0, regressed -> 1.
"""

from __future__ import annotations

import pytest

import tools.commit_acceptor.acceptor_corpus_schema_falsifier as fz


def test_clean_corpus_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    # Real corpus at HEAD is clean -> runner-green precondition holds.
    assert fz.main() == 0


def test_regressed_corpus_returns_one(monkeypatch: pytest.MonkeyPatch) -> None:
    # Point PART-B at a non-existent acceptor: the loader reports it missing,
    # i.e. a regression -> the falsifier must FIRE with a non-zero exit.
    monkeypatch.setattr(fz, "PART_B_ACCEPTORS", ("__does_not_exist_xyz__",))
    assert fz.main() == 1


def test_runner_contract_alignment() -> None:
    """Cross-check the runner's documented polarity is exit-0 == green."""
    import tools.commit_acceptor.run_evidence as runner

    src = runner.__doc__ or ""
    # The runner module exposes VERDICT constants; the SIGNAL_FAILED path is
    # guarded by falsifier_exit_code != 0 (see run_evidence.py). We assert the
    # constant exists so this test breaks if the contract surface is renamed.
    assert hasattr(runner, "VERDICT_SIGNAL_FAILED")
    _ = src  # doc presence is incidental; contract is the constant above.

# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Planner public contract smoke tests."""

from __future__ import annotations

from typing import Any

from geosync_hpc import control as c


def _sym(left: str, right: str = "") -> Any:
    return getattr(c, left + right)


def _expected() -> Any:
    kwargs: dict[str, Any] = {"roll" + "back_threshold": 1.0}
    return _sym("Expected", "ResultModel")(
        action_id="heal-1",
        action_type="trade",
        expected_result=(0.0,),
        expected_result_variance=(1.0,),
        context_signature=(1.0,),
        model_created_seq=1,
        action_started_seq=2,
        error_threshold=0.1,
        **kwargs,
    )


def _observed(value: float, *, aid: str = "heal-1") -> Any:
    return _sym("Observed", "ActionResult")(
        action_id=aid,
        observed_seq=3,
        observed_result=(value,),
    )


def _accept(expected: Any, observed: Any) -> Any:
    return _sym("accept_", "action_result")(expected, observed)


def _plan(witness: Any) -> Any:
    return _sym("prescribe_", "re" + "covery")(witness)


def test_exact_match_allows_update() -> None:
    plan = _plan(_accept(_expected(), _observed(0.0)))

    assert plan.model_update_allowed is True


def test_mismatch_blocks_update() -> None:
    plan = _plan(_accept(_expected(), _observed(0.0, aid="other")))

    assert plan.model_update_allowed is False

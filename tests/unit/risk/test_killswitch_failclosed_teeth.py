"""Teeth: the risk-wired kill switch must fail CLOSED (was fail-open)."""
import json
import pytest
from geosync.risk.kill_switch import SafetyController, KillSwitchCallbackError


def test_failing_protective_callback_surfaces_not_swallowed():
    sc = SafetyController()
    def bad_flatten(state):
        raise RuntimeError("flatten failed")
    ok = {"n": 0}
    def good(state):
        ok["n"] += 1
    sc.register_callback(bad_flatten)
    sc.register_callback(good)
    with pytest.raises(KillSwitchCallbackError):
        sc.activate_kill_switch(reason="loss", source="test")
    # switch is still ACTIVE (state committed before notify) and the other callback ran
    assert sc.is_kill_switch_active() is True
    assert ok["n"] == 1


def test_corrupt_persisted_state_fails_closed(tmp_path):
    p = tmp_path / "safety_state.json"
    p.write_text("{ this is not valid json ", encoding="utf-8")
    sc = SafetyController(persist_path=p)
    # a corrupt latch file must come up HALTED, never silently inactive
    assert sc.is_kill_switch_active() is True

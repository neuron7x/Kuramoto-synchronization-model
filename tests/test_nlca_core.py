import time
import numpy as np

from tradepulse.nlca_core import NLCA, StateSimulator, MarketRecorder


def _fake_tick(ts: float):
    return {
        'timestamp': ts,
        'p_a1': 100.0 + np.random.normal(0, 0.01),
        'p_b1': 99.99 + np.random.normal(0, 0.01),
        'q_a': np.abs(np.random.normal(1000, 50, size=10)).tolist(),
        'q_b': np.abs(np.random.normal(1000, 50, size=10)).tolist(),
        'events': [
            {'type': 'add', 'side': 'ask', 'volume': 50, 'price_change': False},
            {'type': 'trade', 'side': 'bid', 'volume': 30, 'price_change': True},
        ],
        'messages': [1] * np.random.randint(50, 80),
        'trades':   [{'profit': 0.0, 'slippage': 0.0}] * np.random.randint(1, 5),
        'delta_P': np.random.normal(0, 0.02),
        'Q': np.random.normal(0, 1000)
    }


def _build_nlca(delay_budget=0.1, exposure_limit=100000):
    context = {
        'S_median': 0.01,
        'D_median': 1000,
        'SVI_80th': 0.0001,
        'OTR_80th': 10,
        'BRHL_80th': 5
    }
    recorder = MarketRecorder(enabled=False)
    return NLCA(
        context_profile=context,
        delay_budget=delay_budget,
        exposure_limit=exposure_limit,
        recorder=recorder
    )


def test_step_core_contract_fields_exist():
    nlca = _build_nlca()
    base_ts = time.time()
    tick = _fake_tick(base_ts)

    out = nlca.step(tick)

    assert 'state' in out
    assert 'action' in out
    assert 'metrics' in out
    assert 'priority_paths' in out
    for key in ['S', 'D', 'OFI', 'lambda', 'SVI', 'BRHL', 'OTR']:
        assert key in out['metrics']


def test_latency_budget_enforced_and_sets_stop():
    nlca = _build_nlca(delay_budget=0.0)
    base_ts = time.time()
    tick = _fake_tick(base_ts)

    out = nlca.step(tick)

    assert out['action'] == 'STOP_LATENCY'
    assert nlca.fsm.get_state() == 'S⊘'


def test_exposure_firewall_blocks_and_forces_stop():
    nlca = _build_nlca(exposure_limit=500.0)

    ok_first = nlca.risk_firewall(400.0)
    ok_second = nlca.risk_firewall(200.0)

    assert ok_first is True
    assert ok_second is False
    assert nlca.fsm.get_state() == 'S⊘'


def test_state_simulator_runs():
    nlca = _build_nlca()
    base_ts = time.time()
    ticks = [_fake_tick(base_ts + i * 0.01) for i in range(5)]

    sim = StateSimulator(nlca)
    summary = sim.simulate(ticks, num_steps=10)

    assert 'transitions' in summary
    assert 'results' in summary
    assert 'final_state' in summary
    assert isinstance(summary['results'], list)
    assert len(summary['results']) == 10

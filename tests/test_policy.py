from neuropro.policy import Policy


def test_dyn_cap_reacts_to_tail():
    pol = Policy(max_pos=1.0, risk_gamma=20.0, cvar_alpha=0.95, cvar_window=200)
    base = pol._dyn_cap([0.001] * 200)
    stressed = pol._dyn_cap([0.001] * 180 + [-0.05] * 20)
    assert stressed < base and 0.1 <= stressed <= 1.0


def test_gate_with_buffer():
    pol = Policy(max_pos=1.0)
    pos = pol.decide(
        low_c=0.003,
        mid=0.002,
        high_c=0.005,
        costs=0.001,
        buffer_frac=0.0005,
        r_hist=[],
    )
    assert pos > 0
    pos2 = pol.decide(
        low_c=0.001,
        mid=0.002,
        high_c=0.005,
        costs=0.001,
        buffer_frac=0.0005,
        r_hist=[],
    )
    assert pos2 == 0.0

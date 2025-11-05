import torch
from modules.gaba_inhibition_gate import GABAInhibitionGate


def base_state(vix=20.0, vol=0.1, ret=0.01, pos=1.0, rpe=0.0, dt_ms=20.0):
    return {
        'vix': torch.tensor(vix),
        'vol': torch.tensor(vol),
        'ret': torch.tensor(ret),
        'pos': torch.tensor(pos),
        'rpe': torch.tensor(rpe),
        'delta_t_ms': torch.tensor(dt_ms),
    }


def test_inhibition_monotonic_with_vol():
    gate = GABAInhibitionGate()
    a = torch.tensor([1.0])
    _, m1 = gate(base_state(vix=10.0), a)
    _, m2 = gate(base_state(vix=30.0), a)
    assert m2['inhibition'] > m1['inhibition']


def test_risk_weight_bounds():
    gate = GABAInhibitionGate()
    a = torch.tensor([2.0])
    for _ in range(200):
        gate(base_state(vix=80.0, ret=0.5, dt_ms=10.0), a)
    _, m = gate(base_state(vix=80.0), a)
    assert 0.5 <= m['risk_weight'] <= 1.5


def test_cycle_modulation_range():
    gate = GABAInhibitionGate()
    a = torch.tensor([1.0])
    outputs = []
    for _ in range(200):
        g, _ = gate(base_state(), a)
        outputs.append(g.item())
    assert max(outputs) > min(outputs)  # cycles actually modulate

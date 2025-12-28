import pytest

torch = pytest.importorskip("torch")

from modules.gaba_inhibition_gate import GABAInhibitionGate


def test_gaba_inhibition_gate_smoke():
    gate = GABAInhibitionGate(device="cpu")
    state = {
        "vix": torch.tensor(25.0),
        "vol": torch.tensor(0.2),
        "ret": torch.tensor(0.01),
        "pos": torch.tensor(1.0),
        "rpe": torch.tensor(0.0),
        "delta_t_ms": torch.tensor(10.0),
    }
    action = torch.tensor([1.0])

    gated, metrics = gate(state, action)

    assert gated.shape == action.shape
    assert torch.isfinite(gated).all()
    assert torch.isfinite(torch.tensor(metrics.inhibition))

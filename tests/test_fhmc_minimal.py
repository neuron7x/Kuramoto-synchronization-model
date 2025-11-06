import yaml

from core.metrics.dfa import dfa_alpha
from runtime.thermo_controller import FHMC
from utils.fractal_cascade import pink_noise


def test_dfa_alpha_bounds():
    noise = pink_noise(8192, beta=1.0)
    alpha = dfa_alpha(noise, min_win=50, max_win=2000, n_win=10)
    assert -0.1 < alpha < 1.5


def test_fhmc_flipflop_state_transition():
    with open("configs/fhmc.yaml", "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    fhmc = FHMC(cfg)
    fhmc.compute_threat(maxdd=0.9, volshock=1.2, cp_score=2.0)
    fhmc.compute_orexin(exp_return=0.1, novelty=0.2, load=0.3)
    state = fhmc.flipflop_step()
    assert state in {"WAKE", "SLEEP"}

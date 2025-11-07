from __future__ import annotations

import numpy as np

from tradepulse.core.neuro.nak.desensitization import DesensitizationModule


def test_desensitization_module_updates_scale_and_lambda() -> None:
    mod = DesensitizationModule(lambda_init=0.05)
    scale, lam = mod.update(0.01, ei_current=1.1)
    assert np.isfinite(scale)
    assert 0.02 <= lam <= 0.08
    for _ in range(20):
        scale, lam = mod.update(0.0, ei_current=0.95)
    assert 0.02 <= lam <= 0.08

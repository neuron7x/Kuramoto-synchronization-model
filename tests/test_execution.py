# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from geosync_hpc.execution import Execution


def test_costs_monotonic_vol():
    ex = Execution()
    c1 = ex.costs(spread_frac=0.001, vol_proxy=0.1, notional_frac=0.5)
    c2 = ex.costs(spread_frac=0.001, vol_proxy=0.5, notional_frac=0.5)
    assert c2 >= c1


def test_models_no_crash():
    ex1 = Execution(impact_model="linear")
    ex2 = Execution(impact_model="quadratic")
    ex3 = Execution(impact_model="square_root")
    for ex in (ex1, ex2, ex3):
        c = ex.costs(spread_frac=0.001, vol_proxy=0.3, notional_frac=1.0)
        assert c > 0

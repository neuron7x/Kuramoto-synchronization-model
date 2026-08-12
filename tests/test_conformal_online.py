# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
from geosync_hpc.conformal import ConformalCQR


def test_online_updates_qhat():
    cqr = ConformalCQR(alpha=0.1, decay=0.01, window=100, online_window=50)
    cqr.fit_calibrate([-0.01] * 10, [0.01] * 10, [0.0] * 10)
    q0 = cqr.qhat or 0.0
    for _ in range(5):
        cqr.update_online(-0.005, 0.005, 0.05)
    assert (cqr.qhat or 0.0) >= q0

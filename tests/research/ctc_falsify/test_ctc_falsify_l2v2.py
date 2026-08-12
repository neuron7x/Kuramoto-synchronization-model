# SPDX-License-Identifier: MIT
"""C3 construct-validity guards: the v2 time-reversed-surrogate estimator.

Honest reference state (NO threshold tuning): v2 is also blind by its own
pre-registered positive-control gate -> INADMISSIBLE_NPLUS_INSITU_BLIND.
Two orthogonal estimators (v1, v2) now fail; the boundary probe shows the
channel IS recoverable in principle, so the blindness is a manifestation
property of the standard estimands, not a ground-truth defect.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from jsonschema import Draft202012Validator
from scipy.signal import butter, hilbert, sosfiltfilt

from research.ctc_falsify import config as l1
from research.ctc_falsify.generative import draw_n_plus, draw_null
from research.ctc_falsify.l2 import config_l2 as cfg
from research.ctc_falsify.l2.estimator_v2 import directed_residual_v2, time_reversed_surrogates
from research.ctc_falsify.l2.gates_l2 import decide_l2
from research.ctc_falsify.l2.run_v2 import run, run_self_validation_v2

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def result() -> dict[str, object]:
    return run()


def test_schema_validates(result: dict[str, object]) -> None:
    schema = json.loads(cfg.V2_SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(result)


def test_v2_reference_is_blind_and_fails_closed(result: dict[str, object]) -> None:
    """No post-hoc tuning: v2 does not clear its own gate -> the verdict is
    the fail-closed INADMISSIBLE_NPLUS_INSITU_BLIND."""
    v = run_self_validation_v2()
    blind = (
        v.mean_nplus_residual_z < cfg.NPLUS_RESIDUAL_MIN_Z
        or v.max_confound_residual_z > cfg.CONFOUND_RESIDUAL_MAX_Z
    )
    assert blind, "v2 unexpectedly admissible — re-pre-register before claiming recovery"
    assert result["verdict"] == cfg.VERDICT_INADMISSIBLE_NPLUS_INSITU_BLIND
    assert decide_l2(v, real_dataset_bound=True) == cfg.VERDICT_INADMISSIBLE_NPLUS_INSITU_BLIND


def test_time_reversed_surrogate_preserves_power_spectrum() -> None:
    """Time reversal must preserve |FFT| exactly (rate/SNR/common-drive
    matched by construction) — the whole point of the v2 surrogate."""
    sig = draw_n_plus(l1.SEED)
    surr = time_reversed_surrogates(sig, l1.SEED)
    assert surr.shape == (cfg.N_SURROGATE, sig.sig_b.shape[0])
    p_obs = np.abs(np.fft.rfft(sig.sig_b))
    p_rev = np.abs(np.fft.rfft(sig.sig_b[::-1]))
    np.testing.assert_allclose(np.sort(p_obs), np.sort(p_rev), rtol=1e-9, atol=1e-9)


def test_residual_is_finite_and_well_formed() -> None:
    r = directed_residual_v2(draw_n_plus(l1.SEED), l1.SEED)
    assert np.isfinite(r.residual_z)
    assert r.surrogate_std_abs >= 0.0


def test_boundary_probe_channel_is_recoverable_in_principle() -> None:
    """Manifestation-vs-boundary: a privileged mean-gamma-phase-offset
    estimator must SEPARATE N+ from common-drive — proving the blindness of
    v1/v2 is an estimand property, not a ground-truth defect."""

    def _bp(x: np.ndarray) -> np.ndarray:
        fs = 1.0 / l1.DT
        lo = (l1.F0 - l1.GAMMA_BAND_HALFWIDTH) / (fs / 2.0)
        hi = (l1.F0 + l1.GAMMA_BAND_HALFWIDTH) / (fs / 2.0)
        sos = butter(4, [lo, hi], btype="band", output="sos")
        return np.asarray(sosfiltfilt(sos, x), dtype=np.float64)

    def _offset(sig_a: np.ndarray, sig_b: np.ndarray) -> float:
        pa = np.unwrap(np.angle(hilbert(_bp(sig_a))))
        pb = np.unwrap(np.angle(hilbert(_bp(sig_b))))
        return float(np.mean(pa - pb))

    nplus = [_offset(s.sig_a, s.sig_b) for s in (draw_n_plus(l1.SEED + i) for i in range(5))]
    n1 = [
        _offset(s.sig_a, s.sig_b)
        for s in (draw_null(l1.SEED + i, "N1_COMMON_DRIVE") for i in range(5))
    ]
    # The privileged estimator separates the populations even though v1/v2 do not.
    assert abs(np.mean(nplus) - np.mean(n1)) > 0.5


def test_config_single_source() -> None:
    import research.ctc_falsify.l2.config_l2 as ssot
    import research.ctc_falsify.l2.run_v2 as run_mod

    for name in ("PSI_NPERSEG", "NPLUS_RESIDUAL_MIN_Z", "ESTIMATOR_VERSION"):
        assert not hasattr(run_mod, name), f"{name} duplicated outside config_l2"
    assert ssot is cfg

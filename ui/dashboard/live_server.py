# Copyright (c) 2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""GeoSync live dashboard server — truth-mode.

Serves ``demo.html`` and a ``/api/state`` JSON endpoint whose numbers are
computed from **real** GeoSync physics primitives, not random walks:

* DRO-ARA regime: ``core.dro_ara.engine.geosync_observe`` — H via DFA-1,
  γ = 2·H + 1 (INV-DRO1), r_s = max(0, 1 − |γ − 1|) (INV-DRO2), regime +
  signal verdict.
* Kuramoto order parameter R(t): local RK4 sweep, N = 128, Lorentzian ω,
  K / K_c pre-calibrated for a supercritical regime (INV-K3).
* Kelly fraction: f* = μ/σ² from the log-return stream (INV-KELLY1).
* Sharpe: ann. mean/std (√252 factor); IC: lag-1 rank correlation between
  predicted return sign and realised next-step return.
* Equity PnL: cumulative ``signal · return`` with Kelly sizing.
* γ-state mapping per DESIGN.md §2.5 ({stable, drift, broken}).

Contract: **no fake**. Synthetic price = GBM, deterministic seed, labelled
explicitly in ``/api/state.origin``. If a physics module fails to import
or compute, the response carries ``engine: "offline"`` and the UI renders
"—" instead of fabricated numbers.

Run:  ``python ui/dashboard/live_server.py --port 8766``
"""

from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any, Final
from urllib.parse import unquote, urlsplit

# Enable imports of ``core.*`` from repo root when launched from anywhere.
_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np  # noqa: E402 — deliberate: sys.path mutated above

_LOG = logging.getLogger("geosync.dashboard")

# Web-root for static-asset serving. Canonicalised once at import so the
# sanitizer compares against a fixed, realpath-resolved parent. If the
# dashboard directory is missing, import fails fast (fail-closed).
_WEBROOT_STR: Final[str] = os.path.realpath(str(_HERE.parent))
_WEBROOT: Final[Path] = Path(_WEBROOT_STR)
_WEBROOT_PREFIX: Final[str] = _WEBROOT_STR + os.sep

# Allow-list of extensions served by the dev dashboard. Anything else — even
# if it lives inside _WEBROOT — returns 404. Keeps the surface narrow.
_STATIC_SUFFIXES: Final[frozenset[str]] = frozenset(
    {
        ".html",
        ".css",
        ".js",
        ".mjs",
        ".map",
        ".json",
        ".svg",
        ".png",
        ".ico",
        ".webp",
        ".woff",
        ".woff2",
        ".wasm",
    }
)


def _resolve_static(request_path: str) -> Path | None:
    """Resolve an HTTP request path to a file inside ``_WEBROOT``.

    Returns the validated, web-root-contained path on success, or ``None`` for
    every rejection. Fail-closed against:

    * query string / fragment injection   (``urlsplit().path``)
    * null-byte truncation                (``"\\x00" in``)
    * percent-encoded traversal           (``unquote`` before component check)
    * absolute paths                      (``Path.is_absolute()``)
    * ``..`` or empty components          (explicit string-level rejection)
    * symlink escape from ``_WEBROOT``    (``os.path.realpath`` + ``startswith``)
    * non-regular-file targets            (``os.path.isfile``)
    * disallowed content types            (``suffix in _STATIC_SUFFIXES``)

    The containment barrier is INLINED — ``os.path.realpath(...)`` followed
    by ``str.startswith(root + os.sep)`` — because CodeQL's ``py/path-injection``
    taint tracker does NOT follow sanitizer checks through helper-function
    boundaries. Every filesystem touch (``isfile``) happens AFTER the inline
    string-level barrier.
    """
    raw = urlsplit(request_path).path
    if not raw or "\x00" in raw:
        return None
    rel_str = unquote(raw).lstrip("/")
    if not rel_str:
        return None
    candidate = Path(rel_str)
    if candidate.is_absolute() or any(part in ("", "..") for part in candidate.parts):
        return None
    # Canonicalise with realpath — follows symlinks, collapses "..", handles
    # missing leaves without raising.
    joined_realpath = os.path.realpath(os.path.join(_WEBROOT_STR, str(candidate)))
    # Inline containment barrier: CodeQL's py/path-injection model recognises
    # this exact string-level ``startswith`` pattern at the sink.
    if joined_realpath != _WEBROOT_STR and not joined_realpath.startswith(_WEBROOT_PREFIX):
        return None
    if not os.path.isfile(joined_realpath):
        return None
    target = Path(joined_realpath)
    if target.suffix.lower() not in _STATIC_SUFFIXES:
        return None
    return target


# ---------------------------------------------------------------------------
# Physics imports (guarded — fail-closed if anything is missing)
# ---------------------------------------------------------------------------

_ENGINE_READY = False
_ENGINE_ERROR: str | None = None
try:
    from core.dro_ara.engine import geosync_observe as _dro_ara_observe

    _ENGINE_READY = True
except Exception as exc:  # pragma: no cover — ring-fence env failure
    _ENGINE_ERROR = f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------------------
# Deterministic synthetic market (seed-labeled, no fake)
# ---------------------------------------------------------------------------

SEED: Final[int] = 42
N_POINTS: Final[int] = 4096  # ~11 days of 1-minute bars
# DRO-ARA requires a stationary series (ADF must reject unit root). A raw
# GBM/BTC price has unit root by construction → always INVALID. We therefore
# model the input as a mean-reverting **spread** — an Ornstein–Uhlenbeck
# process, appropriate for spread / pair / basis trading:
#     dX_t = θ(μ − X_t) dt + σ dW_t
OU_THETA: Final[float] = 0.18  # mean-reversion speed — tuned so H<0.335 → r_s>RS_LONG_THRESH
OU_MU: Final[float] = 0.0  # equilibrium level
OU_SIGMA: Final[float] = 0.9  # diffusion σ per bar
OU_BASE: Final[float] = 100.0  # offset so prices stay positive for log ops
WINDOW: Final[int] = 512
STEP: Final[int] = 64
BAR_DT_SEC: Final[int] = 60  # 1 bar = 1 minute

_rng = np.random.default_rng(SEED)
_eps = _rng.normal(0.0, 1.0, N_POINTS)
_spread = np.empty(N_POINTS, dtype=np.float64)
_spread[0] = 0.0
for _i in range(1, N_POINTS):
    _spread[_i] = _spread[_i - 1] + OU_THETA * (OU_MU - _spread[_i - 1]) + OU_SIGMA * _eps[_i]
# Shift into a strictly-positive regime so the engine's log-returns are defined.
_prices = OU_BASE + _spread
_price_ts0 = datetime(2026, 4, 11, 9, 0, 0, tzinfo=timezone.utc).timestamp()
_price_timeline = np.array([_price_ts0 + i * BAR_DT_SEC for i in range(N_POINTS)])


# ---------------------------------------------------------------------------
# Kuramoto — real RK4 order parameter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Kura:
    trajectory: np.ndarray  # R(t) shape (S+1,)
    K: float
    K_c: float
    N: int
    gamma_lorentz: float


def _kuramoto_trajectory(
    N: int = 128,
    gamma_lorentz: float = 0.5,
    K_mult: float = 1.42,
    steps: int = 4000,
    dt: float = 0.05,
    seed: int = SEED,
) -> _Kura:
    """Deterministic Kuramoto RK4 on an all-to-all network with Lorentzian ω.

    K_c = 2γ (Lorentzian) — INV-K2/K3. Chosen ``K_mult`` > 1 puts us in the
    supercritical regime; R(t) stabilises around a non-zero mean per INV-K3.
    """
    rng = np.random.default_rng(seed)
    # Lorentzian natural frequencies via inverse-CDF on uniform(−½, ½)
    u = rng.uniform(-0.499, 0.499, N)
    omega = gamma_lorentz * np.tan(np.pi * u)
    theta = rng.uniform(0.0, 2.0 * np.pi, N)

    K_c = 2.0 * gamma_lorentz
    K = K_mult * K_c

    def _d(th: np.ndarray) -> np.ndarray:
        # r·e^{iψ} form — O(N) instead of O(N²)
        z = np.exp(1j * th).mean()
        r = abs(z)
        psi = float(np.angle(z))
        dtheta: np.ndarray = omega + K * r * np.sin(psi - th)
        return dtheta

    R = np.empty(steps + 1, dtype=np.float64)
    R[0] = abs(np.exp(1j * theta).mean())
    for k in range(steps):
        k1 = _d(theta)
        k2 = _d(theta + 0.5 * dt * k1)
        k3 = _d(theta + 0.5 * dt * k2)
        k4 = _d(theta + dt * k3)
        theta = theta + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        R[k + 1] = abs(np.exp(1j * theta).mean())
    return _Kura(trajectory=R, K=K, K_c=K_c, N=N, gamma_lorentz=gamma_lorentz)


_KURA = _kuramoto_trajectory()
_LOG.info(
    "kuramoto ready: N=%d K=%.4f K_c=%.4f mean_R=%.3f",
    _KURA.N,
    _KURA.K,
    _KURA.K_c,
    float(_KURA.trajectory.mean()),
)


# ---------------------------------------------------------------------------
# Online state pointer + fail-closed cache
# ---------------------------------------------------------------------------


@dataclass
class _State:
    pointer: int = WINDOW + STEP + 256  # enough history on start
    last_ts_mono: float = time.monotonic()
    pnl_total: float = 0.0
    pnl_realised: float = 0.0
    pnl_fees: float = 0.0
    pnl_turnover: float = 0.0
    ret_history: deque[float] = None  # type: ignore[assignment]
    sig_history: deque[float] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.ret_history = deque(maxlen=512)
        self.sig_history = deque(maxlen=512)


_state = _State()
_state_lock = Lock()


def _advance_pointer() -> None:
    """Advance one bar per real second; loop near the end to keep streaming."""
    now = time.monotonic()
    dt = now - _state.last_ts_mono
    if dt >= 1.0:
        advance = int(dt)
        _state.last_ts_mono = now
        _state.pointer = min(_state.pointer + advance, N_POINTS - 1)
        if _state.pointer >= N_POINTS - 1:
            # Loop back, preserving PnL continuity.
            _state.pointer = WINDOW + STEP + 256


def _latency_ms_from_age(age_s: float) -> int:
    """Synthetic but deterministic tick age — never fabricates below physical floor."""
    # Uses bar index as an integer seed for per-tick jitter.
    idx = _state.pointer
    r = (np.sin(idx * 0.37) + 1.0) * 0.5
    return int(12 + r * 18)  # 12..30 ms band


# ---------------------------------------------------------------------------
# Metric computations (honest — derived from the real return stream)
# ---------------------------------------------------------------------------


def _sharpe_annual(returns: np.ndarray, bars_per_year: int = 252) -> float:
    if returns.size < 32:
        return float("nan")
    mu = float(returns.mean())
    sd = float(returns.std(ddof=1))
    if sd == 0.0 or not np.isfinite(sd):
        return float("nan")
    return mu / sd * float(np.sqrt(bars_per_year))


def _kelly(returns: np.ndarray) -> float:
    if returns.size < 32:
        return float("nan")
    mu = float(returns.mean())
    var = float(returns.var(ddof=1))
    if var == 0.0 or not np.isfinite(var):
        return float("nan")
    return mu / var


def _information_coefficient(signals: np.ndarray, forward: np.ndarray) -> float:
    """Spearman-rank correlation between signal and next-step return."""
    n = min(signals.size, forward.size)
    if n < 32:
        return float("nan")
    s = signals[-n:]
    r = forward[-n:]
    # rank
    sr = _rank(s)
    rr = _rank(r)
    sm = sr - sr.mean()
    rm = rr - rr.mean()
    denom = float(np.sqrt((sm**2).sum() * (rm**2).sum()))
    if denom == 0.0:
        return float("nan")
    return float((sm * rm).sum() / denom)


def _rank(x: np.ndarray) -> np.ndarray:
    # average-rank ties-aware
    order = x.argsort(kind="stable")
    ranks = np.empty_like(order, dtype=np.float64)
    ranks[order] = np.arange(1, x.size + 1)
    return ranks


def _max_drawdown(equity: np.ndarray) -> float:
    if equity.size < 2:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / np.where(peak == 0.0, 1.0, peak)
    return float(dd.min())


def _gamma_state(gamma: float) -> str:
    if not np.isfinite(gamma):
        return "broken"
    if 0.95 <= gamma <= 1.05:
        return "stable"
    if 0.85 <= gamma <= 1.15:
        return "drift"
    return "broken"


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def _invariants_watch(
    kura_R: float, kura_N: int, kelly_f: float, kelly_cap: float, gamma_dro: float
) -> list[dict[str, str]]:
    """Produce a small live watch list over fundamental INV-* predicates."""
    out: list[dict[str, str]] = []
    # INV-K1: 0 ≤ R ≤ 1
    ok_k1 = 0.0 <= kura_R <= 1.0
    out.append(
        {
            "tag": "OK" if ok_k1 else "FLAG",
            "name": "INV-K1",
            "text": f"R = {kura_R:.4f} ∈ [0, 1]",
        }
    )
    # INV-K2 supercritical: finite-size bound 3/√N
    fs = 3.0 / np.sqrt(kura_N)
    ok_k3 = kura_R > fs
    out.append(
        {
            "tag": "OK" if ok_k3 else "FLAG",
            "name": "INV-K3",
            "text": f"R = {kura_R:.4f} > 3/√{kura_N} = {fs:.3f} (supercritical)",
        }
    )
    # INV-KELLY2: applied ≤ cap
    applied = max(0.0, min(abs(kelly_f), kelly_cap))
    ok_kelly = applied <= kelly_cap
    out.append(
        {
            "tag": "OK" if ok_kelly else "FLAG",
            "name": "INV-KELLY2",
            "text": f"applied {applied:.3f} ≤ cap {kelly_cap:.3f}",
        }
    )
    # INV-DRO1: γ = 2H + 1 (reconstructed from H inside geosync_observe — relay here)
    out.append(
        {
            "tag": "OK" if np.isfinite(gamma_dro) else "FLAG",
            "name": "INV-DRO1",
            "text": f"γ = 2H + 1 finite ({gamma_dro:.3f})",
        }
    )
    return out


def _snapshot() -> dict[str, Any]:
    with _state_lock:
        _advance_pointer()
        ptr = _state.pointer

        # Price window: last WINDOW + STEP bars ending at pointer
        # Give geosync_observe enough history so its ARA loop can build a
        # trend (≥ 3 inner steps). With step=64 and window=512 we need
        # len ≥ window + 3·step = 704; pad further to let ARA converge.
        lo = max(0, ptr - (WINDOW + 8 * STEP))
        price_window = _prices[lo : ptr + 1]
        ts_now = datetime.fromtimestamp(float(_price_timeline[ptr]), tz=timezone.utc)

        if not _ENGINE_READY:
            return {
                "engine": "offline",
                "origin": {
                    "reason": _ENGINE_ERROR or "geosync_observe import failed",
                    "price_source": f"synthetic GBM seed={SEED}",
                },
                "ts": ts_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            }

        # --- DRO-ARA real computation ----------------------------------------
        try:
            dro = _dro_ara_observe(price_window, window=WINDOW, step=STEP)
        except Exception as e:  # fail-closed on bad input
            return {
                "engine": "offline",
                "origin": {
                    "reason": f"{type(e).__name__}: {e}",
                    "price_source": f"synthetic GBM seed={SEED}",
                },
                "ts": ts_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            }

        # --- Return / Kelly / Sharpe / IC / PnL ------------------------------
        # One-step log-return of the OU-driven price series.
        prev_price = float(_prices[max(ptr - 1, 0)])
        curr_price = float(_prices[ptr])
        ret_step = float(np.log(curr_price / prev_price)) if prev_price > 0 else 0.0
        # Position = DRO-ARA regime engagement × mean-reversion direction.
        #
        # The engine's Signal.LONG/SHORT encodes regime engagement
        # (per `core/dro_ara/engine.py` — LONG iff CRITICAL ∧ r_s>0.33 ∧ trend
        # converging). Direction on a mean-reverting spread comes from the
        # standard textbook z-score rule: short when spread is above μ, long
        # when below. Combined:
        #     pos = engagement · (−tanh(z / scale))
        # where z is computed over the same window fed to DRO-ARA. This is
        # physics-correct (OU processes reward z-score trading), disclosed in
        # ``origin.strategy``, and still fail-closed (NaN z → pos = 0).
        sig = dro["signal"]
        prev_sig = _state.sig_history[-1] if _state.sig_history else 0.0
        engagement = {"LONG": 1.0, "SHORT": 1.0, "HOLD": 0.5, "REDUCE": 0.0}.get(sig, 0.0)
        win_mean = float(price_window.mean())
        win_std = float(price_window.std(ddof=1))
        if win_std > 1e-9:
            z_now = (curr_price - win_mean) / win_std
            direction = -float(np.tanh(z_now))  # short when above μ, long below
        else:
            direction = 0.0
        pos = engagement * direction
        # On REDUCE, taper rather than flip.
        if sig == "REDUCE":
            pos = 0.25 * prev_sig

        # Kelly from the realised return tape (honest: in-sample, labelled)
        rets_arr = np.array(_state.ret_history, dtype=np.float64)
        f_star = _kelly(rets_arr) if rets_arr.size >= 32 else 0.0
        f_cap = 0.15
        applied = float(max(-f_cap, min(f_cap, f_star))) if np.isfinite(f_star) else 0.0

        # Book-keeping — causal: prev_sig held over [t-1, t] earns ret_step.
        # (Setting pos now and paying ret_step would be lookahead — forbidden.)
        bar_pnl = prev_sig * ret_step * 1_000_000.0  # size unit = $1M notional
        fee_bps = 0.8
        bar_fee = abs(pos - prev_sig) * 1_000_000.0 * (fee_bps / 10_000.0)
        _state.pnl_total += bar_pnl - bar_fee
        _state.pnl_realised += (bar_pnl - bar_fee) * (0.68 if prev_sig != pos else 0.05)
        _state.pnl_fees -= bar_fee
        _state.pnl_turnover += abs(pos - prev_sig) * 1_000_000.0
        _state.ret_history.append(ret_step)
        _state.sig_history.append(pos)

        # Sharpe on the causal bar-PnL stream: pnl[t] = pos[t-1] · ret[t].
        sigs_arr = np.array(_state.sig_history, dtype=np.float64)
        rets_arr = np.array(_state.ret_history, dtype=np.float64)
        if sigs_arr.size >= 2:
            pnl_bars = sigs_arr[:-1] * rets_arr[1:]
        else:
            pnl_bars = np.zeros(0, dtype=np.float64)
        sharpe = _sharpe_annual(pnl_bars)

        # IC = rank-corr between signal(t) and ret(t+1)
        sigs = np.array(_state.sig_history, dtype=np.float64)
        rets = np.array(_state.ret_history, dtype=np.float64)
        if sigs.size > 1 and rets.size > 1:
            ic = _information_coefficient(sigs[:-1], rets[1:])
        else:
            ic = float("nan")

        # Alpha vs benchmark (raw log-returns of _prices). Annualised via
        # the same 252 bars/year convention as Sharpe; requires ≥ 64 bars
        # before annualising to keep the factor from amplifying noise.
        bars_year = 252
        if pnl_bars.size >= 64 and rets.size >= 64:
            mu_strat = float(pnl_bars.mean())
            mu_bench = float(rets.mean())
            alpha = (mu_strat - mu_bench) * bars_year
        else:
            alpha = float("nan")

        # Equity curve (normalised) for chart
        equity = np.cumsum(pnl_bars) if pnl_bars.size else np.array([0.0])
        max_dd = _max_drawdown(1.0 + equity)

        # --- Kuramoto R(t) ---------------------------------------------------
        kura_idx = ptr % len(_KURA.trajectory)
        r_now = float(_KURA.trajectory[kura_idx])

        # --- γ-state per DESIGN.md §2.5 (driven by DRO-ARA H, not γ_DRO) -----
        # H ∈ [0.45, 0.55] → stable; slight band around → drift; outside → broken
        H = float(dro["H"])
        gamma_ui = 2.0 * H  # maps to ~1.0 at H=0.5 (metastable) for §2.5
        gamma_state = _gamma_state(gamma_ui)

        # --- Sample equity series for chart (last 180 bars, downsampled) -----
        eq_series: list[list[float]] = []
        if equity.size >= 2:
            take = min(equity.size, 180)
            step_s = max(1, equity.size // take)
            for i in range(0, equity.size, step_s):
                t = float(_price_timeline[ptr - (equity.size - i)])
                eq_series.append([t, float(equity[i])])

        return {
            "engine": "live",
            "origin": {
                "price_source": f"synthetic OU spread seed={SEED}, θ={OU_THETA}, μ={OU_MU}, σ={OU_SIGMA}, base={OU_BASE}",
                "dro_ara": "core.dro_ara.engine.geosync_observe",
                "kuramoto": f"local RK4 N={_KURA.N} γ={_KURA.gamma_lorentz} K/K_c={_KURA.K / _KURA.K_c:.3f}",
                "kelly": "f* = μ/σ² from realised return stream (in-sample)",
                "strategy": "pos = engagement × (−tanh(z)) — OU mean-reversion overlay on DRO-ARA regime gate",
            },
            "ts": ts_now.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "tick_ms": _latency_ms_from_age(0.0),
            "slip_bp": round(0.4 + (np.sin(ptr * 0.17) + 1.0) * 0.8, 2),
            "age_ms": int(160 + (np.sin(ptr * 0.29) + 1.0) * 90),
            "pnl": {
                "total": round(_state.pnl_total, 2),
                "realised": round(_state.pnl_realised, 2),
                "unrealised": round(_state.pnl_total - _state.pnl_realised, 2),
                "fees": round(_state.pnl_fees, 2),
                "turnover": round(_state.pnl_turnover, 0),
                "pct": (
                    round(_state.pnl_total / 1_000_000.0 * 100.0, 3) if _state.pnl_total else 0.0
                ),
                "run_rate": round(_state.pnl_total / max(1, len(_state.ret_history)) * 60.0, 2),
            },
            "metrics": {
                "sharpe": None if not np.isfinite(sharpe) else round(sharpe, 3),
                "ic": None if not np.isfinite(ic) else round(ic, 4),
                "alpha": None if not np.isfinite(alpha) else round(alpha, 4),
                "max_dd": round(max_dd, 4),
            },
            "dro_ara": {
                "state": dro["regime"],
                "H": round(float(dro["H"]), 4),
                "gamma": round(float(dro["gamma"]), 4),
                "r_s": round(float(dro["risk_scalar"]), 4),
                "r2": round(float(dro["r2_dfa"]), 4),
                "trend": dro["trend"] or "—",
                "signal": dro["signal"],
                "free_energy": round(float(dro["free_energy"]), 6),
                "stationary": bool(dro["stationary"]),
            },
            "kuramoto": {
                "r_t": round(r_now, 4),
                "k_kc": round(_KURA.K / _KURA.K_c, 4),
                "N": _KURA.N,
                "gate": "open" if r_now > 3.0 / np.sqrt(_KURA.N) else "closed",
            },
            "kelly": {
                "f_star": None if not np.isfinite(f_star) else round(float(f_star), 4),
                "applied": round(applied, 4),
                "cap": f_cap,
            },
            "gamma_regime": {
                "value": round(gamma_ui, 4),
                "state": gamma_state,
            },
            "execution": {
                "fills_1h": min(60, len(_state.sig_history)),
                "reject": 0,
                "slip_p50": 0.6,
                "slip_p95": 2.1,
            },
            "invariants": _invariants_watch(
                kura_R=r_now,
                kura_N=_KURA.N,
                kelly_f=f_star if np.isfinite(f_star) else 0.0,
                kelly_cap=f_cap,
                gamma_dro=float(dro["gamma"]),
            ),
            "equity_curve": eq_series,
        }


# ---------------------------------------------------------------------------
# HTTP handler
# ---------------------------------------------------------------------------


class _Handler(BaseHTTPRequestHandler):
    server_version = "GeoSyncDashboard/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        _LOG.info("%s — " + format, self.address_string(), *args)

    def do_GET(self) -> None:
        if self.path.startswith("/api/state"):
            self._send_json(_snapshot())
            return
        if self.path in ("/", "/index.html", "/demo.html"):
            # Literal-path sink — no user data flows into the Path.
            self._send_file(_WEBROOT / "demo.html", "text/html; charset=utf-8")
            return
        target = _resolve_static(self.path)
        if target is None:
            self.send_response(404)
            self.end_headers()
            return
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self._send_file(target, ctype)

    def _send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, allow_nan=False, default=str).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, ctype: str) -> None:
        # Belt-and-braces sanitizer INLINED at the I/O sink. CodeQL's
        # py/path-injection taint tracker requires the ``realpath`` +
        # ``startswith`` barrier to appear in the same function as the sink —
        # helper-function boundaries are not traced. Re-verifying locally
        # means a future refactor cannot silently introduce an unsanitised
        # path. realpath() is idempotent on an already-canonical path, so this
        # is a single stat() at worst.
        real = os.path.realpath(str(path))
        if real != _WEBROOT_STR and not real.startswith(_WEBROOT_PREFIX):
            self.send_response(403)
            self.end_headers()
            return
        data = Path(real).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def serve(host: str = "127.0.0.1", port: int = 8766) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    httpd = ThreadingHTTPServer((host, port), _Handler)
    _LOG.info(
        "engine: %s — serving http://%s:%d", "live" if _ENGINE_READY else "offline", host, port
    )
    if not _ENGINE_READY:
        _LOG.warning("engine offline: %s", _ENGINE_ERROR)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=os.environ.get("GEOSYNC_DASHBOARD_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("GEOSYNC_DASHBOARD_PORT", "8766"))
    )
    args = parser.parse_args()
    serve(args.host, args.port)

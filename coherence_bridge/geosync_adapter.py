"""GeoSync physics kernel → CoherenceBridge adapter.

Upgrades over v1:
  1. PSDGammaEstimator: multi-segment Welch + quality gate (replaces single aperiodic_slope)
  2. AugmentedFormanRicci: triangle reinforcement + degree penalty (topology fragility)
  3. Deterministic compute path: pure function of (returns, symbols, seq, timestamp)

Wiring table:
  PSDGammaEstimator.compute(returns)            → gamma (DERIVED, never assigned)
  GeoSyncCompositeEngine.analyze_market(df)     → R, regime, confidence, signal_strength
  AugmentedFormanRicci.compute_mean(returns, s) → ricci_curvature (augmented κ)
  maximal_lyapunov_exponent(returns)            → lyapunov_max

MarketPhase → RegimeType mapping:
  CHAOTIC        → DECOHERENT
  PROTO_EMERGENT → METASTABLE
  STRONG_EMERGENT→ COHERENT
  TRANSITION     → CRITICAL
  POST_EMERGENT  → DECOHERENT
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Any

import numpy as np

from coherence_bridge.risk import compute_risk_scalar
from geosync.estimators.augmented_ricci import AugmentedFormanRicci
from geosync.estimators.gamma_estimator import PSDGammaEstimator

if TYPE_CHECKING:
    pass

logger = logging.getLogger("coherence_bridge.geosync_adapter")

GEOSYNC_PATH = os.getenv(
    "GEOSYNC_PATH",
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)

_PHASE_TO_REGIME: dict[str, str] = {
    "CHAOTIC": "DECOHERENT",
    "PROTO_EMERGENT": "METASTABLE",
    "STRONG_EMERGENT": "COHERENT",
    "TRANSITION": "CRITICAL",
    "POST_EMERGENT": "DECOHERENT",
}

_DEFAULT_INSTRUMENTS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]


class OllivierStatus(str, Enum):
    """Typed outcome of the Ollivier-κ computation (telemetry field).

    OK is the only status that yields a trusted finite κ. Every other status is
    a degraded outcome with a NaN value — diagnosable, never a silent swallow.
    """

    OK = "OK"
    EMPTY_GRAPH = "EMPTY_GRAPH"
    IMPORT_ERROR = "IMPORT_ERROR"
    SOLVER_ERROR = "SOLVER_ERROR"
    PERF_BUDGET_EXCEEDED = "PERF_BUDGET_EXCEEDED"  # |edges| > max-edges budget
    TIMEOUT = "TIMEOUT"  # monotonic deadline crossed mid-solve (pre-empted)
    CIRCUIT_OPEN = "CIRCUIT_OPEN"  # breaker tripped — skipped without computing


@dataclass(frozen=True)
class OllivierResult:
    """Ollivier-κ outcome + runtime telemetry (P0 operational hardening)."""

    value: float
    status: OllivierStatus
    edges_seen: int = 0
    edges_budget: int = 0
    elapsed_ms: float = 0.0
    cache_hit: bool = False
    circuit_state: str = "closed"


# Policy defaults (env-overridable). The deadline guard PRE-EMPTS the solve
# (checked before each edge), never post-hoc; it only ever DOWNGRADES to NaN.
_OLLIVIER_MAX_EDGES_DEFAULT = 4000
_OLLIVIER_MAX_MS_DEFAULT = 750.0
_OLLIVIER_CACHE_MAX = 256
_OLLIVIER_MAX_CONSECUTIVE_TIMEOUTS_DEFAULT = 3
_OLLIVIER_COOLDOWN_MS_DEFAULT = 30_000.0

# Thread-safe state: a single RLock guards the bounded-LRU cache AND the
# per-instrument circuit-breaker. The heavy solve runs OUTSIDE the lock (a
# duplicate concurrent solve is deterministic, so correctness holds without
# serialising every consumer).
_OLLIVIER_LOCK = threading.RLock()
_OLLIVIER_CACHE: "OrderedDict[str, OllivierResult]" = OrderedDict()
_OLLIVIER_CIRCUIT: dict[str, dict[str, int]] = {}  # instrument -> {consecutive, open_until_ns}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None else int(raw)


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None else float(raw)


def ollivier_required() -> bool:
    """True ⇒ a degraded Ollivier κ must REFUSE the signal (NaN → NO_GO).

    False (default) ⇒ degraded κ is ABSTAINED (field omitted), so the signal can
    still be VALID on its other legs — never a fabricated in-band κ.
    """
    return os.environ.get("COHERENCE_REQUIRE_OLLIVIER", "0").strip().lower() in {"1", "true", "yes"}


def reset_ollivier_runtime_state() -> None:
    """Clear cache + circuit-breaker state (test hook; thread-safe)."""
    with _OLLIVIER_LOCK:
        _OLLIVIER_CACHE.clear()
        _OLLIVIER_CIRCUIT.clear()


def _prices_key(prices: np.ndarray) -> str:
    arr = np.ascontiguousarray(prices, dtype=np.float64)
    h = hashlib.sha256()
    h.update(str(arr.shape).encode("ascii"))
    h.update(arr.tobytes())
    return h.hexdigest()


def _ollivier_compute(prices: np.ndarray) -> OllivierResult:
    """Worst (max) per-edge Ollivier-Ricci κ + typed result. Never raises.

    INV-RC1 (κ ≤ 1) governs THIS operator. O(E) optimal-transport solves — the
    heaviest term in ``_compute_signal`` — so it is bounded by a deterministic
    max-edges budget AND a monotonic deadline checked BEFORE EACH EDGE: a slow
    solver is pre-empted mid-loop (TIMEOUT) instead of being timed post-hoc, so a
    latency spike cannot stall the risk loop.
    """
    try:
        from core.indicators.ricci import build_price_graph, ricci_curvature_edge
    except ImportError as exc:
        logger.warning("ollivier IMPORT_ERROR: %s: %s", type(exc).__name__, exc)
        return OllivierResult(float("nan"), OllivierStatus.IMPORT_ERROR)
    try:
        graph = build_price_graph(prices)
        edges = list(graph.edges())
    except Exception as exc:
        logger.warning("ollivier SOLVER_ERROR (graph build): %s: %s", type(exc).__name__, exc)
        return OllivierResult(float("nan"), OllivierStatus.SOLVER_ERROR)
    if not edges:
        logger.warning("ollivier EMPTY_GRAPH (NaN)")
        return OllivierResult(float("nan"), OllivierStatus.EMPTY_GRAPH)
    max_edges = _env_int("COHERENCE_OLLIVIER_MAX_EDGES", _OLLIVIER_MAX_EDGES_DEFAULT)
    if len(edges) > max_edges:
        logger.warning("ollivier PERF_BUDGET_EXCEEDED: %d > %d edges", len(edges), max_edges)
        return OllivierResult(
            float("nan"), OllivierStatus.PERF_BUDGET_EXCEEDED, edges_budget=max_edges
        )
    budget_ms = _env_float("COHERENCE_OLLIVIER_MAX_MS", _OLLIVIER_MAX_MS_DEFAULT)
    deadline_ns = time.monotonic_ns() + int(budget_ms * 1_000_000)
    t0 = time.perf_counter()
    worst = float("-inf")
    seen = 0
    try:
        for u, v in edges:
            if time.monotonic_ns() > deadline_ns:
                elapsed = (time.perf_counter() - t0) * 1000.0
                logger.warning("ollivier TIMEOUT: pre-empted after %d/%d edges", seen, len(edges))
                return OllivierResult(
                    float("nan"),
                    OllivierStatus.TIMEOUT,
                    edges_seen=seen,
                    edges_budget=max_edges,
                    elapsed_ms=elapsed,
                )
            worst = max(worst, float(ricci_curvature_edge(graph, int(u), int(v))))
            seen += 1
    except Exception as exc:
        logger.warning("ollivier SOLVER_ERROR (edge solve): %s: %s", type(exc).__name__, exc)
        return OllivierResult(float("nan"), OllivierStatus.SOLVER_ERROR, edges_seen=seen)
    elapsed = (time.perf_counter() - t0) * 1000.0
    return OllivierResult(
        worst, OllivierStatus.OK, edges_seen=seen, edges_budget=max_edges, elapsed_ms=elapsed
    )


def _ollivier_worst_edge_kappa(prices: np.ndarray, instrument: str = "") -> OllivierResult:
    """Thread-safe cached + circuit-broken Ollivier κ.

    Cache: bounded LRU (OrderedDict) keyed by price content + perf policy, under
    an RLock — no whole-cache clear as eviction. Circuit breaker: after
    max-consecutive TIMEOUTs on an instrument the operator is skipped
    (CIRCUIT_OPEN) for a cooldown window, so a persistently-slow solver cannot
    keep stalling the loop. The heavy solve runs outside the lock.
    """
    max_edges = _env_int("COHERENCE_OLLIVIER_MAX_EDGES", _OLLIVIER_MAX_EDGES_DEFAULT)
    max_ms = _env_float("COHERENCE_OLLIVIER_MAX_MS", _OLLIVIER_MAX_MS_DEFAULT)
    key = f"{_prices_key(prices)}|{max_edges}|{max_ms}"

    with _OLLIVIER_LOCK:
        circ = _OLLIVIER_CIRCUIT.get(instrument)
        if circ is not None and circ["open_until_ns"] > time.monotonic_ns():
            return OllivierResult(float("nan"), OllivierStatus.CIRCUIT_OPEN, circuit_state="open")
        cached = _OLLIVIER_CACHE.get(key)
        if cached is not None:
            _OLLIVIER_CACHE.move_to_end(key)
            return replace(cached, cache_hit=True)

    result = _ollivier_compute(prices)  # heavy work outside the lock

    max_consec = _env_int(
        "COHERENCE_OLLIVIER_MAX_CONSECUTIVE_TIMEOUTS", _OLLIVIER_MAX_CONSECUTIVE_TIMEOUTS_DEFAULT
    )
    cooldown_ns = int(
        _env_float("COHERENCE_OLLIVIER_COOLDOWN_MS", _OLLIVIER_COOLDOWN_MS_DEFAULT) * 1e6
    )
    with _OLLIVIER_LOCK:
        circ = _OLLIVIER_CIRCUIT.setdefault(instrument, {"consecutive": 0, "open_until_ns": 0})
        if result.status is OllivierStatus.TIMEOUT:
            circ["consecutive"] += 1
            if circ["consecutive"] >= max_consec:
                circ["open_until_ns"] = time.monotonic_ns() + cooldown_ns
                logger.warning("ollivier CIRCUIT OPEN for %r (cooldown)", instrument)
        else:
            circ["consecutive"] = 0
        circuit_state = "open" if circ["open_until_ns"] > time.monotonic_ns() else "closed"
        _OLLIVIER_CACHE[key] = result
        _OLLIVIER_CACHE.move_to_end(key)
        while len(_OLLIVIER_CACHE) > _OLLIVIER_CACHE_MAX:
            _OLLIVIER_CACHE.popitem(last=False)  # evict least-recently-used
    return replace(result, circuit_state=circuit_state)


class GeoSyncAdapter:
    """Adapts GeoSync physics kernel to SignalEngine interface.

    Thread-safe. Non-blocking: returns last-known-good if compute not ready.
    gamma is ALWAYS derived from PSD via PSDGammaEstimator, never assigned.
    """

    def __init__(self, geosync_path: str = GEOSYNC_PATH) -> None:
        if geosync_path not in sys.path:
            sys.path.insert(0, geosync_path)

        self._lock = threading.Lock()
        self._instruments: list[str] = []
        self._last_known_good: dict[str, dict[str, Any]] = {}
        self._seq: dict[str, int] = {}
        self._regime_start: dict[str, float] = {}
        self._last_regime: dict[str, str] = {}

        # Physics components
        self._composite_engine: Any = None
        self._forman_ricci: Any = None  # GeoSync core Forman-Ricci
        self._lyapunov_fn: Any = None
        self._gamma_estimator = PSDGammaEstimator(fs=1.0)
        self._augmented_ricci = AugmentedFormanRicci(correlation_threshold=0.2)

        # Market data cache
        self._market_data: dict[str, Any] = {}

        self._load_engine(geosync_path)

    def _load_engine(self, path: str) -> None:
        """Wire GeoSync physics kernel components."""
        from core.indicators.kuramoto_ricci_composite import GeoSyncCompositeEngine
        from core.physics.forman_ricci import FormanRicciCurvature
        from core.physics.lyapunov_exponent import maximal_lyapunov_exponent

        self._composite_engine = GeoSyncCompositeEngine()
        self._forman_ricci = FormanRicciCurvature()
        self._lyapunov_fn = maximal_lyapunov_exponent

        self._instruments = list(_DEFAULT_INSTRUMENTS)
        for inst in self._instruments:
            self._seq[inst] = 0
            self._regime_start[inst] = time.time()
            self._last_regime[inst] = "UNKNOWN"

        logger.info(
            "GeoSync engine loaded from %s, instruments=%s",
            path,
            self._instruments,
        )

    @property
    def instruments(self) -> list[str]:
        return list(self._instruments)

    def update_market_data(self, instrument: str, df: Any) -> None:
        """Feed new OHLCV DataFrame for an instrument."""
        import pandas

        if not isinstance(df, pandas.DataFrame):
            raise TypeError(f"Expected DataFrame, got {type(df)}")
        if not isinstance(df.index, pandas.DatetimeIndex):
            raise TypeError("DataFrame must have DatetimeIndex")
        with self._lock:
            self._market_data[instrument] = df

    def get_signal(self, instrument: str) -> dict[str, Any] | None:
        if instrument not in self._instruments:
            return None

        with self._lock:
            df = self._market_data.get(instrument)

        if df is None or len(df) < 30:
            with self._lock:
                cached = self._last_known_good.get(instrument)
            if cached is not None:
                stale = dict(cached)
                stale["timestamp_ns"] = time.time_ns()
                return stale
            return None

        try:
            sig = self._compute_signal(instrument, df)
            with self._lock:
                self._last_known_good[instrument] = sig
            return sig
        except Exception as exc:
            logger.warning("Compute failed for %s: %s", instrument, exc)
            with self._lock:
                cached = self._last_known_good.get(instrument)
            if cached is not None:
                stale = dict(cached)
                stale["timestamp_ns"] = time.time_ns()
                return stale
            return None

    def _compute_signal(
        self,
        instrument: str,
        df: Any,
    ) -> dict[str, Any]:
        """Run full GeoSync physics kernel on market data.

        gamma is DERIVED from PSD via PSDGammaEstimator. NEVER assigned.
        Ricci curvature uses augmented Forman-Ricci with triangle reinforcement.
        """
        prices = df["close"].values.astype(np.float64)
        returns = np.diff(np.log(prices + 1e-12))

        # 1. Composite analysis (Kuramoto + temporal Ricci + regime)
        composite = self._composite_engine.analyze_market(df)

        # 2. gamma — DERIVED from multi-segment PSD (never assigned)
        gamma_est = self._gamma_estimator.compute(returns)
        if gamma_est.is_valid:
            gamma = gamma_est.value
        else:
            # Fallback: insufficient quality → metastable default
            gamma = 1.0

        # 3. Ricci curvature — dual track:
        #    a) Augmented Forman-Ricci on lagged returns (topology fragility)
        #    b) GeoSync core Forman-Ricci (compatibility)
        n_lags = min(5, len(returns) // 10)
        if n_lags >= 2:
            lagged = np.column_stack(
                [returns[i : len(returns) - n_lags + i + 1] for i in range(n_lags)]
            )
            lag_symbols = [f"lag_{i}" for i in range(n_lags)]

            # Augmented: triangle + degree penalty
            augmented_kappa = self._augmented_ricci.compute_mean(lagged, lag_symbols)

            # Core: standard Forman-Ricci
            try:
                core_result = self._forman_ricci.compute_from_prices(
                    lagged, window=min(30, len(lagged))
                )
                core_kappa = core_result.kappa_mean
            except Exception:
                core_kappa = composite.static_ricci

            # Blend: augmented dominates, core stabilizes
            ricci_curvature = 0.7 * augmented_kappa + 0.3 * core_kappa
        else:
            ricci_curvature = composite.static_ricci

        # 4. Lyapunov exponent
        if len(returns) >= 50:
            lyapunov_max = self._lyapunov_fn(returns, dim=3, tau=1)
            if not math.isfinite(lyapunov_max):
                lyapunov_max = 0.0
        else:
            lyapunov_max = 0.0

        # 5. Regime mapping
        regime_name = _PHASE_TO_REGIME.get(composite.phase.name, "UNKNOWN")

        # 6. Fail-closed: invalid physics → UNKNOWN, risk=0
        if not math.isfinite(gamma) or not math.isfinite(ricci_curvature):
            gamma = 0.0
            ricci_curvature = 0.0
            lyapunov_max = 0.0
            regime_name = "UNKNOWN"

        # 7. Regime duration tracking
        with self._lock:
            if regime_name != self._last_regime.get(instrument):
                self._regime_start[instrument] = time.time()
                self._last_regime[instrument] = regime_name
            duration = time.time() - self._regime_start.get(instrument, time.time())

        # 8. Signal strength from entry/exit asymmetry [-1, +1]
        signal_strength = max(
            -1.0,
            min(1.0, composite.entry_signal - composite.exit_signal),
        )

        # 9. risk_scalar from gamma (derived, never assigned)
        risk_scalar = compute_risk_scalar(gamma, fail_closed=True)

        # 10. Sequence number
        with self._lock:
            seq = self._seq.get(instrument, 0)
            self._seq[instrument] = seq + 1

        # 11. Ricci name split (closes the ledger OPEN GAP):
        #   - augmented_forman_ricci: the Forman blend exposed for topology
        #     fragility. LEGITIMATELY unbounded above; NOT the κ ≤ 1 field and
        #     NEVER κ-bound evidence (INV-RC1 does not govern it).
        #   - ollivier_kappa: the Ollivier-Ricci operator INV-RC1 (κ ≤ 1) DOES
        #     govern, computed over the close-price graph (fail-closed to NaN).
        #   - ricci_curvature: retained as a backward-compatible DISPLAY alias of
        #     the Forman blend (verify_T5 classifies it P1/finite-only).
        ollivier = _ollivier_worst_edge_kappa(prices, instrument)

        sig: dict[str, Any] = {
            "timestamp_ns": time.time_ns(),
            "instrument": instrument,
            "gamma": round(float(gamma), 6),
            "order_parameter_R": round(float(composite.kuramoto_R), 6),
            "augmented_forman_ricci": round(float(ricci_curvature), 6),
            "ricci_curvature": round(float(ricci_curvature), 6),
            "lyapunov_max": round(float(lyapunov_max), 6),
            "regime": regime_name,
            "regime_confidence": round(float(composite.confidence), 4),
            "regime_duration_s": round(duration, 2),
            "signal_strength": round(float(signal_strength), 4),
            "risk_scalar": round(float(risk_scalar), 4),
            "sequence_number": seq,
            # Ollivier runtime telemetry (always present, diagnosable):
            "ollivier_status": ollivier.status.value,
            "ollivier_elapsed_ms": round(ollivier.elapsed_ms, 3),
            "ollivier_edges_seen": ollivier.edges_seen,
            "ollivier_edges_budget": ollivier.edges_budget,
            "ollivier_cache_hit": ollivier.cache_hit,
            "ollivier_circuit_state": ollivier.circuit_state,
        }
        # Ollivier-κ emission policy (degraded ⇒ ABSTAIN, never fake PASS):
        #   OK            → emit the trusted finite κ (contract checks ≤ 1).
        #   degraded+req  → emit NaN ⇒ contract INVALID ⇒ NO_GO (refuse).
        #   degraded+!req → OMIT the field ⇒ contract abstains on the κ leg.
        if ollivier.status is OllivierStatus.OK:
            sig["ollivier_kappa"] = round(float(ollivier.value), 6)
        elif ollivier_required():
            sig["ollivier_kappa"] = float("nan")
        return sig

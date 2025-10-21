# SPDX-License-Identifier: MIT
"""Ricci curvature-based structural stress indicators for price graphs.

This module turns price histories into discrete graphs and computes
Ollivier–Ricci curvature to characterise structural fragility. The approach
follows the geometric market diagnostics documented in ``docs/indicators.md``
and the resilience monitoring playbooks in ``docs/risk_ml_observability.md``.
By embedding curvature metrics into the feature stack, we meet the governance
requirement that core risk signals expose interpretable topology, as detailed
in ``docs/documentation_governance.md``.

Upstream data arrives from the ingestion pipeline via indicator callers, while
downstream consumers include the feature engineering stack, execution risk
monitoring, and CLI diagnostics in ``interfaces/cli.py``. Key dependencies
include optional NetworkX (with an in-repo fallback) for graph manipulation,
NumPy for numerical work, and SciPy for Wasserstein distances when available.
The module records telemetry using ``core.utils`` helpers to satisfy
traceability expectations laid out in ``docs/quality_gates.md`` and to
coordinate with the governance guardrails documented in ``docs/monitoring.md``.
"""

from __future__ import annotations

import asyncio
import logging
import warnings
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Iterable, Literal

import numpy as np

from ..utils.logging import get_logger
from ..utils.metrics import get_metrics_collector
from .base import BaseFeature, FeatureResult

_logger = get_logger(__name__)
_metrics = get_metrics_collector()


def _log_debug_enabled() -> bool:
    base_logger = getattr(_logger, "logger", None)
    check = getattr(base_logger, "isEnabledFor", None)
    return bool(check and check(logging.DEBUG))


def _is_runtime_warning_forced() -> bool:
    """Return True when global filters force RuntimeWarning emission."""

    for filt in warnings.filters:
        action, _msg, category, _module, _lineno, *_rest = filt
        if action == "always" and issubclass(RuntimeWarning, category):
            return True
    return False


try:
    import networkx as nx
except Exception:  # pragma: no cover - fallback for lightweight environments

    class _SimpleGraph:
        def __init__(self) -> None:
            self._adj: dict[int, dict[int, float]] = {}

        def add_node(self, node: int) -> None:
            self._adj.setdefault(int(node), {})

        def add_nodes_from(self, nodes: Iterable[int]) -> None:
            for node in nodes:
                self.add_node(int(node))

        def add_edge(self, u: int, v: int, weight: float | None = None) -> None:
            self.add_node(int(u))
            self.add_node(int(v))
            w = float(weight if weight is not None else 1.0)
            self._adj[int(u)][int(v)] = w
            self._adj[int(v)][int(u)] = w

        def neighbors(self, node: int) -> Iterable[int]:
            return tuple(self._adj.get(int(node), ()))

        def degree(
            self,
            node: int | None = None,
            weight: str | None = None,
        ) -> Iterable[tuple[int, float]] | float:
            if node is None:
                if weight:
                    return tuple(
                        (n, sum(neigh.values())) for n, neigh in self._adj.items()
                    )
                return tuple((n, len(neigh)) for n, neigh in self._adj.items())
            neigh = self._adj.get(int(node), {})
            return sum(neigh.values()) if weight else len(neigh)

        def nodes(self) -> Iterable[int]:
            return tuple(self._adj.keys())

        def number_of_edges(self) -> int:
            return sum(len(neigh) for neigh in self._adj.values()) // 2

        def edges(
            self,
            data: bool = False,
        ) -> Iterable[tuple[int, int] | tuple[int, int, dict[str, float]]]:
            seen: set[tuple[int, int]] = set()
            for u, neigh in self._adj.items():
                for v in neigh:
                    edge = (min(u, v), max(u, v))
                    if edge not in seen:
                        seen.add(edge)
                        if data:
                            yield (edge[0], edge[1], {"weight": neigh[v]})
                        else:
                            yield edge

        def has_edge(self, u: int, v: int) -> bool:
            return int(v) in self._adj.get(int(u), set())

        def number_of_nodes(self) -> int:
            return len(self._adj)

        def shortest_path_length(
            self,
            source: int,
            target: int,
            weight: str | None = None,
        ) -> float:
            import heapq

            if source == target:
                return 0.0
            distances = {source: 0.0}
            heap: list[tuple[float, int]] = [(0.0, source)]
            while heap:
                dist, node = heapq.heappop(heap)
                if node == target:
                    return dist
                if dist > distances.get(node, float("inf")):
                    continue
                for neigh, w in self._adj.get(node, {}).items():
                    step = w if weight else 1.0
                    nd = dist + step
                    if nd < distances.get(neigh, float("inf")):
                        distances[neigh] = nd
                        heapq.heappush(heap, (nd, neigh))
            return float("inf")

        def get_edge_data(
            self,
            u: int,
            v: int,
            default: dict[str, float] | None = None,
        ) -> dict[str, float] | None:
            weight = self._adj.get(int(u), {}).get(int(v))
            if weight is None:
                return default
            return {"weight": weight}

    class _NXModule:  # pragma: no cover
        Graph = _SimpleGraph

    nx = _NXModule()  # type: ignore[assignment]

try:  # pragma: no cover - SciPy optional
    from scipy.spatial.distance import wasserstein_distance as W1
except Exception:  # pragma: no cover
    W1 = None


_W1_WARNING_LOCK = Lock()
_W1_WARNING_EMITTED = False


def build_price_graph(prices: np.ndarray, delta: float = 0.005) -> nx.Graph:
    """Quantise a price path into a level graph.

    Args:
        prices: One-dimensional array of strictly positive prices representing a
            single asset history.
        delta: Relative price increment controlling the resolution of quantised
            levels as documented in ``docs/indicators.md``.

    Returns:
        nx.Graph: Undirected graph whose nodes correspond to discretised price
        levels and whose edges capture successive transitions weighted by price
        deltas.

    Examples:
        >>> prices = np.array([100.0, 100.5, 101.0])
        >>> G = build_price_graph(prices, delta=0.01)
        >>> sorted(G.nodes())
        [-0, 1, 2]

    Notes:
        Non-finite prices are removed before quantisation in accordance with the
        cleansing contract in ``docs/documentation_governance.md``. Empty or
        degenerate series yield an empty graph, keeping downstream curvature
        computations stable.
    """
    p = np.asarray(prices, dtype=float)
    mask = np.isfinite(p)
    if mask.sum() < 2:
        return nx.Graph()
    p = p[mask]
    base = p[0]
    scale = float(abs(base))
    if not np.isfinite(scale) or scale == 0.0:
        scale = 1.0
    levels = np.round((p - base) / (scale * delta)).astype(int)
    G = nx.Graph()
    for i, lv in enumerate(levels):
        G.add_node(int(lv))
        if i > 0:
            weight = float(abs(p[i] - p[i - 1])) + 1.0
            G.add_edge(int(levels[i - 1]), int(lv), weight=weight)
    return G


def local_distribution(G: nx.Graph, node: int, radius: int = 1) -> np.ndarray:
    """Return the degree-weighted probability mass over a node's neighbourhood.

    Args:
        G: Graph produced by :func:`build_price_graph` or a compatible structure.
        node: Node identifier whose neighbourhood distribution is required.
        radius: Currently unused, reserved for future extensions involving
            multi-hop neighbourhoods.

    Returns:
        np.ndarray: Probability vector whose elements sum to one and correspond
        to the relative transition weights from ``node``.

    Notes:
        When ``node`` is isolated a single mass ``[1.0]`` is returned to avoid
        downstream NaNs. Edge weights are sanitised to remain finite, matching
        the governance requirements of ``docs/quality_gates.md``.
    """
    neigh = [n for n in G.neighbors(node)]
    if not neigh:  # pragma: no cover - defensive guard for isolated nodes
        return np.array([1.0])
    weights = []
    for n in neigh:
        data = G.get_edge_data(node, n, default={"weight": 1.0})
        weight = float(data.get("weight", 1.0))
        if not np.isfinite(weight):
            weight = 1.0
        weights.append(weight)
    w_arr = np.asarray(weights, dtype=float)
    total = w_arr.sum()
    if total == 0:  # pragma: no cover - degenerate weights
        return np.full(len(neigh), 1.0 / len(neigh))
    return w_arr / total


def ricci_curvature_edge(G: nx.Graph, x: int, y: int) -> float:
    """Evaluate the Ollivier–Ricci curvature for a specific edge.

    Args:
        G: Graph describing price transitions.
        x: Source node identifier.
        y: Target node identifier.

    Returns:
        float: Curvature value in the range ``(-∞, 1]`` where negative values
        denote dispersion and positive values indicate clustering.

    Notes:
        The implementation normalises discrete neighbourhood measures and uses
        SciPy's Wasserstein distance when available, falling back to a cumulative
        distribution approximation otherwise. Shortest-path calculations are
        hardened through :func:`_shortest_path_length_safe`, aligning with the
        numerical stability guidance in ``docs/monitoring.md``.
    """
    if not G.has_edge(x, y):  # pragma: no cover - caller ensures edge exists
        return 0.0
    mu_x = local_distribution(G, x)
    mu_y = local_distribution(G, y)
    # for simple comparison, map distributions to common support by padding
    m = max(len(mu_x), len(mu_y))
    a = np.pad(mu_x, (0, m - len(mu_x)))
    b = np.pad(mu_y, (0, m - len(mu_y)))
    d_xy = _shortest_path_length_safe(G, x, y)
    if not np.isfinite(d_xy) or d_xy <= 0:
        return 0.0
    if W1 is None:
        global _W1_WARNING_EMITTED
        force_warning = _is_runtime_warning_forced()
        if force_warning or not _W1_WARNING_EMITTED:
            with _W1_WARNING_LOCK:
                # Re-evaluate after acquiring the lock to honour concurrent updates.
                force_warning = force_warning or _is_runtime_warning_forced()
                if force_warning or not _W1_WARNING_EMITTED:
                    warnings.warn(
                        "SciPy unavailable; using discrete Wasserstein approximation for Ricci curvature",
                        RuntimeWarning,
                        stacklevel=2,
                    )
                    if not force_warning:
                        _W1_WARNING_EMITTED = True
    dist = W1(a, b) if W1 is not None else _w1_fallback(a, b)
    return float(1.0 - dist / d_xy)


def _shortest_path_length_safe(G: nx.Graph, x: int, y: int) -> float:
    """Return a robust shortest-path distance tolerant to malformed weights.

    Args:
        G: Graph describing price transitions.
        x: Source node identifier.
        y: Target node identifier.

    Returns:
        float: Weighted path length, falling back to unweighted distance when
        weight metadata is invalid. ``inf`` is returned when no path exists.

    Notes:
        The helper logs debug diagnostics when weight issues arise, which feed
        into the risk observability pipeline in ``docs/risk_ml_observability.md``.
    """

    def _call_shortest_path(graph: nx.Graph, weight: str | None) -> float:
        if hasattr(graph, "shortest_path_length"):
            return graph.shortest_path_length(x, y, weight=weight)
        return nx.shortest_path_length(graph, x, y, weight=weight)

    try:
        return float(_call_shortest_path(G, "weight"))
    except ValueError as exc:
        if _log_debug_enabled():
            _logger.debug(
                "ricci.shortest_path: falling back to unweighted distance for edge (%s,%s)",
                x,
                y,
                error=str(exc),
            )
        try:
            return float(_call_shortest_path(G, None))
        except Exception:
            return float("inf")


def mean_ricci(
    G: nx.Graph,
    *,
    chunk_size: int | None = None,
    use_float32: bool = False,
    parallel: Literal["none", "async"] = "none",
    max_workers: int | None = None,
) -> float:
    """Compute the mean Ollivier–Ricci curvature of a price graph.

    Args:
        G: Input graph whose edge weights encode price transition costs.
        chunk_size: Optional batch size for edge iteration to bound memory usage.
        use_float32: When ``True``, accumulate in ``float32`` as a performance
            trade-off.
        parallel: Execution strategy. Set to ``"async"`` to evaluate edges via an
            asyncio-backed thread pool, mirroring the scaling guidance in
            ``docs/execution.md``.
        max_workers: Upper bound for the thread pool when ``parallel`` is async.

    Returns:
        float: Mean curvature value across all edges. ``0.0`` is returned for
        empty graphs.

    Raises:
        RuntimeError: Propagated if asynchronous execution fails to initialise a
            loop.

    Notes:
        High positive curvature implies tightly connected price states, while
        negative curvature indicates dispersion—a signal cross-referenced by the
        monitoring blueprint in ``docs/risk_ml_observability.md``. ``float32``
        accumulation is recommended only when graphs exceed ~50k edges; otherwise
        ``float64`` provides more stable averages.
    """
    with _logger.operation(
        "mean_ricci",
        edges=G.number_of_edges(),
        nodes=G.number_of_nodes(),
        chunk_size=chunk_size,
        use_float32=use_float32,
        parallel=parallel,
    ):
        if G.number_of_edges() == 0:
            return 0.0

        edges = list(G.edges())

        # Chunked processing for large graphs
        if chunk_size is not None and len(edges) > chunk_size:
            dtype = np.float32 if use_float32 else float
            curvatures = []

            for i in range(0, len(edges), chunk_size):
                chunk_edges = edges[i : i + chunk_size]
                chunk_curv = [ricci_curvature_edge(G, u, v) for u, v in chunk_edges]
                curvatures.extend(chunk_curv)

            return float(np.mean(np.array(curvatures, dtype=dtype)))

        # Standard processing
        if parallel == "async":
            curv = _run_ricci_async(G, edges, max_workers)
        else:
            curv = [ricci_curvature_edge(G, u, v) for u, v in edges]
        dtype = np.float32 if use_float32 else float
        if not curv:  # pragma: no cover - empty graph handled above
            return 0.0
        arr = np.array(curv, dtype=dtype)
        arr = arr[np.isfinite(arr)]
        if arr.size == 0:  # pragma: no cover - defensive guard
            return 0.0
        return float(np.mean(arr))


def _run_ricci_async(
    G: nx.Graph,
    edges: list[tuple[int, int]],
    max_workers: int | None,
) -> list[float]:
    """Evaluate curvature across edges concurrently using asyncio threads."""

    async def _runner() -> list[float]:
        loop = asyncio.get_running_loop()
        executor: ThreadPoolExecutor | None = None
        try:
            if max_workers is not None:
                executor = ThreadPoolExecutor(max_workers=max_workers)
            futures = [
                loop.run_in_executor(executor, ricci_curvature_edge, G, int(u), int(v))
                for u, v in edges
            ]
            return await asyncio.gather(*futures)
        finally:
            if executor is not None:
                executor.shutdown(wait=True)

    try:
        return asyncio.run(_runner())
    except RuntimeError as exc:
        if "event loop is running" not in str(exc):
            raise
        new_loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(new_loop)
            return new_loop.run_until_complete(_runner())
        finally:
            asyncio.set_event_loop(None)
            new_loop.close()


def _w1_fallback(a: np.ndarray, b: np.ndarray) -> float:
    """Approximate the Wasserstein-1 distance when SciPy is unavailable.

    The implementation follows the discrete formulation of the
    Kantorovich-Rubinstein dual on an equally spaced support. This matches
    SciPy's ``wasserstein_distance`` for one-dimensional histograms whose bins
    share a uniform spacing of ``1``. The inputs are treated as probability
    masses and therefore undergo sanitisation (non-finite values are converted
    to ``0`` and negative entries are clipped) before normalisation. The
    cumulative difference of the distributions is then integrated in ``L1``
    space, which is a numerically stable operation for medium-sized arrays
    (cf. ``docs/indicators.md``).

    Args:
        a: First discrete probability mass function.
        b: Second discrete probability mass function.

    Returns:
        float: The 1-Wasserstein distance between the two discrete
        distributions.

    Raises:
        ValueError: Raised when the input shapes differ.
    """

    a_arr = np.array(a, dtype=float, copy=True).reshape(-1)
    b_arr = np.array(b, dtype=float, copy=True).reshape(-1)

    if a_arr.shape != b_arr.shape:
        raise ValueError("Distributions must share the same shape")

    if a_arr.size == 0:
        return 0.0

    a_arr = np.nan_to_num(a_arr, nan=0.0, posinf=0.0, neginf=0.0)
    b_arr = np.nan_to_num(b_arr, nan=0.0, posinf=0.0, neginf=0.0)

    np.clip(a_arr, 0.0, None, out=a_arr)
    np.clip(b_arr, 0.0, None, out=b_arr)

    total_a = float(a_arr.sum())
    total_b = float(b_arr.sum())

    if not np.isfinite(total_a) or not np.isfinite(total_b):
        raise ValueError("Distributions must have finite total mass")

    if total_a > 0.0:
        a_arr /= total_a
    else:
        a_arr.fill(0.0)

    if total_b > 0.0:
        b_arr /= total_b
    else:
        b_arr.fill(0.0)

    cdf_difference = np.add.accumulate(a_arr - b_arr)
    return float(np.sum(np.abs(cdf_difference)))


class MeanRicciFeature(BaseFeature):
    """Feature wrapper for mean Ollivier–Ricci curvature.

    The feature converts a univariate price series into a quantised graph using
    :func:`build_price_graph` and then averages edge-level curvature. This is the
    production-ready implementation referenced in ``docs/indicators.md`` and the
    ``docs/risk_ml_observability.md`` control blueprint.

    Attributes are configured via the constructor to align the feature with
    portfolio monitoring guidelines (see ``docs/monitoring.md``).
    """

    def __init__(
        self,
        delta: float = 0.005,
        *,
        chunk_size: int | None = None,
        use_float32: bool = False,
        parallel_async: bool = False,
        max_workers: int | None = None,
        name: str | None = None,
    ) -> None:
        """Initialise the feature configuration.

        Args:
            delta: Price quantisation granularity.
            chunk_size: Process edges in chunks for large graphs.
            use_float32: Use ``float32`` precision for memory efficiency.
            parallel_async: Execute curvature computations concurrently via
                asyncio thread pools.
            max_workers: Optional cap for the async worker pool when
                ``parallel_async`` is enabled.
            name: Optional custom name.
        """
        super().__init__(name or "mean_ricci")
        self.delta = float(delta)
        self.chunk_size = chunk_size
        self.use_float32 = use_float32
        self.parallel_async = parallel_async
        self.max_workers = max_workers

    def transform(self, data: np.ndarray, **_: Any) -> FeatureResult:
        """Compute mean Ricci curvature of the price graph.

        Args:
            data: Price array used to build the underlying graph.
            **_: Additional keyword arguments (ignored).

        Returns:
            FeatureResult: Mean curvature value and metadata about graph size.
        """

        with _metrics.measure_feature_transform(self.name, "ricci"):
            G = build_price_graph(data, delta=self.delta)
            value = mean_ricci(
                G,
                chunk_size=self.chunk_size,
                use_float32=self.use_float32,
                parallel="async" if self.parallel_async else "none",
                max_workers=self.max_workers,
            )
            _metrics.record_feature_value(self.name, value)
            metadata: dict[str, Any] = {
                "delta": self.delta,
                "nodes": G.number_of_nodes(),
                "edges": G.number_of_edges(),
            }
            if self.use_float32:
                metadata["use_float32"] = True
            if self.chunk_size is not None:
                metadata["chunk_size"] = self.chunk_size
            if self.parallel_async:
                metadata["parallel"] = "async"
            if self.max_workers is not None:
                metadata["max_workers"] = self.max_workers
            return FeatureResult(name=self.name, value=value, metadata=metadata)


__all__ = [
    "build_price_graph",
    "local_distribution",
    "ricci_curvature_edge",
    "mean_ricci",
    "MeanRicciFeature",
]

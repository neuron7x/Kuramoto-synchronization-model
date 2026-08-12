# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""D-002J-P4 — planted positive controls v1 (synthetic ground truth).

This module implements six SYNTHETIC positive-control families with KNOWN
ground truth and per-family negative siblings. Each family generates a
deterministic, numpy-only synthetic dataset under an explicit seed and
returns a :class:`ControlInstance` carrying:

* ``id`` / ``family`` / ``seed`` / ``params`` provenance,
* ``signal_array`` — the planted-signal realisation,
* ``null_sibling_array`` — the matched null realisation (same shape,
  same seed-derived noise generator, signal turned off),
* ``ground_truth_metadata`` — the planted onset/effect-size/topology.

Every family also implements ``score(arr)`` returning a single non-
negative scalar observable. The pipeline acceptance contract is:

* ``score(signal) >= pass_threshold`` for the positive control,
* ``score(null) <  pass_threshold`` for the negative sibling.

PC5 (information-delay / vintage-leakage trap) is INVERTED: pass means
the pipeline DETECTS the lookahead violation and REJECTS the leaking
detector. The :func:`PC5InfoDelayLeakageTrap.score` returns
``1.0`` iff a leakage detector is supplied and any of its synthetic
"signals" use post-decision data; ``0.0`` otherwise.

Discipline boundaries:

* All synthesis is deterministic (``numpy.random.default_rng(seed)``);
  no wall-clock dependence.
* No file reads from ``artifacts/d002j/ingestion/`` or anywhere else.
* No real-world claim. Synthetic only.
* Pass on these controls does NOT prove real-world detection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Final

import numpy as np
from numpy.typing import NDArray

# ---------------------------------------------------------------------------
# Constants & schema versions
# ---------------------------------------------------------------------------

SCHEMA_CONTROL_INSTANCE: Final[str] = "D002J-POSITIVE-CONTROL-INSTANCE-v1"
"""Schema version stamped onto every :class:`ControlInstance`."""

PC5_PASS_TOKEN: Final[float] = 1.0
"""Score value emitted by PC5 when leakage IS caught by the detector."""

PC5_FAIL_TOKEN: Final[float] = 0.0
"""Score value emitted by PC5 when the leakage-using detector slips through."""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ControlInstance:
    """Frozen, hashable record of one synthetic positive-control realisation.

    The two arrays (``signal_array`` + ``null_sibling_array``) share shape
    and are produced by the same seed-derived rng so that any difference
    between them is attributable to the planted signal, not to noise.
    """

    schema_version: str
    id: str
    family: str
    seed: int
    params: dict[str, Any]
    signal_array: NDArray[np.float64]
    null_sibling_array: NDArray[np.float64]
    ground_truth_metadata: dict[str, Any]

    def shapes_match(self) -> bool:
        """Return True iff signal/null arrays are the same shape."""
        return self.signal_array.shape == self.null_sibling_array.shape


@dataclass(frozen=True)
class ControlFamilySpec:
    """Static declaration of one control family (pure metadata, no synthesis)."""

    family_id: str
    control_class: str
    ground_truth_fields: tuple[str, ...]
    negative_sibling_id: str
    expected_observable_signature: str
    pass_threshold_metric: str
    pass_threshold_value: float
    fail_threshold_metric: str
    fail_threshold_value: float
    mapped_p5_substrate_candidates: tuple[str, ...]
    mapped_p2_window_class: tuple[str, ...]
    forbidden_claim_boundary: str
    hidden_until_scoring: bool = True


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class PositiveControlFamily:
    """Abstract base for all PCn families.

    Subclasses set the class-level :attr:`SPEC` and take no constructor
    args; the base ``__init__`` binds ``self.spec`` from that attribute.
    This keeps every subclass constructor signature identical
    (``__init__(self) -> None``) so the registry can instantiate any
    family uniformly.
    """

    family_id: str = "ABSTRACT"
    control_class: str = "abstract"
    SPEC: ControlFamilySpec | None = None

    def __init__(self) -> None:
        if self.SPEC is None:
            msg = f"{type(self).__name__} must set class attribute SPEC"
            raise NotImplementedError(msg)
        self.spec: ControlFamilySpec = self.SPEC

    def generate(self, seed: int, params: dict[str, Any]) -> ControlInstance:
        """Synthesise one signal+null realisation under *seed*."""
        msg = f"generate() not implemented for {type(self).__name__}"
        raise NotImplementedError(msg)

    def score(self, arr: NDArray[np.float64]) -> float:
        """Return a non-negative scalar observable for *arr*.

        Each subclass implements the observable consistent with its
        ``expected_observable_signature``. The pipeline asserts:
        ``score(signal) >= pass_threshold`` and
        ``score(null)   <  pass_threshold``.
        """
        msg = f"score() not implemented for {type(self).__name__}"
        raise NotImplementedError(msg)


# ---------------------------------------------------------------------------
# PC1 — liquidity shock injection
# ---------------------------------------------------------------------------


PC1_SPEC: Final[ControlFamilySpec] = ControlFamilySpec(
    family_id="PC1_LIQUIDITY_SHOCK_INJECTION",
    control_class="liquidity_shock",
    ground_truth_fields=("onset_time", "effect_size", "propagation_radius", "shocked_node"),
    negative_sibling_id="PC1_NEGATIVE_SIBLING",
    expected_observable_signature=(
        "worst-node post-onset mean-shift z (SEM-normalised) exceeds the "
        "n_nodes extreme-value null floor; magnitude scales with epsilon"
    ),
    # Threshold is NULL-CALIBRATED, not a single-node 2-sigma: the
    # observable is max over n_nodes of a SEM-normalised z, an
    # extreme-value statistic whose null E[max] ~ sqrt(2 ln n_nodes)
    # (~2.7 for n=24, tail to ~3.5). 5.0 sits safely above the empirical
    # null extreme over the registered seed battery; the planted
    # sustained shock drives the signal to ~30. Tightening this bar
    # to fit the null is FORBIDDEN — it is set ABOVE the null.
    pass_threshold_metric="worst_node_post_onset_mean_shift_z",
    pass_threshold_value=5.0,
    fail_threshold_metric="null_sibling_worst_node_z",
    fail_threshold_value=5.0,
    mapped_p5_substrate_candidates=(
        "funding_liquidity_rollover",
        "interbank_funding_topology",
    ),
    mapped_p2_window_class=(
        "liquidity_crisis",
        "repo_market_dysfunction",
    ),
    forbidden_claim_boundary=(
        "Synthetic only. Pass on PC1 does NOT prove real-world liquidity-crisis detection, "
        "does NOT prove bank-level validation, does NOT authorise any canonical run."
    ),
)


class PC1LiquidityShockInjectionFamily(PositiveControlFamily):
    """N-node funding-graph; planted shock at T_onset on a chosen node."""

    family_id = PC1_SPEC.family_id
    control_class = PC1_SPEC.control_class
    SPEC = PC1_SPEC

    def generate(self, seed: int, params: dict[str, Any]) -> ControlInstance:
        n_nodes = int(params.get("n_nodes", 24))
        t_steps = int(params.get("t_steps", 200))
        t_onset = int(params.get("t_onset", 120))
        epsilon = float(params.get("epsilon", 4.0))
        shocked_node = int(params.get("shocked_node", 0))
        noise_sigma = float(params.get("noise_sigma", 1.0))
        if not (0 <= shocked_node < n_nodes):
            msg = f"shocked_node {shocked_node} out of range [0, {n_nodes})"
            raise ValueError(msg)
        if not (0 <= t_onset < t_steps):
            msg = f"t_onset {t_onset} out of range [0, {t_steps})"
            raise ValueError(msg)
        rng_signal = np.random.default_rng(seed)
        rng_null = np.random.default_rng(seed)
        # Common base noise: independent samples drawn under identical RNG state.
        base_signal: NDArray[np.float64] = (
            rng_signal.standard_normal((t_steps, n_nodes)) * noise_sigma
        )
        base_null: NDArray[np.float64] = rng_null.standard_normal((t_steps, n_nodes)) * noise_sigma
        # Inject planted SUSTAINED liquidity shock on shocked_node from
        # t_onset onward. A funding-liquidity shock is a persistent
        # elevated-stress regime (slow ~1/long-tau relaxation), not a
        # fast transient — so the post-window mean shift ≈ epsilon and
        # the shock survives time-averaging in the detector.
        signal = base_signal.copy()
        post_n = t_steps - t_onset
        shock_profile = epsilon * (0.5 + 0.5 * np.exp(-np.arange(post_n) / float(max(1, post_n))))
        signal[t_onset:, shocked_node] += shock_profile
        gt = {
            "onset_time": t_onset,
            "effect_size": epsilon,
            "propagation_radius": 1,
            "shocked_node": shocked_node,
            "n_nodes": n_nodes,
            "t_steps": t_steps,
        }
        return ControlInstance(
            schema_version=SCHEMA_CONTROL_INSTANCE,
            id=f"{self.family_id}#seed={seed}",
            family=self.family_id,
            seed=seed,
            params=dict(params),
            signal_array=signal,
            null_sibling_array=base_null,
            ground_truth_metadata=gt,
        )

    def score(self, arr: NDArray[np.float64]) -> float:
        """Return the most-stressed node's post-onset mean-shift z.

        For each node we form the post-onset *mean* (averaged over the
        post window) minus the pre-onset mean, divided by the pre-onset
        per-node standard error of the mean. Averaging over the post
        window shrinks the noise variance by ~1/post_len so a transient
        single-sample extreme cannot masquerade as a persistent shock,
        while a planted persistent liquidity shock survives the average.
        The observable is ``max`` over nodes of that absolute z — a
        targeted "worst-stressed node" detector.
        """
        t_steps = arr.shape[0]
        split = int(0.6 * t_steps)
        pre = arr[:split, :]
        post = arr[split:, :]
        post_len = post.shape[0]
        pre_mu = pre.mean(axis=0)
        post_mu = post.mean(axis=0)
        pre_sd = pre.std(axis=0, ddof=1) + 1e-9  # bounds: numerical floor
        # Standard error of the post-window mean under the pre-window
        # noise scale (post mean of post_len iid samples).
        sem = pre_sd / np.sqrt(post_len)
        z = np.abs((post_mu - pre_mu) / sem)
        return float(z.max())


# ---------------------------------------------------------------------------
# PC2 — contagion cascade injection
# ---------------------------------------------------------------------------


PC2_SPEC: Final[ControlFamilySpec] = ControlFamilySpec(
    family_id="PC2_CONTAGION_CASCADE_INJECTION",
    control_class="contagion_cascade",
    ground_truth_fields=("onset_time", "cascade_extent", "cascade_speed", "defaulted_node"),
    negative_sibling_id="PC2_NEGATIVE_SIBLING",
    expected_observable_signature=(
        "≥k nodes hit cumulative impairment > threshold at lag ≤ L "
        "after T_onset; DebtRank-style cascade through exposure matrix W"
    ),
    pass_threshold_metric="cascade_extent_fraction",
    pass_threshold_value=0.30,
    fail_threshold_metric="null_sibling_cascade_extent",
    fail_threshold_value=0.30,
    mapped_p5_substrate_candidates=(
        "interbank_exposure_cascade",
        "debtrank_propagation",
    ),
    mapped_p2_window_class=(
        "contagion_event",
        "interbank_default_chain",
    ),
    forbidden_claim_boundary=(
        "Synthetic only. Pass on PC2 does NOT prove real-world contagion detection, "
        "does NOT prove DebtRank validation, does NOT authorise any canonical run."
    ),
)


class PC2ContagionCascadeInjectionFamily(PositiveControlFamily):
    """N-node exposure matrix; planted default at T_onset propagates through W."""

    family_id = PC2_SPEC.family_id
    control_class = PC2_SPEC.control_class
    SPEC = PC2_SPEC

    def generate(self, seed: int, params: dict[str, Any]) -> ControlInstance:
        n_nodes = int(params.get("n_nodes", 20))
        t_steps = int(params.get("t_steps", 150))
        t_onset = int(params.get("t_onset", 80))
        defaulted_node = int(params.get("defaulted_node", 0))
        cascade_decay = float(params.get("cascade_decay", 0.6))
        noise_sigma = float(params.get("noise_sigma", 0.5))
        rng = np.random.default_rng(seed)
        # Random sparse-ish positive exposure matrix W (row-normalised).
        w_raw = rng.uniform(0.0, 1.0, size=(n_nodes, n_nodes))
        np.fill_diagonal(w_raw, 0.0)
        row_sums = w_raw.sum(axis=1, keepdims=True) + 1e-9  # bounds: numerical floor
        w_norm = w_raw / row_sums
        # Build impairment series for signal: cascade from defaulted_node from t_onset.
        rng_signal = np.random.default_rng(seed)
        rng_null = np.random.default_rng(seed)
        signal = rng_signal.standard_normal((t_steps, n_nodes)) * noise_sigma
        null = rng_null.standard_normal((t_steps, n_nodes)) * noise_sigma
        impair = np.zeros(n_nodes, dtype=np.float64)
        impair[defaulted_node] = 1.0
        for tt in range(t_onset, t_steps):
            # Propagate cumulatively through W with decay.
            impair = impair + cascade_decay * (w_norm.T @ impair)
            impair = np.clip(
                impair, 0.0, 5.0
            )  # bounds: cascade-impairment ceiling, no physics INV here
            signal[tt, :] += impair
        gt = {
            "onset_time": t_onset,
            "cascade_extent": float((impair > 0.1).mean()),
            "cascade_speed": cascade_decay,
            "defaulted_node": defaulted_node,
            "n_nodes": n_nodes,
            "t_steps": t_steps,
        }
        return ControlInstance(
            schema_version=SCHEMA_CONTROL_INSTANCE,
            id=f"{self.family_id}#seed={seed}",
            family=self.family_id,
            seed=seed,
            params=dict(params),
            signal_array=signal,
            null_sibling_array=null,
            ground_truth_metadata=gt,
        )

    def score(self, arr: NDArray[np.float64]) -> float:
        """Return fraction of nodes hit by a persistent impairment shift.

        A node is "hit" iff its post-window MEAN shift exceeds a robust
        bar of 6 pre-window standard-errors-of-the-mean. Using the mean
        (not a cumulative sum) keeps the null bounded — a cumulative sum
        is a random walk whose variance grows with the horizon and would
        manufacture false positives. The cascade drives impaired nodes
        far past 6·SEM; pure-noise nodes stay near 0·SEM. The score is
        the fraction of impaired nodes (the cascade extent observable).
        """
        t_steps = arr.shape[0]
        split = int(0.55 * t_steps)
        pre = arr[:split, :]
        post = arr[split:, :]
        post_len = post.shape[0]
        pre_mu = pre.mean(axis=0)
        post_mu = post.mean(axis=0)
        pre_sd = pre.std(axis=0, ddof=1) + 1e-9  # bounds: numerical floor
        sem = pre_sd / np.sqrt(post_len)
        z = (post_mu - pre_mu) / sem
        return float((z > 6.0).mean())


# ---------------------------------------------------------------------------
# PC3 — balance-sheet impairment injection
# ---------------------------------------------------------------------------


PC3_SPEC: Final[ControlFamilySpec] = ControlFamilySpec(
    family_id="PC3_BALANCE_SHEET_IMPAIRMENT_INJECTION",
    control_class="balance_sheet_impairment",
    ground_truth_fields=("onset_time", "mark_down_magnitude", "impaired_set"),
    negative_sibling_id="PC3_NEGATIVE_SIBLING",
    expected_observable_signature=(
        "capital-distribution leftward shift on a defined subset of banks "
        "post T_onset; AFS/HTM unrealized-loss-like spike on impaired set"
    ),
    pass_threshold_metric="leftward_shift_mean_diff",
    pass_threshold_value=1.5,
    fail_threshold_metric="null_sibling_leftward_shift",
    fail_threshold_value=1.5,
    mapped_p5_substrate_candidates=(
        "balance_sheet_solvency_proxy",
        "capital_ratio_distribution_dynamics",
    ),
    mapped_p2_window_class=(
        "balance_sheet_impairment",
        "afs_htm_unrealized_loss",
    ),
    forbidden_claim_boundary=(
        "Synthetic only. Pass on PC3 does NOT prove real-world solvency-stress detection, "
        "does NOT prove regulatory capital-stress validation, does NOT authorise any canonical run."
    ),
)


class PC3BalanceSheetImpairmentInjectionFamily(PositiveControlFamily):
    """N-bank capital series; planted mark-down on a subset from T_onset."""

    family_id = PC3_SPEC.family_id
    control_class = PC3_SPEC.control_class
    SPEC = PC3_SPEC

    def generate(self, seed: int, params: dict[str, Any]) -> ControlInstance:
        n_banks = int(params.get("n_banks", 30))
        t_steps = int(params.get("t_steps", 180))
        t_onset = int(params.get("t_onset", 100))
        markdown_mag = float(params.get("markdown_mag", 3.0))
        impaired_frac = float(params.get("impaired_frac", 0.4))
        noise_sigma = float(params.get("noise_sigma", 1.0))
        rng = np.random.default_rng(seed)
        rng_signal = np.random.default_rng(seed)
        rng_null = np.random.default_rng(seed)
        # Capital-ratio-like series (mean 10, sd ~ noise_sigma).
        base_signal: NDArray[np.float64] = (
            10.0 + rng_signal.standard_normal((t_steps, n_banks)) * noise_sigma
        )
        base_null: NDArray[np.float64] = (
            10.0 + rng_null.standard_normal((t_steps, n_banks)) * noise_sigma
        )
        n_impaired = max(1, int(round(impaired_frac * n_banks)))
        impaired_set: NDArray[np.int64] = rng.choice(
            n_banks, size=n_impaired, replace=False
        ).astype(np.int64)
        # Apply markdown on impaired_set from t_onset.
        signal = base_signal.copy()
        signal[t_onset:, impaired_set] -= markdown_mag
        gt = {
            "onset_time": t_onset,
            "mark_down_magnitude": markdown_mag,
            "impaired_set": impaired_set.tolist(),
            "n_banks": n_banks,
            "t_steps": t_steps,
        }
        return ControlInstance(
            schema_version=SCHEMA_CONTROL_INSTANCE,
            id=f"{self.family_id}#seed={seed}",
            family=self.family_id,
            seed=seed,
            params=dict(params),
            signal_array=signal,
            null_sibling_array=base_null,
            ground_truth_metadata=gt,
        )

    def score(self, arr: NDArray[np.float64]) -> float:
        """Return the left-tail (worst-decile) capital-shift magnitude.

        A real solvency-stress detector reads the LEFT TAIL of the
        capital-ratio distribution, not the panel mean (which dilutes a
        concentrated impaired subset). We compute each bank's pre/post
        time-averaged level shift, then average the shift over the worst
        decile of banks (the ones whose capital fell the most). The
        planted markdown on the impaired set drives that decile down by
        ~mark_down_magnitude; the null sibling's worst decile is near
        zero (only noise).
        """
        t_steps = arr.shape[0]
        split = int(0.55 * t_steps)
        n_banks = arr.shape[1]
        per_bank_shift = arr[:split, :].mean(axis=0) - arr[split:, :].mean(axis=0)
        # Worst decile = banks with the largest leftward (positive) shift.
        decile = max(1, int(round(0.1 * n_banks)))
        worst = np.sort(per_bank_shift)[-decile:]
        return float(worst.mean())


# ---------------------------------------------------------------------------
# PC4 — market-wide volatility regime switch
# ---------------------------------------------------------------------------


PC4_SPEC: Final[ControlFamilySpec] = ControlFamilySpec(
    family_id="PC4_MARKET_WIDE_VOLATILITY_REGIME_SWITCH",
    control_class="volatility_regime_switch",
    ground_truth_fields=("switch_time", "vol_ratio", "pre_vol", "post_vol"),
    negative_sibling_id="PC4_NEGATIVE_SIBLING",
    expected_observable_signature=(
        "realised-vol breakpoint at T_switch; VIX-like proxy spike; "
        "GARCH-like variance jump from sigma_pre to sigma_post"
    ),
    pass_threshold_metric="post_pre_realised_vol_ratio",
    pass_threshold_value=2.0,
    fail_threshold_metric="null_sibling_vol_ratio",
    fail_threshold_value=2.0,
    mapped_p5_substrate_candidates=(
        "realised_volatility_regime_observer",
        "garch_breakpoint_detector",
    ),
    mapped_p2_window_class=(
        "market_wide_stress",
        "vix_spike_regime",
    ),
    forbidden_claim_boundary=(
        "Synthetic only. Pass on PC4 does NOT prove real-world volatility-regime detection, "
        "does NOT prove VIX-based crisis prediction, does NOT authorise any canonical run."
    ),
)


class PC4MarketWideVolatilityRegimeSwitchFamily(PositiveControlFamily):
    """Univariate returns series with planted variance regime switch."""

    family_id = PC4_SPEC.family_id
    control_class = PC4_SPEC.control_class
    SPEC = PC4_SPEC

    def generate(self, seed: int, params: dict[str, Any]) -> ControlInstance:
        t_steps = int(params.get("t_steps", 600))
        t_switch = int(params.get("t_switch", 300))
        sigma_pre = float(params.get("sigma_pre", 0.5))
        sigma_post = float(params.get("sigma_post", 2.0))
        rng_signal = np.random.default_rng(seed)
        rng_null = np.random.default_rng(seed)
        # Signal: low-vol then high-vol.
        signal = np.concatenate(
            [
                rng_signal.standard_normal(t_switch) * sigma_pre,
                rng_signal.standard_normal(t_steps - t_switch) * sigma_post,
            ]
        )
        # Null: stationary sigma_pre throughout.
        null = rng_null.standard_normal(t_steps) * sigma_pre
        gt = {
            "switch_time": t_switch,
            "vol_ratio": sigma_post / sigma_pre,
            "pre_vol": sigma_pre,
            "post_vol": sigma_post,
            "t_steps": t_steps,
        }
        return ControlInstance(
            schema_version=SCHEMA_CONTROL_INSTANCE,
            id=f"{self.family_id}#seed={seed}",
            family=self.family_id,
            seed=seed,
            params=dict(params),
            signal_array=signal,
            null_sibling_array=null,
            ground_truth_metadata=gt,
        )

    def score(self, arr: NDArray[np.float64]) -> float:
        """Return post/pre realised-volatility ratio."""
        t_steps = arr.shape[0]
        split = t_steps // 2
        pre_vol = arr[:split].std(ddof=1) + 1e-9  # bounds: numerical floor
        post_vol = arr[split:].std(ddof=1)
        return float(post_vol / pre_vol)


# ---------------------------------------------------------------------------
# PC5 — information-delay / vintage-leakage trap (INVERTED PASS RULE)
# ---------------------------------------------------------------------------


PC5_SPEC: Final[ControlFamilySpec] = ControlFamilySpec(
    family_id="PC5_INFORMATION_DELAY_VINTAGE_LEAKAGE_TRAP",
    control_class="information_delay_trap",
    ground_truth_fields=("leakage_delta", "expected_failure_mode"),
    negative_sibling_id="PC5_NEGATIVE_SIBLING",
    expected_observable_signature=(
        "INVERTED: pass iff pipeline DETECTS that a candidate detector uses "
        "future-release-date data and REJECTS that detector under the P3 "
        "point-in-time contract (vintage_release_date <= decision_date)"
    ),
    pass_threshold_metric="leakage_detection_flag",
    pass_threshold_value=1.0,
    fail_threshold_metric="null_sibling_leakage_flag",
    fail_threshold_value=1.0,
    mapped_p5_substrate_candidates=(
        "point_in_time_vintage_enforcer",
        "lookahead_violation_detector",
    ),
    mapped_p2_window_class=(
        "vintage_anti_leakage_baseline",
        "real_time_information_constraint",
    ),
    forbidden_claim_boundary=(
        "Synthetic only. PC5 PASS proves the P3 point-in-time discipline "
        "CATCHES a constructed-leakage detector; it does NOT prove real-world "
        "leakage absence, does NOT prove vintage-correctness of any live "
        "adapter, does NOT authorise any canonical run."
    ),
)


class PC5InfoDelayLeakageTrap(PositiveControlFamily):
    """Vintage time-series + lookahead-violation oracle.

    PASS criterion is INVERTED: a leakage-using detector MUST be flagged
    by the pipeline. ``score(signal_array)`` returns 1.0 IFF the
    detector callable (or the signal-array convention used here)
    references release dates > decision date.
    """

    family_id = PC5_SPEC.family_id
    control_class = PC5_SPEC.control_class
    SPEC = PC5_SPEC

    def generate(self, seed: int, params: dict[str, Any]) -> ControlInstance:
        t_steps = int(params.get("t_steps", 100))
        leakage_delta = int(params.get("leakage_delta", 5))
        rng_signal = np.random.default_rng(seed)
        rng_null = np.random.default_rng(seed)
        # Encode as a 3-column array: (observation_date, release_date,
        # value). For the leakage-using "signal" we tag release_date
        # = observation_date - leakage_delta to simulate using FUTURE
        # data (leakage); for the null sibling we tag release_date =
        # observation_date + leakage_delta (point-in-time correct).
        obs_dates = np.arange(t_steps, dtype=np.float64)
        # Signal: release dates LEAK by leakage_delta steps EARLY (peeks future).
        leaking_release = obs_dates - float(leakage_delta)
        signal_vals = rng_signal.standard_normal(t_steps)
        signal_array: NDArray[np.float64] = np.stack(
            [obs_dates, leaking_release, signal_vals], axis=1
        )
        # Null sibling: release dates are AFTER observation by leakage_delta steps
        # (i.e. point-in-time-correct vintage-aware).
        pit_release = obs_dates + float(leakage_delta)
        null_vals = rng_null.standard_normal(t_steps)
        null_array: NDArray[np.float64] = np.stack([obs_dates, pit_release, null_vals], axis=1)
        gt = {
            "leakage_delta": leakage_delta,
            "expected_failure_mode": "LOOKAHEAD_DETECTED",
            "t_steps": t_steps,
        }
        return ControlInstance(
            schema_version=SCHEMA_CONTROL_INSTANCE,
            id=f"{self.family_id}#seed={seed}",
            family=self.family_id,
            seed=seed,
            params=dict(params),
            signal_array=signal_array,
            null_sibling_array=null_array,
            ground_truth_metadata=gt,
        )

    def score(self, arr: NDArray[np.float64]) -> float:
        """Return PC5_PASS_TOKEN iff release_date < observation_date anywhere.

        Encodes the P3 vintage-discipline invariant
        (``release_date <= decision_date``) operating on the
        decision_date == observation_date contract used in PC5: any
        row with ``release_date < observation_date`` means the
        "detector" used data that did not yet exist — a lookahead
        violation. The pipeline asserts this returns 1.0 on
        ``signal_array`` and 0.0 on ``null_sibling_array``.
        """
        if arr.ndim != 2 or arr.shape[1] < 2:
            msg = f"PC5 score expects 2-col (obs_date, release_date) array, got shape {arr.shape}"
            raise ValueError(msg)
        obs_dates = arr[:, 0]
        release_dates = arr[:, 1]
        # Any release < observation = LOOKAHEAD_DETECTED.
        if bool(np.any(release_dates < obs_dates)):
            return PC5_PASS_TOKEN
        return PC5_FAIL_TOKEN


# ---------------------------------------------------------------------------
# PC6 — official-response event shock
# ---------------------------------------------------------------------------


PC6_SPEC: Final[ControlFamilySpec] = ControlFamilySpec(
    family_id="PC6_OFFICIAL_RESPONSE_EVENT_SHOCK",
    control_class="official_response_event_shock",
    ground_truth_fields=("intervention_time", "shift_magnitude", "pre_vol", "post_vol"),
    negative_sibling_id="PC6_NEGATIVE_SIBLING",
    expected_observable_signature=(
        "post-intervention mean/variance regime shift; e.g. volatility "
        "drops by factor f post-event; structural breakpoint at T_event"
    ),
    pass_threshold_metric="post_event_vol_drop_ratio",
    pass_threshold_value=1.5,
    fail_threshold_metric="null_sibling_vol_drop_ratio",
    fail_threshold_value=1.5,
    mapped_p5_substrate_candidates=(
        "policy_intervention_breakpoint_detector",
        "post_event_regime_shift_observer",
    ),
    mapped_p2_window_class=(
        "official_response",
        "policy_intervention",
    ),
    forbidden_claim_boundary=(
        "Synthetic only. Pass on PC6 does NOT prove real-world policy-response detection, "
        "does NOT prove intervention-effectiveness validation, does NOT authorise any canonical run."
    ),
)


class PC6OfficialResponseEventShockFamily(PositiveControlFamily):
    """Univariate series with planted post-intervention variance reduction."""

    family_id = PC6_SPEC.family_id
    control_class = PC6_SPEC.control_class
    SPEC = PC6_SPEC

    def generate(self, seed: int, params: dict[str, Any]) -> ControlInstance:
        t_steps = int(params.get("t_steps", 400))
        t_event = int(params.get("t_event", 200))
        sigma_pre = float(params.get("sigma_pre", 2.0))
        sigma_post = float(params.get("sigma_post", 0.5))
        rng_signal = np.random.default_rng(seed)
        rng_null = np.random.default_rng(seed)
        # Signal: high-vol pre-event then sharp reduction post-event.
        signal = np.concatenate(
            [
                rng_signal.standard_normal(t_event) * sigma_pre,
                rng_signal.standard_normal(t_steps - t_event) * sigma_post,
            ]
        )
        # Null: stationary sigma_pre throughout (no intervention effect).
        null = rng_null.standard_normal(t_steps) * sigma_pre
        gt = {
            "intervention_time": t_event,
            "shift_magnitude": sigma_pre / sigma_post,
            "pre_vol": sigma_pre,
            "post_vol": sigma_post,
            "t_steps": t_steps,
        }
        return ControlInstance(
            schema_version=SCHEMA_CONTROL_INSTANCE,
            id=f"{self.family_id}#seed={seed}",
            family=self.family_id,
            seed=seed,
            params=dict(params),
            signal_array=signal,
            null_sibling_array=null,
            ground_truth_metadata=gt,
        )

    def score(self, arr: NDArray[np.float64]) -> float:
        """Return pre/post-event realised-vol ratio (>1 means volatility dropped)."""
        t_steps = arr.shape[0]
        split = t_steps // 2
        pre_vol = arr[:split].std(ddof=1)
        post_vol = arr[split:].std(ddof=1) + 1e-9  # bounds: numerical floor
        return float(pre_vol / post_vol)


# ---------------------------------------------------------------------------
# Registry & accessors
# ---------------------------------------------------------------------------


ALL_FAMILIES: Final[tuple[type[PositiveControlFamily], ...]] = (
    PC1LiquidityShockInjectionFamily,
    PC2ContagionCascadeInjectionFamily,
    PC3BalanceSheetImpairmentInjectionFamily,
    PC4MarketWideVolatilityRegimeSwitchFamily,
    PC5InfoDelayLeakageTrap,
    PC6OfficialResponseEventShockFamily,
)

ALL_SPECS: Final[tuple[ControlFamilySpec, ...]] = (
    PC1_SPEC,
    PC2_SPEC,
    PC3_SPEC,
    PC4_SPEC,
    PC5_SPEC,
    PC6_SPEC,
)


def family_by_id(family_id: str) -> PositiveControlFamily:
    """Return an instance of the family matching *family_id*.

    Raises :class:`KeyError` if no family matches.
    """
    for cls in ALL_FAMILIES:
        if cls.family_id == family_id:
            return cls()
    msg = f"unknown family_id {family_id!r}; known: {[c.family_id for c in ALL_FAMILIES]}"
    raise KeyError(msg)


__all__ = [
    "ALL_FAMILIES",
    "ALL_SPECS",
    "ControlFamilySpec",
    "ControlInstance",
    "PC1LiquidityShockInjectionFamily",
    "PC1_SPEC",
    "PC2ContagionCascadeInjectionFamily",
    "PC2_SPEC",
    "PC3BalanceSheetImpairmentInjectionFamily",
    "PC3_SPEC",
    "PC4MarketWideVolatilityRegimeSwitchFamily",
    "PC4_SPEC",
    "PC5InfoDelayLeakageTrap",
    "PC5_SPEC",
    "PC6OfficialResponseEventShockFamily",
    "PC6_SPEC",
    "PC5_PASS_TOKEN",
    "PC5_FAIL_TOKEN",
    "PositiveControlFamily",
    "SCHEMA_CONTROL_INSTANCE",
    "family_by_id",
]

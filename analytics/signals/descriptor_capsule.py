# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Integrated descriptor replay capsule — one reproducible pipeline.

This module chains the descriptor-only methodology instruments into a single
deterministic capsule path::

    null_baseline → state_quantization → null_comparison
                  → descriptor_information_quality → descriptor_metadata

and emits one manifest carrying every stage's digest, the observed-vs-null
rank, the information-quality measures, and the claim-safe disclaimers. Given
the same config it reproduces a byte-identical manifest and ``manifest_digest``.

Every output is a STRUCTURAL descriptor of seeded inputs;
``claim_boundary="descriptor_only_not_predictor"``. Nothing here is a
significance, predictive, or financial claim. The capsule fails closed
(``ValueError``) on any malformed config or any instrument's own fail-closed
guard — it never emits an ambiguous manifest.

One-command entry point: :mod:`scripts.run_descriptor_capsule`.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import numpy as np

from analytics.signals.descriptor_information_quality import (
    as_metadata,
    compute_information_quality,
)
from analytics.signals.descriptor_metadata import build_descriptor_metadata
from analytics.signals.null_baseline import make_gaussian_null
from analytics.signals.null_comparison import compare_to_null
from analytics.signals.state_quantization import DEFAULT_INVALID_STATE, quantize_states

__all__ = ["CLAIM_BOUNDARY", "build_capsule"]

CLAIM_BOUNDARY = "descriptor_only_not_predictor"


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _require(config: Mapping[str, Any], key: str) -> Any:
    if key not in config:
        raise ValueError(f"descriptor-capsule: missing required config key {key!r}")
    return config[key]


def build_capsule(config: Mapping[str, Any]) -> dict[str, Any]:
    """Run the integrated descriptor pipeline and return its manifest.

    Required config keys: ``observed`` (list of floats), ``thresholds``
    (list of floats), ``labels`` (list of strings), ``null_seed`` (int).
    Optional: ``null_loc`` / ``null_scale`` (gaussian null params, default
    0.0 / 1.0), ``null_n`` (null length, default ``len(observed)``),
    ``band`` (null comparison band, default 0.05), ``source`` (provenance
    label, default ``"descriptor_capsule"``).
    """
    observed_raw = _require(config, "observed")
    thresholds = [float(t) for t in _require(config, "thresholds")]
    labels = [str(x) for x in _require(config, "labels")]
    null_seed = int(_require(config, "null_seed"))
    null_loc = float(config.get("null_loc", 0.0))
    null_scale = float(config.get("null_scale", 1.0))
    band = float(config.get("band", 0.05))
    source = str(config.get("source", "descriptor_capsule"))

    observed = np.asarray(observed_raw, dtype=np.float64)
    if observed.ndim != 1 or observed.size == 0:
        raise ValueError("descriptor-capsule: 'observed' must be a non-empty 1-D series")
    null_n = int(config.get("null_n", observed.size))
    if null_n < 1:
        raise ValueError("descriptor-capsule: 'null_n' must be >= 1")

    # Stage 1 — seeded null baseline.
    null_series, null_meta = make_gaussian_null(null_n, null_seed, loc=null_loc, scale=null_scale)

    # Stage 2 — quantize observed and null into the same label vocabulary.
    obs_q = quantize_states(observed.tolist(), thresholds=thresholds, labels=labels)
    null_q = quantize_states(null_series.tolist(), thresholds=thresholds, labels=labels)
    vocab = [*labels, DEFAULT_INVALID_STATE]

    # Stage 3 — locate the observed mean within the null ensemble. Non-finite
    # observations are already counted as invalid states in stage 2; the
    # located statistic summarises the FINITE observations so a partially
    # invalid series is described rather than rejected. An all-invalid series
    # has no statistic to locate and fails closed.
    finite_observed = observed[np.isfinite(observed)]
    if finite_observed.size == 0:
        raise ValueError("descriptor-capsule: 'observed' has no finite values to locate")
    observed_stat = float(np.mean(finite_observed))
    cmp = compare_to_null(observed_stat, null_series, band=band)

    # Stage 4 — information-quality of the observed states vs the null states.
    iq = compute_information_quality(
        list(obs_q.states),
        list(null_q.states),
        labels=vocab,
        observed_percentile=cmp.percentile,
    )

    # Stage 5 — claim-safe descriptor metadata.
    invalid_count = int(obs_q.metadata["invalid_count"])
    metadata = build_descriptor_metadata(
        method="descriptor_capsule",
        source=source,
        input_count=int(observed.size),
        invalid_count=invalid_count,
    )

    stages: dict[str, Any] = {
        "null_baseline": {
            "seed": int(null_seed),
            "n": int(null_n),
            "method": str(null_meta["method"]),
        },
        "quantization": {
            "observed_states": list(obs_q.states),
            "observed_digest": _digest(list(obs_q.states)),
            "null_digest": _digest(list(null_q.states)),
            "invalid_count": invalid_count,
        },
        "null_comparison": {
            "observed_stat": observed_stat,
            "rank": int(cmp.rank),
            "percentile": float(cmp.percentile),
            "n_null": int(cmp.n_null),
            "is_outside_null_band": bool(cmp.is_outside_null_band),
            "band": band,
        },
        "information_quality": dict(as_metadata(iq)),
    }

    config_hash = _digest(
        {
            "observed": observed.tolist(),
            "thresholds": thresholds,
            "labels": labels,
            "null_seed": null_seed,
            "null_loc": null_loc,
            "null_scale": null_scale,
            "null_n": null_n,
            "band": band,
            "source": source,
        }
    )

    body: dict[str, Any] = {
        "config_hash": config_hash,
        "stages": stages,
        "metadata": metadata,
        "claim_boundary": CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "not_financial_advice": True,
        "research_only": True,
    }
    manifest = dict(body)
    manifest["manifest_digest"] = _digest(body)
    return manifest

# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Deterministic public replay command surface for descriptor capsules.

This module is a *replay harness*, not a forecaster. Given a descriptor
configuration (an explicit fixed-threshold rule, or a seed-driven null
fixture), it re-emits a bounded descriptor result together with a replay
*manifest* that pins exactly how the result was produced:

* ``config_hash`` — a stable sha256 over the canonical, sorted config so
  the same config always hashes identically;
* ``input_count`` — the number of observations the descriptor consumed;
* ``method`` — the descriptor method that ran (``fixed_threshold`` or a
  null generator name);
* ``output_digest`` — a sha256 over the canonical descriptor output, so a
  replay can be checked byte-for-byte against an expected digest;
* ``manifest_digest`` — a sha256 over the manifest body itself, so the
  *whole* replay reduces to a single reproducible fingerprint;
* ``claim_boundary="descriptor_only_not_predictor"`` — the explicit
  boundary disclaimer shared with the underlying building blocks.

Determinism
-----------
Every code path is a pure function of its inputs. The only randomness is
the seed routed through :func:`numpy.random.default_rng` inside the
reused :mod:`analytics.signals.null_baseline` generators; there is no
module-level or process-global random state. The same config therefore
yields a byte-identical manifest, and ``manifest_digest`` is a complete
reproducibility fingerprint. A malformed config fails closed with a
:class:`ValueError` rather than emitting an ambiguous manifest.

Boundary
--------
The re-emitted states are structural descriptors of where each
observation falls relative to a declared rule, or seeded structureless
null fixtures. They carry no directional or financial meaning: the
contract asserts nothing about future prices, returns, or profitability,
and is research-only replay infrastructure.

Worked example
--------------
>>> manifest = replay({
...     "method": "fixed_threshold",
...     "values": [-2.0, 0.0, 0.4],
...     "thresholds": [-0.5, 0.5],
...     "labels": ["low", "neutral", "high"],
... })
>>> manifest["method"]
'fixed_threshold'
>>> manifest["input_count"]
3
>>> manifest["claim_boundary"]
'descriptor_only_not_predictor'
>>> replay({
...     "method": "fixed_threshold",
...     "values": [-2.0, 0.0, 0.4],
...     "thresholds": [-0.5, 0.5],
...     "labels": ["low", "neutral", "high"],
... })["manifest_digest"] == manifest["manifest_digest"]
True
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

# The two reused building blocks are pure leaf modules (stdlib + numpy only,
# no intra-package imports). They are loaded directly from their file
# location rather than via ``import analytics.signals.x``: the latter would
# execute the heavy ``analytics.signals.__init__`` aggregation surface
# (which transitively pulls backtest/execution chains). Loading the leaf
# files keeps this CLI self-contained, importable from any working
# directory, and free of any ``sys.path`` mutation.
_SIGNALS_DIR = Path(__file__).resolve().parents[1] / "analytics" / "signals"


def _load_leaf_module(name: str) -> ModuleType:
    """Load a pure leaf descriptor module by file path (no package init)."""
    spec = importlib.util.spec_from_file_location(
        f"_replay_capsule_{name}", _SIGNALS_DIR / f"{name}.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load building block {name!r} from {_SIGNALS_DIR}")
    module = importlib.util.module_from_spec(spec)
    # Register before execution so dataclass/typing machinery can resolve the
    # module's own qualified name via sys.modules during class construction.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_quantization = _load_leaf_module("state_quantization")
_null_baseline = _load_leaf_module("null_baseline")

quantize_states = _quantization.quantize_states
make_gaussian_null = _null_baseline.make_gaussian_null
make_constant_null = _null_baseline.make_constant_null

__all__ = [
    "CLAIM_BOUNDARY",
    "SUPPORTED_METHODS",
    "ReplayConfigError",
    "replay",
    "main",
]

#: The single declared boundary string echoed into every manifest.
CLAIM_BOUNDARY: str = "descriptor_only_not_predictor"

#: The descriptor methods this replay surface can re-emit.
SUPPORTED_METHODS: tuple[str, ...] = (
    "fixed_threshold",
    "gaussian_null",
    "constant_null",
)


class ReplayConfigError(ValueError):
    """A descriptor config was malformed; the replay fails closed."""


def _canonical_json(payload: Any) -> str:
    """Serialise ``payload`` deterministically (sorted keys, no spaces)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _digest(payload: Any) -> str:
    """Return the sha256 hex digest of the canonical encoding of ``payload``."""
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _config_hash(config: Mapping[str, Any]) -> str:
    """Stable provenance hash over the canonical config mapping."""
    return _digest(dict(config))


def _require(config: Mapping[str, Any], key: str) -> Any:
    """Return ``config[key]`` or fail closed with a precise message."""
    if key not in config:
        raise ReplayConfigError(f"replay config missing required key {key!r}")
    return config[key]


def _as_float_sequence(values: Any, key: str) -> list[float]:
    """Coerce ``values`` to a list of floats or fail closed."""
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ReplayConfigError(f"{key!r} must be a sequence of numbers, got {values!r}")
    try:
        return [float(v) for v in values]
    except (TypeError, ValueError) as exc:
        raise ReplayConfigError(f"{key!r} must contain only numbers: {exc}") from None


def _as_positive_int(value: Any, key: str) -> int:
    """Coerce ``value`` to a positive int or fail closed."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ReplayConfigError(f"{key!r} must be a positive int, got {value!r}")
    if value <= 0:
        raise ReplayConfigError(f"{key!r} must be > 0, got {value}")
    return value


def _replay_fixed_threshold(config: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Re-emit a fixed-threshold quantization descriptor result."""
    values = _as_float_sequence(_require(config, "values"), "values")
    thresholds = _as_float_sequence(_require(config, "thresholds"), "thresholds")
    labels_raw = _require(config, "labels")
    if isinstance(labels_raw, (str, bytes)) or not isinstance(labels_raw, Sequence):
        raise ReplayConfigError(f"'labels' must be a sequence of strings, got {labels_raw!r}")
    labels = [str(label) for label in labels_raw]
    try:
        result = quantize_states(values, thresholds=thresholds, labels=labels)
    except ValueError as exc:
        raise ReplayConfigError(f"fixed_threshold rule rejected: {exc}") from None
    states = list(result.states)
    output: dict[str, Any] = {
        "states": states,
        "input_count": int(result.metadata["input_count"]),
        "invalid_count": int(result.metadata["invalid_count"]),
        "state_counts": dict(result.metadata["state_counts"]),
    }
    return states, output


def _replay_gaussian_null(config: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Re-emit a seeded Gaussian null fixture as a descriptor result."""
    n = _as_positive_int(_require(config, "n"), "n")
    seed = _require(config, "seed")
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ReplayConfigError(f"'seed' must be a non-negative int, got {seed!r}")
    try:
        array, _meta = make_gaussian_null(n=n, seed=seed)
    except ValueError as exc:
        raise ReplayConfigError(f"gaussian_null request rejected: {exc}") from None
    series = [float(x) for x in array.tolist()]
    output = {"series": series, "input_count": len(series)}
    return [repr(x) for x in series], output


def _replay_constant_null(config: Mapping[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """Re-emit a degenerate constant null fixture as a descriptor result."""
    n = _as_positive_int(_require(config, "n"), "n")
    value = config.get("value", 0.0)
    try:
        array, _meta = make_constant_null(n=n, value=float(value))
    except (TypeError, ValueError) as exc:
        raise ReplayConfigError(f"constant_null request rejected: {exc}") from None
    series = [float(x) for x in array.tolist()]
    output = {"series": series, "input_count": len(series)}
    return [repr(x) for x in series], output


def replay(config: Mapping[str, Any]) -> dict[str, Any]:
    """Re-emit a bounded descriptor result and a reproducible replay manifest.

    Parameters
    ----------
    config:
        A descriptor configuration mapping. ``config['method']`` selects
        the descriptor (see :data:`SUPPORTED_METHODS`); the remaining keys
        are the method-specific inputs (``values``/``thresholds``/``labels``
        for ``fixed_threshold``; ``n``/``seed`` for ``gaussian_null``;
        ``n``/``value`` for ``constant_null``).

    Returns
    -------
    dict
        The replay manifest. It pins ``method``, ``config_hash``,
        ``input_count``, the descriptor ``output``, an ``output_digest``,
        a top-level ``manifest_digest`` fingerprint, and the boundary
        fields ``claim_boundary``, ``not_predictive_claim``,
        ``not_financial_advice``, ``research_only``.

    Raises
    ------
    ReplayConfigError
        If the config is not a mapping, omits a required key, names an
        unsupported method, or carries a malformed descriptor rule. The
        replay fails closed rather than emitting an ambiguous manifest.
    """
    if not isinstance(config, Mapping):
        raise ReplayConfigError(f"config must be a mapping, got {type(config).__name__}")
    method = _require(config, "method")
    if not isinstance(method, str) or method not in SUPPORTED_METHODS:
        raise ReplayConfigError(
            f"unsupported method {method!r}; expected one of {SUPPORTED_METHODS}"
        )

    if method == "fixed_threshold":
        _states, output = _replay_fixed_threshold(config)
    elif method == "gaussian_null":
        _states, output = _replay_gaussian_null(config)
    else:
        _states, output = _replay_constant_null(config)

    config_hash = _config_hash(config)
    output_digest = _digest(output)
    input_count = int(output["input_count"])

    manifest_body: dict[str, Any] = {
        "method": method,
        "config_hash": config_hash,
        "input_count": input_count,
        "output": output,
        "output_digest": output_digest,
        "claim_boundary": CLAIM_BOUNDARY,
        "not_predictive_claim": True,
        "not_financial_advice": True,
        "research_only": True,
    }
    manifest: dict[str, Any] = dict(manifest_body)
    manifest["manifest_digest"] = _digest(manifest_body)
    return manifest


def _load_config(raw: str) -> Mapping[str, Any]:
    """Parse a JSON config string into a mapping or fail closed."""
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ReplayConfigError(f"config is not valid JSON: {exc}") from None
    if not isinstance(parsed, Mapping):
        raise ReplayConfigError("config JSON must decode to an object/mapping")
    return parsed


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the replay command surface."""
    parser = argparse.ArgumentParser(
        prog="replay_descriptor_capsule",
        description=(
            "Deterministic descriptor replay surface: re-emit a bounded "
            "descriptor result and a reproducible replay manifest. "
            "Research replay infrastructure only; descriptor-only, not a "
            "predictor and not financial advice."
        ),
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--config-json",
        type=str,
        default=None,
        help="Descriptor config as an inline JSON object string.",
    )
    source.add_argument(
        "--config-file",
        type=str,
        default=None,
        help="Path to a JSON file holding the descriptor config object.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for the emitted manifest (default: 2).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point: parse a config, emit a manifest, return an exit code.

    Returns
    -------
    int
        ``0`` on a successful replay, ``2`` on a malformed config (the
        argparse fail-closed convention).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.config_file is not None:
            with open(args.config_file, encoding="utf-8") as handle:
                raw = handle.read()
        else:
            raw = args.config_json
        config = _load_config(raw)
        manifest = replay(config)
    except (ReplayConfigError, OSError) as exc:
        print(f"replay failed (fail-closed): {exc}", file=sys.stderr)
        return 2
    print(json.dumps(manifest, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

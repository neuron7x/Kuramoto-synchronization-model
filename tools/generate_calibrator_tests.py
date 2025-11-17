"""Utility for auto-generating calibrator unit tests with explanations.

This script inspects the neuro calibration module and renders a deterministic
test suite that documents the intent of each covered component.  The generated
tests live under ``tests/generated`` so they can be executed by the regular
pytest run while keeping the source of truth for the scaffolding in one place.

Usage
-----
::

    python tools/generate_calibrator_tests.py

The command will (re)create ``tests/generated/test_neuro_calibration_autogen.py``
with a header noting that the file is auto-generated.

The implementation favours clarity over clever meta-programming so that new
components can easily be added by extending the ``COMPONENTS`` mapping below.
Each component describes the explanation text surfaced in the docstring of the
resulting test and provides a small template for the assertions that capture
the behavioural contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
GENERATED_TEST_PATH = ROOT / "tests" / "generated" / "test_neuro_calibration_autogen.py"


@dataclass(frozen=True)
class Component:
    """Definition of a calibrator component and its accompanying test."""

    name: str
    explanation: str
    test_body: str


COMPONENTS: tuple[Component, ...] = (
    Component(
        name="CalibConfig",
        explanation=(
            "Validates that the calibration configuration advertises the "
            "expected default search space for AdaptiveMarketMind parameters."
        ),
        test_body=dedent(
            """
            cfg = CalibConfig()
            assert cfg.iters == 200
            assert cfg.seed == 7
            assert cfg.ema_span == (8, 96)
            assert cfg.vol_lambda == (0.86, 0.98)
            assert cfg.alpha == (0.2, 5.0)
            assert cfg.beta == (0.1, 2.0)
            assert cfg.lambda_sync == (0.2, 1.2)
            assert cfg.eta_ricci == (0.1, 1.0)
            assert cfg.rho == (0.01, 0.12)
            """
        ).strip(),
    ),
    Component(
        name="rand_helper",
        explanation=(
            "Ensures the internal ``_rand`` helper respects the provided "
            "boundaries for both integer and floating-point draws."
        ),
        test_body=dedent(
            """
            rng = np.random.default_rng(123)
            assert _rand(rng, (1, 3), is_int=True) in {1, 2, 3}
            for _ in range(10):
                draw = _rand(rng, (0.5, 0.6))
                assert 0.5 <= draw <= 0.6
            """
        ).strip(),
    ),
    Component(
        name="evaluate_trace",
        explanation=(
            "Covers ``_evaluate_trace`` behaviour for degenerate inputs and "
            "verifies that a well-formed trace yields the documented metrics."
        ),
        test_body=dedent(
            """
            short = _evaluate_trace(np.array([0.1], dtype=Float), np.array([1.0], dtype=Float), np.array([1.0], dtype=Float))
            assert short is None

            S = np.array([0.2, 0.6, -0.4], dtype=Float)
            P = np.array([0.9, 1.1, 1.0], dtype=Float)
            PE = np.array([0.05, 0.15, 0.10], dtype=Float)

            result = _evaluate_trace(S, P, PE)
            assert result is not None
            score, metrics = result
            assert set(metrics) == {"corr", "mean_precision", "precision_std", "pulse_std", "pe_std", "score"}
            assert np.isclose(score, metrics["score"])  # score mirrors metrics entry
            assert metrics["mean_precision"] == np.mean(np.clip(P, 0.01, 100.0))
            assert metrics["pulse_std"] == np.std(S)
            assert metrics["pe_std"] == np.std(PE)
            """
        ).strip(),
    ),
    Component(
        name="calibrate_random",
        explanation=(
            "Exercises ``calibrate_random`` end-to-end to assert bounds, "
            "default fallbacks, and the integrity of the returned diagnostics."
        ),
        test_body=dedent(
            """
            cfg = CalibConfig(iters=5, seed=2, ema_span=(4, 5), vol_lambda=(0.8, 0.81), alpha=(0.3, 0.31), beta=(0.2, 0.21), lambda_sync=(0.5, 0.51), eta_ricci=(0.1, 0.11), rho=(0.02, 0.021))
            rng = np.random.default_rng(99)
            x = rng.normal(0.0, 0.01, 32).astype(Float)
            R = rng.uniform(0.1, 0.9, 32).astype(Float)
            kappa = rng.normal(0.0, 0.2, 32).astype(Float)

            result = calibrate_random(x, R, kappa, cfg, return_details=True)
            assert isinstance(result.config, AMMConfig)
            assert cfg.ema_span[0] <= result.config.ema_span <= cfg.ema_span[1]
            assert cfg.vol_lambda[0] <= result.config.vol_lambda <= cfg.vol_lambda[1]
            assert cfg.alpha[0] <= result.config.alpha <= cfg.alpha[1]
            assert cfg.beta[0] <= result.config.beta <= cfg.beta[1]
            assert cfg.lambda_sync[0] <= result.config.lambda_sync <= cfg.lambda_sync[1]
            assert cfg.eta_ricci[0] <= result.config.eta_ricci <= cfg.eta_ricci[1]
            assert cfg.rho[0] <= result.config.rho <= cfg.rho[1]
            assert np.isfinite(result.score) or np.isnan(result.score)
            if np.isfinite(result.score):
                assert np.isclose(result.score, result.metrics["corr"] * result.metrics["mean_precision"])

            empty_result = calibrate_random(x, R, kappa, CalibConfig(iters=0, seed=cfg.seed), return_details=True)
            assert isinstance(empty_result.config, AMMConfig)
            assert np.isnan(empty_result.score)
            assert empty_result.metrics == {}
            """
        ).strip(),
    ),
)


FILE_HEADER = dedent(
    '''
    """Auto-generated tests for ``core.neuro.calibration``.

    This module is generated by ``tools/generate_calibrator_tests.py``.  Manual
    edits will be lost the next time the generator runs.  Each test documents the
    reasoning behind a specific calibrator component to make the behavioural
    contract explicit for future maintainers.
    """

    from __future__ import annotations

    import numpy as np

    from core.neuro.calibration import (
        AMMConfig,
        CalibConfig,
        Float,
        _evaluate_trace,
        _rand,
        calibrate_random,
    )
    '''
)


def _build_test_function(component: Component) -> str:
    """Render a pytest-compatible function for ``component``."""

    test_name = f"test_{component.name}_autogenerated"
    docstring = component.explanation.replace('"', '\\"')
    body = dedent(component.test_body)
    indented_body = "\n".join(
        "    " + line if line else "" for line in body.splitlines()
    )
    function_source = (
        f"\n\n\n"
        f"def {test_name}() -> None:\n"
        f'    """{docstring}"""\n'
        f"{indented_body}\n"
    )
    return function_source.rstrip()


def render_module() -> str:
    """Compose the full module content."""

    parts = [FILE_HEADER.strip()]
    for component in COMPONENTS:
        parts.append(_build_test_function(component))
    return "\n".join(parts) + "\n"


def main() -> None:
    """Materialise the generated test module on disk."""

    GENERATED_TEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    GENERATED_TEST_PATH.write_text(render_module(), encoding="utf-8")


if __name__ == "__main__":
    main()

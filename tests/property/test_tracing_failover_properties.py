"""Property-based tests for tracing failover resilience."""

from __future__ import annotations

import importlib
from contextlib import contextmanager
from typing import Any, Mapping

import pytest
from pytest import MonkeyPatch

hypothesis = pytest.importorskip(
    "hypothesis", reason="hypothesis is required for property-based tracing tests"
)
st = hypothesis.strategies
HealthCheck = hypothesis.HealthCheck
given = hypothesis.given
settings = hypothesis.settings

from tests.unit.observability.test_tracing import (  # noqa: E402
    _install_stub_opentelemetry,
)

FAILOVER_KEYS = (
    "pipeline.failover",
    "resilience.failover",
    "routing.failover",
    "routing.failover_active",
    "failover.active",
)

TRUTHY_VALUES = [True, "true", "TRUE", "1", "yes", "YES", "on", "active", 1]
FALSY_VALUES = [False, "false", "0", "no", "", 0, None]

IDENTIFIER_CHARS = st.characters(min_codepoint=97, max_codepoint=122)


@contextmanager
def _load_tracing():
    monkeypatch = MonkeyPatch()
    _install_stub_opentelemetry(monkeypatch)
    tracing = importlib.import_module("observability.tracing")
    tracing = importlib.reload(tracing)
    try:
        yield tracing
    finally:
        monkeypatch.undo()


@settings(
    max_examples=1200,
    deadline=None,
    suppress_health_check=(HealthCheck.too_slow,),
)
@given(
    stage_base=st.text(IDENTIFIER_CHARS, min_size=3, max_size=12),
    triggers=st.lists(
        st.sampled_from(("attribute", "failover_attr", "pattern")),
        min_size=1,
        max_size=3,
        unique=True,
    ),
    attribute_flag=st.sampled_from(
        (
            "pipeline.hot_path",
            "pipeline.failover",
            "routing.hot_path",
            "resilience.hot_path",
        )
    ),
    truthy_pair=st.tuples(
        st.sampled_from(TRUTHY_VALUES),
        st.sampled_from(FALSY_VALUES),
    ).filter(lambda pair: pair[0] != pair[1]),
    failover_pair=st.tuples(
        st.sampled_from(TRUTHY_VALUES),
        st.sampled_from(FALSY_VALUES),
    ).filter(lambda pair: pair[0] != pair[1]),
    failover_key=st.sampled_from(FAILOVER_KEYS),
    hot_ratio=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    default_ratio=st.floats(
        min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
    ),
    use_matching_pattern=st.booleans(),
    additional_attrs=st.dictionaries(
        keys=st.text(IDENTIFIER_CHARS, min_size=3, max_size=16),
        values=st.one_of(
            st.sampled_from(TRUTHY_VALUES + FALSY_VALUES),
            st.integers(min_value=-1, max_value=2),
        ),
        max_size=3,
    ),
)
def test_selective_sampler_prioritises_failover_signals(
    stage_base: str,
    triggers: list[str],
    attribute_flag: str,
    truthy_pair: tuple[Any, Any],
    failover_pair: tuple[Any, Any],
    failover_key: str,
    hot_ratio: float,
    default_ratio: float,
    use_matching_pattern: bool,
    additional_attrs: Mapping[str, Any],
) -> None:
    with _load_tracing() as tracing:
        _exercise_sampler(
            tracing,
            stage_base,
            triggers,
            attribute_flag,
            truthy_pair,
            failover_pair,
            failover_key,
            hot_ratio,
            default_ratio,
            use_matching_pattern,
            additional_attrs,
        )


def _exercise_sampler(
    tracing: Any,
    stage_base: str,
    triggers: list[str],
    attribute_flag: str,
    truthy_pair: tuple[Any, Any],
    failover_pair: tuple[Any, Any],
    failover_key: str,
    hot_ratio: float,
    default_ratio: float,
    use_matching_pattern: bool,
    additional_attrs: Mapping[str, Any],
) -> None:

    truthy_value, falsy_value = truthy_pair
    failover_truthy, failover_falsy = failover_pair

    stage_name = f"{stage_base}.pipeline"
    non_failover_stage = f"{stage_base}.primary"

    patterns: list[str] = []
    if "pattern" in triggers:
        stage_name = f"{stage_name}.failover"
        if use_matching_pattern:
            patterns.append(f"{stage_base}*.failover*")
        else:
            patterns.append(f"{stage_base}.shadow*")

    attributes: dict[str, Any] = dict(additional_attrs)

    if "attribute" in triggers:
        attributes[attribute_flag] = truthy_value
    else:
        attributes[attribute_flag] = falsy_value

    if "failover_attr" in triggers:
        attributes[failover_key] = failover_truthy
    elif not ("attribute" in triggers and failover_key == attribute_flag):
        attributes[failover_key] = failover_falsy

    sampler = tracing.SelectiveSampler(
        hot_path_globs=tuple(patterns),
        attribute_flag=attribute_flag,
        default_ratio=default_ratio,
        hot_ratio=hot_ratio,
    )

    sampler._hot_sampler.calls.clear()
    sampler._default_sampler.calls.clear()

    sampler.should_sample(None, 1, stage_name, None, attributes, None)

    assert len(sampler._hot_sampler.calls) == 1
    assert len(sampler._default_sampler.calls) == 0

    non_failover_attributes = dict(attributes)
    if "attribute" in triggers:
        non_failover_attributes[attribute_flag] = falsy_value
    if "failover_attr" in triggers:
        non_failover_attributes[failover_key] = failover_falsy

    sampler._hot_sampler.calls.clear()
    sampler._default_sampler.calls.clear()

    sampler.should_sample(
        None, 2, non_failover_stage, None, non_failover_attributes, None
    )

    assert len(sampler._hot_sampler.calls) == 0
    assert len(sampler._default_sampler.calls) == 1

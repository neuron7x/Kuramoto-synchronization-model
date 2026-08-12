# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""G1 — scope_match returns False on N=8000 with cert for N∈(28,35)."""

from __future__ import annotations

import pytest

from instrument_validation.scope import (
    InstrumentScope,
    country_aggregate_default_scope,
    make_instrument_id,
    scope_match,
    serialise_scope,
)


def test_scope_match_rejects_out_of_n_range() -> None:
    scope = country_aggregate_default_scope("foo", "1.0.0")
    assert scope_match(scope, n=31, substrate=scope.valid_for_substrate, density=0.15)
    # G1: N=8000 must be rejected
    assert not scope_match(scope, n=8000, substrate=scope.valid_for_substrate, density=0.15)
    assert not scope_match(scope, n=15, substrate=scope.valid_for_substrate, density=0.15)


def test_scope_match_rejects_wrong_substrate() -> None:
    scope = country_aggregate_default_scope()
    assert not scope_match(scope, n=31, substrate="bank_level", density=0.15)


def test_scope_match_rejects_density_out_of_range() -> None:
    scope = country_aggregate_default_scope()
    assert not scope_match(scope, n=31, substrate=scope.valid_for_substrate, density=0.95)


def test_scope_match_rejects_low_obs_per_corr() -> None:
    scope = country_aggregate_default_scope()
    assert not scope_match(
        scope,
        n=31,
        substrate=scope.valid_for_substrate,
        density=0.15,
        obs_per_corr=3,
    )


def test_country_aggregate_scope_must_declare_bank_level_invalid() -> None:
    with pytest.raises(ValueError, match="bank_level"):
        InstrumentScope(
            instrument_id="x",
            valid_for_substrate="undirected_weighted_country_aggregate",
            valid_for_n_range=(28, 35),
            valid_for_density_range=(0.05, 0.40),
            valid_for_obs_per_corr=8,
            invalid_for=(),
        )


def test_make_instrument_id_is_deterministic() -> None:
    a = make_instrument_id("source A", "1.0.0")
    b = make_instrument_id("source A", "1.0.0")
    c = make_instrument_id("source B", "1.0.0")
    assert a == b
    assert a != c
    assert len(a) == 64


def test_serialise_scope_shape() -> None:
    scope = country_aggregate_default_scope()
    payload = serialise_scope(scope)
    for key in (
        "instrument_id",
        "valid_for_substrate",
        "valid_for_n_range",
        "valid_for_density_range",
        "valid_for_obs_per_corr",
        "invalid_for",
    ):
        assert key in payload


def test_scope_match_rejects_non_int_n() -> None:
    """Iter-4 audit fix — booleans subclass int, float silently coerced."""
    from typing import Any, cast

    scope = country_aggregate_default_scope()
    # Float n masquerading as int
    assert not scope_match(
        scope,
        n=cast(Any, 31.0),
        substrate=scope.valid_for_substrate,
        density=0.15,
    )
    # Boolean n (True == 1, was silently treated as n=1)
    assert not scope_match(
        scope,
        n=cast(Any, True),
        substrate=scope.valid_for_substrate,
        density=0.15,
    )


def test_scope_match_rejects_bool_substrate() -> None:
    from typing import Any, cast

    scope = country_aggregate_default_scope()
    assert not scope_match(
        scope,
        n=31,
        substrate=cast(Any, False),
        density=0.15,
    )

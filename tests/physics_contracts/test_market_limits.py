# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Witnesses for ``physics_contracts/market_limits.yaml``.

These tests prove the market approximation-limits contract stays well-formed,
fail-closed, and aligned with the canonical claim-tier vocabulary in
``FORBIDDEN_CLAIMS.md`` and the four pre-registered nulls in the Ricci
microstructure preregistration guard. Each ``witness_required`` field in the
contract points at a function here; the cross-check test proves none dangles.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.research.market_limits import (
    KNOWN_FALSIFIERS,
    MarketLimit,
    MarketLimitsContract,
    load_contract,
)

# Canonical claim-tier ceilings, ordered weakest → strongest. A limit's
# `max_claim_tier_violated` must be one of these (mirror of FORBIDDEN_CLAIMS.md).
CANONICAL_TIERS: frozenset[str] = frozenset(
    {
        "Not Measured",
        "Instrumented",
        "Measured-Single",
        "Measured-Multi",
        "Blocked",
        "Not Deployable",
    }
)


@pytest.fixture(scope="module")
def contract() -> MarketLimitsContract:
    return load_contract()


def test_contract_loads_and_is_nonempty(contract: MarketLimitsContract) -> None:
    assert contract.version >= 1
    assert contract.limits, "market-limits contract must declare at least one limit"
    ids = [limit.limit_id for limit in contract.limits]
    assert len(ids) == len(set(ids)), f"duplicate limit_id: {ids}"


def test_claim_tier_vocabulary_matches_forbidden_claims(
    contract: MarketLimitsContract,
) -> None:
    assert set(contract.claim_tiers) == CANONICAL_TIERS


@pytest.mark.parametrize(
    "field",
    ["valid_when", "invalid_when", "forbidden_claims"],
)
def test_list_fields_are_nonempty(contract: MarketLimitsContract, field: str) -> None:
    for limit in contract.limits:
        values = getattr(limit, field)
        assert values, f"{limit.limit_id}.{field} must be non-empty"
        assert all(v.strip() for v in values), f"{limit.limit_id}.{field} has blank entry"


def test_every_falsifier_is_a_known_null(contract: MarketLimitsContract) -> None:
    for limit in contract.limits:
        assert (
            limit.falsifier_required in KNOWN_FALSIFIERS
        ), f"{limit.limit_id} names unknown falsifier {limit.falsifier_required!r}"


def test_promotion_relevant_limits_have_executable_falsifier(
    contract: MarketLimitsContract,
) -> None:
    """A named falsifier is not a falsifier unless it can be run.

    Every promotion-relevant limit must declare a runnable ``falsifier_command``
    or a ``falsifier_artifact_path`` for its required falsifier; otherwise a
    real-data claim could be advanced behind a falsifier that nobody can locate.
    """
    promo = [limit for limit in contract.limits if limit.promotion_relevant]
    assert promo, "expected at least one promotion-relevant market limit"
    for limit in promo:
        assert limit.has_executable_falsifier, (
            f"{limit.limit_id} is promotion_relevant but has neither "
            f"falsifier_command nor falsifier_artifact_path for required "
            f"falsifier {limit.falsifier_required!r}"
        )
        # If a command names a pytest node, it must point at a file that exists
        # under the repo (locatability of the executable falsifier).
        cmd = limit.falsifier_command
        if cmd and "::" in cmd:
            node = cmd.split()[-2] if cmd.split()[-1] == "-q" else cmd.split()[-1]
            test_path = node.split("::", 1)[0]
            repo_root = Path(__file__).resolve().parents[2]
            assert (repo_root / test_path).is_file(), (
                f"{limit.limit_id} falsifier_command references missing test file {test_path!r}"
            )


def test_every_max_tier_is_canonical(contract: MarketLimitsContract) -> None:
    for limit in contract.limits:
        assert (
            limit.max_claim_tier_violated in CANONICAL_TIERS
        ), f"{limit.limit_id} ceiling {limit.max_claim_tier_violated!r} not canonical"


def test_no_witness_reference_dangles(contract: MarketLimitsContract) -> None:
    """Each ``witness_required`` must point at a function defined in this module."""
    module_funcs = {name for name in globals() if name.startswith("test_")}
    for limit in contract.limits:
        ref = limit.witness_required
        assert "::" in ref, f"{limit.limit_id}.witness_required must be path::func, got {ref!r}"
        path, func = ref.split("::", 1)
        assert path == "tests/physics_contracts/test_market_limits.py", (
            f"{limit.limit_id} witness path {path!r} is not this module"
        )
        assert func in module_funcs, f"{limit.limit_id} witness {func!r} is not defined here"


# ── Named witnesses referenced by the contract's `witness_required` fields ──
# Each asserts the specific fail-closed property the limit promises.


def _limit(contract: MarketLimitsContract, limit_id: str) -> MarketLimit:
    found = contract.by_id(limit_id)
    assert found is not None, f"missing limit {limit_id!r}"
    return found


def test_no_conservation_claim(contract: MarketLimitsContract) -> None:
    limit = _limit(contract, "market.non_conservative")
    assert limit.max_claim_tier_violated == "Instrumented"
    assert any("conserv" in c.lower() for c in limit.forbidden_claims)


def test_window_is_declared(contract: MarketLimitsContract) -> None:
    limit = _limit(contract, "market.non_stationary")
    assert limit.falsifier_required == "lag_sweep_no_future_data"


def test_no_fixed_coupling_claim(contract: MarketLimitsContract) -> None:
    limit = _limit(contract, "market.agent_driven")
    assert any("coupling" in c.lower() for c in limit.forbidden_claims)


def test_degenerate_book_fails_closed(contract: MarketLimitsContract) -> None:
    limit = _limit(contract, "market.liquidity_discontinuous")
    # A degenerate book must not merely degrade — it must block promotion.
    assert limit.max_claim_tier_violated == "Blocked"


def test_shock_calm_stratified(contract: MarketLimitsContract) -> None:
    limit = _limit(contract, "market.regime_shock")
    assert limit.falsifier_required == "multi_session_replay"
    # Fail-closed: an invalid shock-regime interpretation must not retain a
    # real-data measured tier — it caps at Instrumented, never Measured-*.
    assert limit.max_claim_tier_violated == "Instrumented"
    assert "Measured" not in limit.max_claim_tier_violated


def test_open_system_acknowledged(contract: MarketLimitsContract) -> None:
    limit = _limit(contract, "market.order_flow_open_system")
    assert any("closed" in c.lower() for c in limit.forbidden_claims)


def test_no_causal_from_correlation(contract: MarketLimitsContract) -> None:
    limit = _limit(contract, "market.correlation_not_causal")
    assert any("causal" in c.lower() for c in limit.forbidden_claims)


def test_descriptor_needs_falsifier(contract: MarketLimitsContract) -> None:
    limit = _limit(contract, "market.descriptor_not_predictor")
    # The descriptor→predictor jump must be gated by a multi-session falsifier.
    assert limit.falsifier_required == "multi_session_replay"
    assert limit.max_claim_tier_violated == "Instrumented"


# ── Negative fixture: contract load must fail closed when a promotion-relevant
#    limit declares no executable falsifier (neither command nor artifact). ──

_MINIMAL_LIMIT_LINES: tuple[str, ...] = (
    "    valid_when:",
    '      - "v"',
    "    invalid_when:",
    '      - "iw"',
    '    witness_required: "tests/physics_contracts/test_market_limits.py::test_no_conservation_claim"',
    '    falsifier_required: "permutation_null"',
    "    forbidden_claims:",
    '      - "fc"',
    "    max_claim_tier_violated: Instrumented",
)


def _write_contract(tmp_path: Path, *, promotion_relevant: bool, executable: bool) -> Path:
    lines: list[str] = [
        "version: 1",
        "claim_tiers:",
        '  - "Instrumented"',
        "limits:",
        '  - limit_id: market.fixture',
        '    mathematical_object: "obj"',
        '    market_interpretation: "interp"',
        f"    promotion_relevant: {str(promotion_relevant).lower()}",
    ]
    if executable:
        lines.append(
            '    falsifier_command: "python -m pytest '
            'tests/physics_contracts/test_market_limits.py::test_no_conservation_claim -q"'
        )
    lines.extend(_MINIMAL_LIMIT_LINES)
    path = tmp_path / "market_limits_fixture.yaml"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_promotion_relevant_without_executable_falsifier_fails_load(tmp_path: Path) -> None:
    """A promotion-relevant limit with no command/artifact must fail closed."""
    bad = _write_contract(tmp_path, promotion_relevant=True, executable=False)
    with pytest.raises(ValueError, match="not executable/locatable"):
        load_contract(bad)


def test_promotion_relevant_with_executable_falsifier_loads(tmp_path: Path) -> None:
    """The same shape with an executable falsifier loads cleanly."""
    ok = _write_contract(tmp_path, promotion_relevant=True, executable=True)
    loaded = load_contract(ok)
    limit = loaded.by_id("market.fixture")
    assert limit is not None
    assert limit.promotion_relevant
    assert limit.has_executable_falsifier


def test_non_promotion_limit_without_falsifier_command_loads(tmp_path: Path) -> None:
    """Non-promotion limits keep prior behavior: no executable falsifier needed."""
    ok = _write_contract(tmp_path, promotion_relevant=False, executable=False)
    loaded = load_contract(ok)
    limit = loaded.by_id("market.fixture")
    assert limit is not None
    assert not limit.promotion_relevant
    assert not limit.has_executable_falsifier

# SPDX-License-Identifier: MIT
"""Property controls for the offline execution-forensics evidence boundary.

Each property is checked against an oracle that shares no code with the module:
``fractions.Fraction`` for exact arithmetic, a row permutation for order
independence, the CSV writer for the round trip, and the float-based
``analytics.execution_quality.implementation_shortfall`` for sign parity.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime, timedelta, timezone
from fractions import Fraction

import pytest

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
except ImportError:  # pragma: no cover - exercised only without the dev lock
    pytest.skip("hypothesis not installed", allow_module_level=True)

from tools.execution_forensics import (
    HEADERS,
    EvidenceInputError,
    analyze_bytes,
    parse_fills,
    report_digest,
    verify_report,
)

_T0 = datetime(2026, 10, 20, 10, 0, 0, tzinfo=timezone.utc)


def _decimal_text(draw: st.DrawFn, *, positive: bool, max_int: int = 10**9) -> str:
    integer = draw(st.integers(min_value=1 if positive else 0, max_value=max_int))
    scale = draw(st.integers(min_value=0, max_value=8))
    if scale == 0:
        return str(integer)
    fraction = draw(st.integers(min_value=0, max_value=10**scale - 1))
    text = f"{integer}.{fraction:0{scale}d}"
    return text if positive or Fraction(text) >= 0 else "0"


@st.composite
def fill_rows(draw: st.DrawFn, *, with_arrival: bool | None = None) -> dict[str, str]:
    side = draw(st.sampled_from(["BUY", "SELL"]))
    quantity = _decimal_text(draw, positive=True, max_int=10**6)
    price = _decimal_text(draw, positive=True)
    executed_offset = draw(st.integers(min_value=1, max_value=3600))
    executed = _T0 + timedelta(seconds=executed_offset)
    row = {
        "venue": "binance",
        "symbol": "BTCUSDT",
        "quote_asset": "USDT",
        "trade_id": "",  # assigned by the caller to keep identities unique
        "order_id": "O1",
        "executed_at_utc": executed.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "side": side,
        "quantity": quantity,
        "price": price,
        "fee_amount": "",
        "fee_asset": "",
        "fee_quote_value": "",
        "fee_conversion_source": "",
        "arrival_price": "",
        "arrival_at_utc": "",
        "arrival_source": "",
    }
    fee_kind = draw(st.sampled_from(["none", "quote", "cross_sourced", "cross_unknown"]))
    if fee_kind != "none":
        row["fee_amount"] = _decimal_text(draw, positive=False, max_int=10**4)
    if fee_kind == "quote":
        row["fee_asset"] = "USDT"
    elif fee_kind == "cross_sourced":
        row["fee_asset"] = "BNB"
        row["fee_quote_value"] = _decimal_text(draw, positive=False, max_int=10**4)
        row["fee_conversion_source"] = "declared_valuation"
    elif fee_kind == "cross_unknown":
        row["fee_asset"] = "BNB"
    arrival = draw(st.booleans()) if with_arrival is None else with_arrival
    if arrival:
        row["arrival_price"] = _decimal_text(draw, positive=True)
        row["arrival_at_utc"] = _T0.strftime("%Y-%m-%dT%H:%M:%SZ")
        row["arrival_source"] = "submission_snapshot"
        row["order_id"] = draw(st.sampled_from(["O1", "O2", "O3"]))
    return row


def _csv_bytes(rows: list[dict[str, str]]) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=HEADERS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _identify(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Give every row a unique trade id and one arrival benchmark per order."""
    arrivals: dict[str, tuple[str, str, str]] = {}
    out = []
    for index, row in enumerate(rows):
        row = dict(row, trade_id=f"T{index}")
        if row["arrival_price"]:
            key = row["order_id"]
            if key in arrivals:
                row["arrival_price"], row["arrival_at_utc"], row["arrival_source"] = arrivals[key]
            else:
                arrivals[key] = (row["arrival_price"], row["arrival_at_utc"], row["arrival_source"])
        out.append(row)
    return out


def _fraction_or_none(text: str | None) -> Fraction | None:
    return None if text is None else Fraction(text)


@given(st.lists(fill_rows(), min_size=1, max_size=12), st.randoms(use_true_random=False))
@settings(deadline=None, max_examples=120)
def test_report_is_invariant_under_row_permutation(rows, rng) -> None:
    rows = _identify(rows)
    shuffled = list(rows)
    rng.shuffle(shuffled)
    base = analyze_bytes(_csv_bytes(rows))
    permuted = analyze_bytes(_csv_bytes(shuffled))
    assert base["groups"] == permuted["groups"], (
        "ORDER-INVARIANCE VIOLATED: exact sums must not depend on row order"
    )
    assert base["fill_count"] == permuted["fill_count"]


@given(st.lists(fill_rows(), min_size=1, max_size=12))
@settings(deadline=None, max_examples=150)
def test_totals_match_an_independent_fraction_oracle(rows) -> None:
    rows = _identify(rows)
    group = analyze_bytes(_csv_bytes(rows))["groups"][0]
    buy = sum((Fraction(r["quantity"]) * Fraction(r["price"]) for r in rows if r["side"] == "BUY"), Fraction(0))
    sell = sum((Fraction(r["quantity"]) * Fraction(r["price"]) for r in rows if r["side"] == "SELL"), Fraction(0))
    assert Fraction(group["buy_notional_quote"]) == buy
    assert Fraction(group["sell_notional_quote"]) == sell
    assert Fraction(group["notional_quote"]) == buy + sell

    fee_known = all(r["fee_amount"] and (r["fee_asset"] == "USDT" or r["fee_quote_value"]) for r in rows)
    fee_oracle = sum(
        (Fraction(r["fee_amount"] if r["fee_asset"] == "USDT" else r["fee_quote_value"]) for r in rows),
        Fraction(0),
    ) if fee_known else None
    assert _fraction_or_none(group["fee_quote_total"]) == fee_oracle
    assert group["missing_fee_valuation_fills"] == sum(
        not (r["fee_amount"] and (r["fee_asset"] == "USDT" or r["fee_quote_value"])) for r in rows
    )

    arrival_known = all(r["arrival_price"] for r in rows)
    slippage_oracle = sum(
        (
            (Fraction(r["price"]) - Fraction(r["arrival_price"])) * Fraction(r["quantity"]) * (1 if r["side"] == "BUY" else -1)
            for r in rows
        ),
        Fraction(0),
    ) if arrival_known else None
    assert _fraction_or_none(group["arrival_slippage_quote"]) == slippage_oracle
    assert group["missing_arrival_benchmark_fills"] == sum(not r["arrival_price"] for r in rows)

    cost = group["execution_shortfall_plus_fees_quote"]
    if fee_oracle is None or slippage_oracle is None:
        assert cost is None and group["evidence_state"] == "PARTIAL_UNKNOWN_COST", (
            "UNKNOWN-IS-NOT-ZERO VIOLATED: a missing component must leave the total null"
        )
    else:
        assert Fraction(cost) == fee_oracle + slippage_oracle
        assert group["evidence_state"] == "COMPLETE_EXECUTION_COMPONENTS"

    native: dict[str, Fraction] = {}
    for r in rows:
        if r["fee_amount"]:
            native[r["fee_asset"]] = native.get(r["fee_asset"], Fraction(0)) + Fraction(r["fee_amount"])
    assert {k: Fraction(v) for k, v in group["fee_totals_native_by_asset"].items()} == native


@given(st.lists(fill_rows(with_arrival=True), min_size=1, max_size=10))
@settings(deadline=None, max_examples=100)
def test_flipping_every_side_negates_slippage_and_swaps_notionals(rows) -> None:
    rows = _identify(rows)
    flipped = [dict(r, side="SELL" if r["side"] == "BUY" else "BUY") for r in rows]
    one = analyze_bytes(_csv_bytes(rows))["groups"][0]
    two = analyze_bytes(_csv_bytes(flipped))["groups"][0]
    assert Fraction(one["arrival_slippage_quote"]) == -Fraction(two["arrival_slippage_quote"])
    assert one["buy_notional_quote"] == two["sell_notional_quote"]
    assert one["sell_notional_quote"] == two["buy_notional_quote"]
    assert one["notional_quote"] == two["notional_quote"]


@given(st.lists(fill_rows(), min_size=1, max_size=8))
@settings(deadline=None, max_examples=100)
def test_csv_round_trip_preserves_every_declared_field(rows) -> None:
    rows = _identify(rows)
    fills = parse_fills(_csv_bytes(rows))
    assert len(fills) == len(rows)
    for fill, row in zip(fills, rows):
        assert (fill.venue, fill.symbol, fill.quote_asset) == ("binance", "BTCUSDT", "USDT")
        assert (fill.trade_id, fill.order_id, fill.side) == (row["trade_id"], row["order_id"], row["side"])
        assert fill.executed_at.strftime("%Y-%m-%dT%H:%M:%SZ") == row["executed_at_utc"]
        assert Fraction(str(fill.quantity)) == Fraction(row["quantity"])
        assert Fraction(str(fill.price)) == Fraction(row["price"])
        if row["fee_amount"]:
            assert fill.fee is not None
            assert Fraction(str(fill.fee.amount)) == Fraction(row["fee_amount"])
            assert fill.fee.asset == row["fee_asset"]
        else:
            assert fill.fee is None
        if row["arrival_price"]:
            assert fill.arrival is not None
            assert Fraction(str(fill.arrival.price)) == Fraction(row["arrival_price"])
            assert fill.arrival.source == row["arrival_source"]
        else:
            assert fill.arrival is None


@given(st.lists(fill_rows(), min_size=1, max_size=6), st.integers(min_value=0))
@settings(deadline=None, max_examples=100)
def test_digest_binds_the_body_and_replay_passes_only_on_identity(rows, salt) -> None:
    rows = _identify(rows)
    raw = _csv_bytes(rows)
    report = analyze_bytes(raw)
    assert report["report_sha256"] == report_digest(report)
    assert verify_report(dict(report), report) == []
    position = len(raw) - 2 - (salt % max(1, len(raw) - len(",".join(HEADERS)) - 2))
    byte = raw[position : position + 1]
    replacement = b"7" if byte != b"7" else b"8"
    tampered = raw[:position] + replacement + raw[position + 1 :]
    try:
        other = analyze_bytes(tampered)
    except EvidenceInputError:
        return  # refused outright: also a correct outcome for a damaged source
    assert other["source_sha256"] != report["source_sha256"]
    assert "source_sha256 differs" in verify_report(dict(other), report)


@given(
    st.sampled_from(["BUY", "SELL"]),
    st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=10**6),
            st.integers(min_value=1, max_value=10**7),
            st.integers(min_value=0, max_value=10**4),
        ),
        min_size=1,
        max_size=8,
    ),
    st.integers(min_value=1, max_value=10**7),
)
@settings(deadline=None, max_examples=100)
def test_sign_convention_matches_the_float_implementation_shortfall(side, legs, arrival_cents) -> None:
    execution_quality = pytest.importorskip("analytics.execution_quality")
    arrival = f"{arrival_cents // 100}.{arrival_cents % 100:02d}"
    rows = []
    for index, (qty_milli, price_cents, fee_milli) in enumerate(legs):
        rows.append(
            {
                "venue": "binance",
                "symbol": "BTCUSDT",
                "quote_asset": "USDT",
                "trade_id": f"T{index}",
                "order_id": "O1",
                "executed_at_utc": "2026-10-20T10:00:01Z",
                "side": side,
                "quantity": f"{qty_milli // 1000}.{qty_milli % 1000:03d}",
                "price": f"{price_cents // 100}.{price_cents % 100:02d}",
                "fee_amount": f"{fee_milli // 1000}.{fee_milli % 1000:03d}",
                "fee_asset": "USDT",
                "fee_quote_value": "",
                "fee_conversion_source": "",
                "arrival_price": arrival,
                "arrival_at_utc": "2026-10-20T10:00:00Z",
                "arrival_source": "submission_snapshot",
            }
        )
    group = analyze_bytes(_csv_bytes(rows))["groups"][0]
    exact = Fraction(group["execution_shortfall_plus_fees_quote"])
    oracle = execution_quality.implementation_shortfall(
        side,
        float(Fraction(arrival)),
        [
            {"quantity": float(Fraction(r["quantity"])), "price": float(Fraction(r["price"])), "fees": float(Fraction(r["fee_amount"]))}
            for r in rows
        ],
    )
    notional = Fraction(group["notional_quote"])
    assert abs(float(exact) - oracle) <= 1e-9 * max(1.0, float(notional)), (
        f"SIGN-PARITY VIOLATED: exact={exact} float_oracle={oracle} side={side}"
    )

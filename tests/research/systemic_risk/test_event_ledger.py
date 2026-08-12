# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Invariant tests for :mod:`research.systemic_risk.event_ledger`."""

from __future__ import annotations

from datetime import date

import pytest

from research.systemic_risk.event_ledger import (
    DEFAULT_LEDGER,
    BankingCrisisEvent,
    BankingCrisisLedger,
)


class TestEventInvariants:
    def test_inv_evt1_end_before_start_rejected(self) -> None:
        with pytest.raises(ValueError, match="INV-EVT1"):
            BankingCrisisEvent(
                country="USA",
                start=date(2008, 1, 1),
                end=date(2007, 12, 31),
                source="LV2018",
                label="bad",
            )

    @pytest.mark.parametrize("country", ["us", "USAA", "12A", "USa"])
    def test_inv_evt2_country_format(self, country: str) -> None:
        with pytest.raises(ValueError, match="INV-EVT2"):
            BankingCrisisEvent(
                country=country,
                start=date(2008, 1, 1),
                end=date(2008, 12, 31),
                source="LV2018",
                label="bad",
            )

    def test_inv_evt1_equal_dates_allowed(self) -> None:
        ev = BankingCrisisEvent(
            country="USA",
            start=date(2008, 1, 1),
            end=date(2008, 1, 1),
            source="LV2018",
            label="point",
        )
        assert ev.start == ev.end

    def test_contains(self) -> None:
        ev = BankingCrisisEvent(
            country="USA",
            start=date(2008, 1, 1),
            end=date(2008, 12, 31),
            source="LV2018",
            label="x",
        )
        assert ev.contains(date(2008, 6, 15))
        assert ev.contains(date(2008, 1, 1))  # inclusive lower
        assert ev.contains(date(2008, 12, 31))  # inclusive upper
        assert not ev.contains(date(2007, 12, 31))
        assert not ev.contains(date(2009, 1, 1))

    def test_overlaps_window(self) -> None:
        ev = BankingCrisisEvent(
            country="USA",
            start=date(2008, 1, 1),
            end=date(2008, 12, 31),
            source="LV2018",
            label="x",
        )
        assert ev.overlaps_window(date(2008, 6, 1), date(2009, 6, 1))
        assert ev.overlaps_window(date(2007, 1, 1), date(2008, 6, 1))
        assert not ev.overlaps_window(date(2009, 1, 1), date(2009, 12, 31))
        assert not ev.overlaps_window(date(2006, 1, 1), date(2007, 12, 31))

    def test_overlaps_window_rejects_inverted_interval(self) -> None:
        ev = BankingCrisisEvent(
            country="USA",
            start=date(2008, 1, 1),
            end=date(2008, 12, 31),
            source="LV2018",
            label="x",
        )
        with pytest.raises(ValueError):
            ev.overlaps_window(date(2009, 1, 1), date(2008, 1, 1))


class TestLedger:
    def test_default_ledger_nonempty(self) -> None:
        assert len(DEFAULT_LEDGER) > 0

    def test_default_ledger_contains_GFC_and_EZ_and_2023(self) -> None:
        labels = {ev.label for ev in DEFAULT_LEDGER.events}
        assert any(lbl.startswith("GFC_USA") for lbl in labels)
        assert any(lbl.startswith("EZ_LATE_GRC") for lbl in labels)
        assert "SVB_FRC_2023" in labels
        assert "CS_2023" in labels

    def test_duplicate_event_rejected(self) -> None:
        ev = BankingCrisisEvent(
            country="USA",
            start=date(2008, 1, 1),
            end=date(2008, 12, 31),
            source="LV2018",
            label="dup",
        )
        with pytest.raises(ValueError, match="duplicate"):
            BankingCrisisLedger(events=(ev, ev))

    def test_by_country_filters(self) -> None:
        usa_events = DEFAULT_LEDGER.by_country("USA")
        assert len(usa_events) >= 2  # GFC + 2023
        assert all(ev.country == "USA" for ev in usa_events)

    def test_crises_in_range(self) -> None:
        in_range = DEFAULT_LEDGER.crises_in_range(date(2007, 1, 1), date(2010, 12, 31))
        assert len(in_range) > 0
        # Every returned event must overlap the requested window.
        for ev in in_range:
            assert ev.overlaps_window(date(2007, 1, 1), date(2010, 12, 31))

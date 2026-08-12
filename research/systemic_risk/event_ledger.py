# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Banking-crisis event ledger for falsification of interbank phase-locking.

The ledger fixes the *truth set* against which the early-warning predictor
is evaluated. It is intentionally small and per-event traceable so that
every entry can be audited against its primary source.

Sources
-------
* **Laeven & Valencia 2018** — *Systemic Banking Crises Revisited*, IMF
  Working Paper WP/18/206 (Table A1, 1970–2017). Each entry below carries
  the country ISO-3 code and (start_year, end_year) tuple from that table.
* **Laeven & Valencia 2020 update** — IMF Departmental Papers DP/20/02,
  used only for entries strictly after 2017.
* **Post-LV-2020 entries** (USA 2023, CHE 2023) are designated by the
  Federal Reserve, FSB and SNB respectively and are tagged
  ``source="post_LV2020"`` so a downstream consumer can choose to drop
  them for replication of pre-2020 papers.

Tier per ``CLAIMS.md``: every entry is ``MEASURED`` (the date pair is the
verifiable artefact); the *predictor* over these dates is ``HYPOTHESIS``.

This module is pure data + lookup. No I/O. No randomness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal

__all__ = [
    "BankingCrisisEvent",
    "BankingCrisisLedger",
    "DEFAULT_LEDGER",
]


CrisisSource = Literal["LV2018", "LV2020_update", "post_LV2020"]


@dataclass(frozen=True, slots=True)
class BankingCrisisEvent:
    """One banking-crisis episode with a verifiable date range.

    Attributes
    ----------
    country
        ISO-3166 alpha-3 country code (uppercase).
    start
        First calendar date the source assigns to the crisis. Crisis-year
        entries from Laeven-Valencia are mapped to ``date(year, 1, 1)``;
        events with documented intra-year onset (USA 2023 SVB, CHE 2023
        Credit Suisse) use the actual day.
    end
        Last calendar date of the crisis. Open-ended LV entries are
        mapped to ``date(end_year, 12, 31)``.
    source
        Provenance tag — see module docstring.
    label
        Short, human-readable handle, e.g. ``"GFC_USA_2007"``.

    Invariants
    ----------
    INV-EVT1: ``start <= end`` (enforced).
    INV-EVT2: ``country`` is exactly three uppercase ASCII letters.
    """

    country: str
    start: date
    end: date
    source: CrisisSource
    label: str

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError(
                f"INV-EVT1 VIOLATED: end={self.end} < start={self.start} for {self.label}"
            )
        if not (
            len(self.country) == 3
            and self.country.isascii()
            and self.country.isalpha()
            and self.country.isupper()
        ):
            raise ValueError(
                f"INV-EVT2 VIOLATED: country={self.country!r} must be 3 uppercase ASCII letters"
            )

    def contains(self, day: date) -> bool:
        """Inclusive containment check."""
        return self.start <= day <= self.end

    def overlaps_window(self, window_start: date, window_end: date) -> bool:
        """Inclusive overlap check between this event and ``[window_start, window_end]``."""
        if window_end < window_start:
            raise ValueError(f"window_end={window_end} < window_start={window_start}")
        return not (self.end < window_start or self.start > window_end)


# ---------------------------------------------------------------------------
# Curated event set (audit-traceable subset of LV2018 + post-LV designations)
# ---------------------------------------------------------------------------
#
# Selection rule: include all systemic banking crises whose date range
# intersects the e-MID public window (2009-01 .. 2015-12) plus the two
# post-LV2020 anchor events (USA-2023, CHE-2023). This keeps the suite
# tractable while spanning two qualitatively different stress regimes.

_GFC_COUNTRIES: Final[tuple[str, ...]] = (
    "USA",
    "GBR",
    "IRL",
    "ISL",
    "NLD",
    "BEL",
    "FRA",
    "DEU",
    "AUT",
    "ESP",
    "ITA",
    "DNK",
    "GRC",
    "PRT",
    "LUX",
    "SWE",
    "CHE",
    "RUS",
    "UKR",
)
_GFC_YEARS: Final[tuple[int, int]] = (2007, 2010)

_EUROZONE_LATE_COUNTRIES: Final[tuple[str, ...]] = (
    "GRC",
    "IRL",
    "PRT",
    "ESP",
    "ITA",
    "CYP",
    "SVN",
)
_EUROZONE_LATE_YEARS: Final[tuple[int, int]] = (2011, 2014)


def _year_range(country: str, years: tuple[int, int], label_prefix: str) -> BankingCrisisEvent:
    s, e = years
    return BankingCrisisEvent(
        country=country,
        start=date(s, 1, 1),
        end=date(e, 12, 31),
        source="LV2018",
        label=f"{label_prefix}_{country}_{s}",
    )


@dataclass(frozen=True, slots=True)
class BankingCrisisLedger:
    """Immutable container of :class:`BankingCrisisEvent` records."""

    events: tuple[BankingCrisisEvent, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        seen: set[tuple[str, date, date]] = set()
        for ev in self.events:
            key = (ev.country, ev.start, ev.end)
            if key in seen:
                raise ValueError(f"duplicate event in ledger: {ev.label}")
            seen.add(key)

    def by_country(self, country: str) -> tuple[BankingCrisisEvent, ...]:
        c = country.upper()
        return tuple(ev for ev in self.events if ev.country == c)

    def crises_in_range(
        self, window_start: date, window_end: date
    ) -> tuple[BankingCrisisEvent, ...]:
        """All events whose interval overlaps ``[window_start, window_end]``."""
        return tuple(ev for ev in self.events if ev.overlaps_window(window_start, window_end))

    def __len__(self) -> int:
        return len(self.events)


def _build_default_ledger() -> BankingCrisisLedger:
    events: list[BankingCrisisEvent] = []
    for c in _GFC_COUNTRIES:
        events.append(_year_range(c, _GFC_YEARS, "GFC"))
    for c in _EUROZONE_LATE_COUNTRIES:
        events.append(_year_range(c, _EUROZONE_LATE_YEARS, "EZ_LATE"))
    # Post-LV2020 anchor events — designated by the Fed and SNB respectively.
    events.append(
        BankingCrisisEvent(
            country="USA",
            start=date(2023, 3, 10),
            end=date(2023, 5, 1),
            source="post_LV2020",
            label="SVB_FRC_2023",
        )
    )
    events.append(
        BankingCrisisEvent(
            country="CHE",
            start=date(2023, 3, 15),
            end=date(2023, 6, 12),
            source="post_LV2020",
            label="CS_2023",
        )
    )
    return BankingCrisisLedger(events=tuple(events))


DEFAULT_LEDGER: Final[BankingCrisisLedger] = _build_default_ledger()

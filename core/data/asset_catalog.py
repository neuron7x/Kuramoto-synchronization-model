# SPDX-License-Identifier: LicenseRef-TradePulse-Proprietary
"""Canonical asset directory and symbol mapping utilities.

The :class:`AssetCatalog` centralises metadata about traded instruments so the
rest of the platform can operate on consistent identifiers.  It keeps track of
primary symbols, venue specific aliases, human readable names, lifecycle
events (e.g. delistings) and the historical symbols that were previously
assigned to an asset.  Historical mappings are retained to guarantee that past
market data continues to resolve to the correct instrument even after renames
or exchange specific changes.

The module purposely focuses on in-memory management – persistence can be
layered on top by serialising :class:`AssetRecord` instances.  The catalog is
optimised for fast lookup of both canonical and venue scoped symbols while
ensuring conflicting assignments are rejected eagerly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Iterable, Mapping, MutableMapping, Optional, Set, Tuple

from core.data.catalog import normalize_symbol, normalize_venue
from core.data.models import InstrumentType

__all__ = [
    "AssetCatalog",
    "AssetRecord",
    "AssetStatus",
]


class AssetStatus(str, Enum):
    """Lifecycle state for an asset in the catalog."""

    ACTIVE = "active"
    DELISTED = "delisted"


@dataclass(slots=True)
class AssetRecord:
    """Metadata describing a traded instrument.

    Parameters
    ----------
    asset_id:
        Stable identifier for the asset.  Typically sourced from internal
        governance systems.  Must remain unchanged even if venue symbols or
        names evolve.
    name:
        Human readable name for the instrument (e.g. ``"Bitcoin"`` or
        ``"Apple Inc."``).
    primary_symbol:
        Canonical symbol used across TradePulse.  The catalog stores a
        normalised representation using :func:`core.data.catalog.normalize_symbol`.
    instrument_type:
        Category of the instrument.  Defaults to spot instruments.
    venue_symbols:
        Optional mapping from venue identifiers to the venue specific symbol
        for the asset.
    listed_at / delisted_at:
        Optional timestamps that capture the lifecycle of the asset.
    """

    asset_id: str
    name: str
    primary_symbol: str
    instrument_type: InstrumentType = InstrumentType.SPOT
    venue_symbols: MutableMapping[str, str] = field(default_factory=dict)
    status: AssetStatus = AssetStatus.ACTIVE
    listed_at: datetime | None = None
    delisted_at: datetime | None = None
    historical_symbols: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        asset_id = self.asset_id.strip()
        if not asset_id:
            raise ValueError("asset_id must be a non-empty string")
        self.asset_id = asset_id

        name = self.name.strip()
        if not name:
            raise ValueError("name must be a non-empty string")
        self.name = name

        self.primary_symbol = normalize_symbol(
            self.primary_symbol,
            instrument_type_hint=self.instrument_type,
        )

        normalised_venue_symbols: Dict[str, str] = {}
        for venue, symbol in self.venue_symbols.items():
            normalised_venue = normalize_venue(venue)
            normalised_symbol = normalize_symbol(
                symbol,
                instrument_type_hint=self.instrument_type,
            )
            normalised_venue_symbols[normalised_venue] = normalised_symbol
        self.venue_symbols = normalised_venue_symbols

        # Historical symbols always include the current assignments so lookups
        # remain stable even if the catalog is rehydrated from persisted data.
        combined_history = set(self.historical_symbols)
        combined_history.add(self.primary_symbol)
        combined_history.update(self.venue_symbols.values())
        self.historical_symbols = combined_history

    def set_name(self, name: str) -> None:
        stripped = name.strip()
        if not stripped:
            raise ValueError("name must be a non-empty string")
        self.name = stripped

    def set_status(self, status: AssetStatus, *, when: datetime | None = None) -> None:
        self.status = status
        if status == AssetStatus.DELISTED:
            self.delisted_at = when
        elif status == AssetStatus.ACTIVE and self.delisted_at is not None:
            # Reactivation clears the delisting timestamp.
            self.delisted_at = None

    def record_symbol(self, symbol: str) -> None:
        """Add *symbol* to the historical history set."""

        self.historical_symbols.add(symbol)


class AssetCatalog:
    """In-memory registry of assets and symbol mappings."""

    def __init__(self, assets: Optional[Iterable[AssetRecord]] = None):
        self._assets: Dict[str, AssetRecord] = {}
        self._symbol_index: Dict[Tuple[str, str | None], str] = {}
        self._historical_index: Dict[str, Set[str]] = {}
        if assets is not None:
            for asset in assets:
                self.register(asset)

    # ------------------------------------------------------------------ helpers
    def _bind_symbol(
        self,
        asset: AssetRecord,
        symbol: str,
        *,
        venue: str | None,
        historical: bool = False,
    ) -> None:
        key = (symbol, venue)
        if historical:
            self._historical_index.setdefault(symbol, set()).add(asset.asset_id)
        else:
            existing = self._symbol_index.get(key)
            if existing is not None and existing != asset.asset_id:
                raise ValueError(
                    f"symbol {symbol!r} already registered for asset {existing}"
                )
            self._symbol_index[key] = asset.asset_id
        asset.record_symbol(symbol)

    def _unbind_symbol(self, asset_id: str, symbol: str, venue: str | None) -> None:
        key = (symbol, venue)
        existing = self._symbol_index.get(key)
        if existing == asset_id:
            del self._symbol_index[key]

    def _get_asset(self, asset_id: str) -> AssetRecord:
        try:
            return self._assets[asset_id]
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise KeyError(f"asset {asset_id!r} is not registered") from exc

    # ------------------------------------------------------------------ builders
    def create_asset(
        self,
        *,
        asset_id: str,
        name: str,
        primary_symbol: str,
        instrument_type: InstrumentType = InstrumentType.SPOT,
        venue_symbols: Mapping[str, str] | None = None,
        listed_at: datetime | None = None,
    ) -> AssetRecord:
        record = AssetRecord(
            asset_id=asset_id,
            name=name,
            primary_symbol=primary_symbol,
            instrument_type=instrument_type,
            venue_symbols=dict(venue_symbols or {}),
            listed_at=listed_at,
        )
        return self.register(record)

    def register(self, asset: AssetRecord) -> AssetRecord:
        if asset.asset_id in self._assets:
            raise ValueError(f"asset {asset.asset_id!r} already registered")
        self._assets[asset.asset_id] = asset

        # Bind primary and venue scoped symbols.
        self._bind_symbol(asset, asset.primary_symbol, venue=None)
        for venue, symbol in asset.venue_symbols.items():
            self._bind_symbol(asset, symbol, venue=venue)

        # Seed historical index with known identifiers.
        for symbol in asset.historical_symbols:
            self._bind_symbol(asset, symbol, venue=None, historical=True)

        return asset

    # ----------------------------------------------------------------- mutation
    def update_name(self, asset_id: str, name: str) -> AssetRecord:
        asset = self._get_asset(asset_id)
        asset.set_name(name)
        return asset

    def update_primary_symbol(
        self,
        asset_id: str,
        symbol: str,
        *,
        instrument_type_hint: InstrumentType | None = None,
    ) -> AssetRecord:
        asset = self._get_asset(asset_id)
        new_symbol = normalize_symbol(
            symbol,
            instrument_type_hint=instrument_type_hint or asset.instrument_type,
        )
        if new_symbol == asset.primary_symbol:
            return asset

        old_symbol = asset.primary_symbol
        self._unbind_symbol(asset.asset_id, old_symbol, None)
        self._bind_symbol(asset, old_symbol, venue=None, historical=True)

        asset.primary_symbol = new_symbol
        self._bind_symbol(asset, new_symbol, venue=None)
        return asset

    def synchronize_venue_symbol(
        self,
        asset_id: str,
        venue: str,
        symbol: str,
    ) -> AssetRecord:
        asset = self._get_asset(asset_id)
        normalised_venue = normalize_venue(venue)
        new_symbol = normalize_symbol(
            symbol,
            instrument_type_hint=asset.instrument_type,
        )

        previous = asset.venue_symbols.get(normalised_venue)
        if previous == new_symbol:
            return asset

        if previous is not None:
            self._unbind_symbol(asset.asset_id, previous, normalised_venue)
            self._bind_symbol(asset, previous, venue=None, historical=True)

        asset.venue_symbols[normalised_venue] = new_symbol
        self._bind_symbol(asset, new_symbol, venue=normalised_venue)
        return asset

    def mark_delisted(
        self, asset_id: str, *, when: datetime | None = None
    ) -> AssetRecord:
        asset = self._get_asset(asset_id)
        asset.set_status(AssetStatus.DELISTED, when=when)
        return asset

    def mark_active(self, asset_id: str) -> AssetRecord:
        asset = self._get_asset(asset_id)
        asset.set_status(AssetStatus.ACTIVE)
        return asset

    # ---------------------------------------------------------------- lookups
    def _normalised_candidates(self, symbol: str) -> list[str]:
        candidates: list[str] = []
        seen: Set[str] = set()

        def _append(value: str) -> None:
            if value not in seen:
                seen.add(value)
                candidates.append(value)

        base = normalize_symbol(symbol)
        _append(base)
        for hint in InstrumentType:
            try:
                candidate = normalize_symbol(symbol, instrument_type_hint=hint)
            except ValueError:
                continue
            _append(candidate)
        return candidates

    def resolve(
        self,
        symbol: str,
        *,
        venue: str | None = None,
        include_historical: bool = True,
    ) -> AssetRecord:
        """Resolve *symbol* to an :class:`AssetRecord`.

        Parameters
        ----------
        symbol:
            Symbol to resolve.  The value is normalised before lookup.
        venue:
            Optional venue identifier.  If provided the lookup favours
            venue-specific assignments.  When omitted, the catalog falls back to
            the canonical symbol.
        include_historical:
            When ``True`` the resolver also considers previously assigned
            symbols.  Ambiguous historical matches raise :class:`LookupError`.
        """

        candidates = self._normalised_candidates(symbol)
        venue_key = normalize_venue(venue) if venue is not None else None

        if venue_key is not None:
            for candidate in candidates:
                asset_id = self._symbol_index.get((candidate, venue_key))
                if asset_id is not None:
                    return self._assets[asset_id]

        for candidate in candidates:
            asset_id = self._symbol_index.get((candidate, None))
            if asset_id is not None:
                return self._assets[asset_id]

        if include_historical:
            matches: Set[str] = set()
            for candidate in candidates:
                matches.update(self._historical_index.get(candidate, set()))
            if not matches:
                raise KeyError(f"symbol {symbol!r} is not registered")
            if len(matches) > 1:
                raise LookupError(
                    f"symbol {symbol!r} maps to multiple assets: {sorted(matches)}"
                )
            return self._assets[next(iter(matches))]

        raise KeyError(f"symbol {symbol!r} is not registered")

    def get(self, asset_id: str) -> AssetRecord:
        return self._get_asset(asset_id)

    def get_display_symbol(self, asset_id: str, venue: str | None = None) -> str:
        asset = self._get_asset(asset_id)
        if venue is not None:
            normalised_venue = normalize_venue(venue)
            symbol = asset.venue_symbols.get(normalised_venue)
            if symbol is not None:
                return symbol
        return asset.primary_symbol

    # ----------------------------------------------------------------- queries
    def assets(self, *, status: AssetStatus | None = None) -> Iterable[AssetRecord]:
        for asset in self._assets.values():
            if status is None or asset.status == status:
                yield asset

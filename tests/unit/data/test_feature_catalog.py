# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth for the file-backed feature catalog.

The catalog is the CLI's record of *which artifact was produced from which config, with what
lineage*. Two `x or default` fall-throughs (metadata, lineage) were unwitnessed: nothing
registered an artifact WITH metadata or lineage and read them back, so a mutant that dropped
either silently on registration survived. A provenance record that silently forgets the
provenance is worse than no record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config.cli_models import GeoSyncBaseConfig
from core.data.feature_catalog import CatalogEntry, FeatureCatalog


def _config() -> GeoSyncBaseConfig:
    return GeoSyncBaseConfig(name="unit", description="teeth", tags=["t"])


def _artifact(tmp_path: Path) -> Path:
    artifact = tmp_path / "features.parquet"
    artifact.write_bytes(b"payload-bytes")
    return artifact


def test_register_round_trips_supplied_metadata_and_lineage(tmp_path: Path) -> None:
    """`metadata or {}` / `lineage or []` must STORE what is passed, not the empty default.

    Under `Or -> And`, `metadata or {}` becomes `metadata and {}`, which is `{}` whenever
    metadata is truthy — the caller's provenance is dropped on every non-empty registration.
    """
    catalog = FeatureCatalog(tmp_path / "catalog.json")
    entry = catalog.register(
        "alpha",
        _artifact(tmp_path),
        config=_config(),
        metadata={"rows": 1024, "source": "binance"},
        lineage=["raw-v1", "validated-v1"],
    )

    assert isinstance(entry, CatalogEntry)
    assert entry.metadata == {"rows": 1024, "source": "binance"}
    assert entry.lineage == ["raw-v1", "validated-v1"]

    # And it survives a reload from disk, not just the in-memory return value.
    reloaded = FeatureCatalog(tmp_path / "catalog.json").find("alpha")
    assert reloaded is not None
    assert reloaded.metadata == {"rows": 1024, "source": "binance"}
    assert reloaded.lineage == ["raw-v1", "validated-v1"]


def test_register_defaults_to_empty_when_nothing_is_supplied(tmp_path: Path) -> None:
    """Matched control: the fall-through IS the right answer when the caller passes nothing."""
    catalog = FeatureCatalog(tmp_path / "catalog.json")
    entry = catalog.register("beta", _artifact(tmp_path), config=_config())

    assert entry.metadata == {}
    assert entry.lineage == []


def test_reregistering_a_name_replaces_only_that_name(tmp_path: Path) -> None:
    """`[item for item in entries if item.get("name") != name]` dedups by name on re-register.

    Under `NotEq -> Eq` the filter keeps only entries that DO match the name — so registering
    a second, different artifact silently deletes every other artifact in the catalog. The
    only way to see it is to register two names, re-register one, and demand the other is
    still there.
    """
    catalog = FeatureCatalog(tmp_path / "catalog.json")
    catalog.register("keep", _artifact(tmp_path), config=_config())
    catalog.register("replace", _artifact(tmp_path), config=_config(), metadata={"v": 1})

    updated = tmp_path / "updated.bin"
    updated.write_bytes(b"new-bytes")
    catalog.register("replace", updated, config=_config(), metadata={"v": 2})

    assert catalog.find("keep") is not None, "an unrelated entry was deleted on re-register"
    replaced = catalog.find("replace")
    assert replaced is not None
    assert replaced.metadata == {"v": 2}, "the re-registration did not overwrite the old entry"
    # Exactly one entry per name -- no duplicate accumulation.
    names = [e["name"] for e in catalog._load_entries()]  # noqa: SLF001 -- inspecting persisted state
    assert sorted(names) == ["keep", "replace"]


def test_checksum_binds_the_entry_to_the_bytes_on_disk(tmp_path: Path) -> None:
    """A provenance checksum that does not change with the artifact is not provenance."""
    a = tmp_path / "a.bin"
    a.write_bytes(b"one")
    b = tmp_path / "b.bin"
    b.write_bytes(b"two")

    catalog = FeatureCatalog(tmp_path / "catalog.json")
    entry_a = catalog.register("a", a, config=_config())
    entry_b = catalog.register("b", b, config=_config())

    assert entry_a.checksum != entry_b.checksum

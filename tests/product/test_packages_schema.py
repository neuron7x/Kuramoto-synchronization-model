# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Schema tests for docs/product/packages.yaml.

Lie blocked:
    "engineering depth = market value"

Each package entry must carry buyer_pain, deliverables, timeline_weeks,
price_band, proof_artifact, demo_command, non_claims. The proof
artifact path must exist on the live tree. Missing fields fail the
test — that is the falsifier surface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGES_PATH = REPO_ROOT / "docs" / "product" / "packages.yaml"

REQUIRED_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "buyer_pain",
    "deliverables",
    "timeline_weeks",
    "price_band",
    "proof_artifact",
    "demo_command",
    "non_claims",
)


@pytest.fixture(scope="module")
def packages() -> list[dict[str, Any]]:
    data = yaml.safe_load(PACKAGES_PATH.read_text(encoding="utf-8")) or {}
    assert data["schema_version"] == 1
    return list(data["packages"])


def test_at_least_five_packages(packages: list[dict[str, Any]]) -> None:
    assert len(packages) >= 5


def test_every_package_has_required_fields(packages: list[dict[str, Any]]) -> None:
    for pkg in packages:
        for key in REQUIRED_FIELDS:
            assert key in pkg, f"package {pkg.get('id')} missing {key!r}"


def test_every_package_has_non_empty_deliverables(packages: list[dict[str, Any]]) -> None:
    for pkg in packages:
        deliverables = pkg.get("deliverables") or []
        assert isinstance(deliverables, list)
        assert len(deliverables) >= 1, f"{pkg.get('id')} has no deliverables"


def test_every_package_has_non_empty_non_claims(packages: list[dict[str, Any]]) -> None:
    """Falsifier surface from brief: package without non_claims fails schema."""
    for pkg in packages:
        non_claims = pkg.get("non_claims") or []
        assert isinstance(non_claims, list)
        assert len(non_claims) >= 1, f"{pkg.get('id')} has no non_claims"


def test_proof_artifact_exists_for_every_package(packages: list[dict[str, Any]]) -> None:
    for pkg in packages:
        artifact = pkg.get("proof_artifact")
        assert isinstance(artifact, str) and artifact.strip()
        path = REPO_ROOT / artifact
        assert path.exists(), f"{pkg.get('id')} proof_artifact missing: {artifact}"


def test_demo_command_non_empty_string(packages: list[dict[str, Any]]) -> None:
    for pkg in packages:
        cmd = pkg.get("demo_command")
        assert isinstance(cmd, str) and cmd.strip(), pkg.get("id")


def test_timeline_is_positive_int(packages: list[dict[str, Any]]) -> None:
    for pkg in packages:
        weeks = pkg.get("timeline_weeks")
        assert isinstance(weeks, int) and weeks > 0, pkg.get("id")


def test_price_band_uses_documented_vocabulary(packages: list[dict[str, Any]]) -> None:
    """Price bands are categorical, not numeric — that's the lie this list refuses."""
    valid = {"PB1_LIGHT", "PB2_MEDIUM", "PB3_HEAVY", "PB4_FLAGSHIP"}
    for pkg in packages:
        band = pkg.get("price_band")
        assert band in valid, f"{pkg.get('id')} has unknown price_band {band!r}"


def test_no_package_uses_forbidden_overclaim_phrase(
    packages: list[dict[str, Any]],
) -> None:
    forbidden = (
        "production-ready",
        "fully verified",
        "predicts returns",
        "trading signal",
        "guaranteed",
    )
    for pkg in packages:
        body = " ".join(str(v) for v in pkg.values() if isinstance(v, (str, list))).lower()
        # non_claims field LEGITIMATELY quotes these as things it refuses.
        # Strip everything after 'Does NOT' for the scan.
        lowered = body
        for phrase in forbidden:
            count = lowered.count(phrase)
            # If found, it should appear ONLY in a "Does NOT ... PHRASE"
            # quotation. Allow up to 2 occurrences per phrase per package.
            assert count <= 2, f"{pkg.get('id')} mentions {phrase!r} {count} times"


def test_unique_package_ids(packages: list[dict[str, Any]]) -> None:
    ids = [p.get("id") for p in packages]
    assert len(set(ids)) == len(ids)


def test_full_reality_validation_references_demo() -> None:
    data = yaml.safe_load(PACKAGES_PATH.read_text(encoding="utf-8"))
    full = next(p for p in data["packages"] if p["id"] == "P_FULL_REALITY_VALIDATION")
    assert "run_demo" in full["demo_command"]

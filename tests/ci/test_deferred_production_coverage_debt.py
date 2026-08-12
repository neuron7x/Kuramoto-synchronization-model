# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail closed on stale / untracked deferred-production coverage debt.

`deferred_production` is honest but dangerous: without a bound it becomes a
permanent hiding place for real production code that ships in the wheel but is
never measured. This ratchet forces every deferred-production allowlist entry to
carry an owner, a tracking issue, a target coverage profile, a creation date, an
age bound, and a concrete next test slice — and it fails once that bound is
exceeded, so the debt cannot sit forever.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ALLOWLIST = ROOT / "tests" / "fixtures" / "coverage_surface_allowlist.json"

REQUIRED_FIELDS = (
    "owner",
    "tracking_issue",
    "target_profile",
    "created_at",
    "max_age_days",
    "next_test_slice",
)


def _deferred_entries() -> list[tuple[str, dict]]:
    data: dict[str, dict] = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return [(root, e) for root, e in data.items() if e.get("reason") == "deferred_production"]


def test_deferred_production_entries_are_fully_tracked() -> None:
    """Every deferred-production root carries all six tracking fields, validly."""
    for root, entry in _deferred_entries():
        missing = [f for f in REQUIRED_FIELDS if f not in entry]
        assert not missing, (
            f"deferred_production root {root!r} is untracked debt — missing {missing}. "
            f"A production root may only be deferred with owner + tracking_issue + "
            f"target_profile + created_at + max_age_days + next_test_slice."
        )
        assert str(entry["owner"]).strip(), f"{root!r}: empty owner"
        assert re.fullmatch(r"#\d+", str(entry["tracking_issue"])), (
            f"{root!r}: tracking_issue {entry['tracking_issue']!r} must be '#<number>'"
        )
        profile = ROOT / str(entry["target_profile"])
        assert profile.is_file(), (
            f"{root!r}: target_profile {entry['target_profile']!r} does not exist"
        )
        # created_at must parse as an ISO date.
        try:
            date.fromisoformat(str(entry["created_at"]))
        except ValueError:
            pytest.fail(f"{root!r}: created_at {entry['created_at']!r} is not ISO YYYY-MM-DD")
        assert isinstance(entry["max_age_days"], int) and entry["max_age_days"] > 0, (
            f"{root!r}: max_age_days must be a positive int, got {entry['max_age_days']!r}"
        )
        slice_glob = str(entry["next_test_slice"]).strip()
        assert slice_glob and slice_glob.startswith("tests/"), (
            f"{root!r}: next_test_slice {slice_glob!r} must be a concrete tests/ path glob"
        )


def test_no_deferred_production_debt_is_past_its_age_bound() -> None:
    """A deferred-production entry that outlives max_age_days fails closed.

    This is the forcing function: the debt must be paid (measured/removed) or the
    entry deliberately refreshed with a new created_at + justification before the
    bound elapses. Time-dependent BY DESIGN — an allowlist without an enforced
    expiry is hidden, permanent debt.
    """
    today = datetime.now(timezone.utc).date()
    overdue: list[str] = []
    for root, entry in _deferred_entries():
        try:
            created = date.fromisoformat(str(entry.get("created_at", "")))
            age_bound = int(entry.get("max_age_days", 0))
        except (ValueError, TypeError):
            continue  # field-validity is asserted by the sibling test
        age_days = (today - created).days
        if age_days > age_bound:
            overdue.append(
                f"{root} (age {age_days}d > bound {age_bound}d; created {created}, "
                f"issue {entry.get('tracking_issue')})"
            )
    assert not overdue, (
        "deferred_production coverage debt is PAST its age bound — measure it, remove it "
        "from packaging, or refresh created_at with justification: " + "; ".join(overdue)
    )


# ---------------------------------------------------------------------------
# Phase-3 terminal state: deferred_production is fully expired.
# ---------------------------------------------------------------------------
def test_deferred_production_is_fully_expired() -> None:
    """Once libs, modules and geosync_pro are measured, NO production root may
    remain deferred. deferred_production is a transient bootstrap category, not a
    permanent home — every packaged production root is now measured or removed, so
    the count must be zero and can never silently grow back.
    """
    deferred = [root for root, _ in _deferred_entries()]
    assert deferred == [], (
        "production roots are still deferred — measure them under a coverage "
        f"profile or remove them from packaging, do not re-defer: {deferred}"
    )

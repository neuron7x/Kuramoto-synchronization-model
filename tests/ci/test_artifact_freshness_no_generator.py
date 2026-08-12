# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Fail-closed regression: a deterministic artifact with no generator cannot be
declared "fresh".

Before the fix, a ``deterministic`` spec with an absent/empty ``generator`` was
never regenerated, yet the snapshot-vs-committed compare trivially passed (the
committed bytes equal themselves) and the gate reported it fresh. Freshness is
unprovable without a generator, so ``check()`` must now emit an error.
"""

from __future__ import annotations

import pytest

import scripts.ci.check_artifact_freshness as fresh
from scripts.ci.check_artifact_freshness import ROOT, _ArtifactSpec

_EXISTING_JSON = "artifacts/manifest.json"


def test_existing_artifact_present() -> None:
    assert (ROOT / _EXISTING_JSON).is_file()


def test_deterministic_spec_without_generator_is_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _ArtifactSpec(
        artifact=_EXISTING_JSON,
        generator=[],  # no generator -> freshness cannot be proven
        sources=[],
        determinism_class="deterministic",
    )
    monkeypatch.setattr(fresh, "_all_specs", lambda: [spec])
    errors = fresh.check()
    assert any(
        "declares no generator" in e and _EXISTING_JSON in e for e in errors
    ), errors


def test_deterministic_spec_with_generator_is_not_flagged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = _ArtifactSpec(
        artifact=_EXISTING_JSON,
        generator=["scripts/ci/some_generator.py"],
        sources=[],
        determinism_class="deterministic",
    )
    monkeypatch.setattr(fresh, "_all_specs", lambda: [spec])
    # Avoid actually running the (fictional) generator: pretend it reproduced
    # the committed bytes so no STALE error masks the assertion under test.
    committed = fresh._sha256((ROOT / _EXISTING_JSON).read_bytes())
    monkeypatch.setattr(fresh, "_regenerate_all", lambda specs: {_EXISTING_JSON: committed})
    errors = fresh.check()
    assert not any("declares no generator" in e for e in errors), errors

"""Smoke tests for the visualization pipeline.

These tests verify the rendering module works end-to-end on the checked-in
Session 1 artifacts. Pixel-exact image comparison is avoided — matplotlib
output is not byte-identical across versions/platforms. Instead we assert:

    - render_all returns three existing PNG paths
    - each PNG is non-empty (> 10 KB)
    - each PNG has the expected PNG magic bytes
    - missing-artifact paths raise FileNotFoundError with a clear message
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("matplotlib")

from research.microstructure.visualize import FigurePaths, render_all  # noqa: E402

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _fixtures_present() -> bool:
    required = [
        "L2_KILLTEST_VERDICT.json",
        "L2_IC_ATTRIBUTION.json",
        "L2_ROBUSTNESS.json",
        "L2_PURGED_CV.json",
        "L2_SPECTRAL.json",
        "L2_HURST.json",
        "L2_DIURNAL_PROFILE.json",
        "L2_TRANSFER_ENTROPY.json",
        "L2_CONDITIONAL_TE.json",
        "L2_REGIME_MARKOV.json",
        "L2_EXEC_COST_SWEEP.json",
        "L2_WALK_FORWARD.json",
        "L2_WALK_FORWARD_SUMMARY.json",
    ]
    results = Path("results")
    return all((results / name).exists() for name in required)


@pytest.mark.skipif(not _fixtures_present(), reason="results fixtures unavailable")
def test_render_all_produces_five_nonempty_pngs(tmp_path: Path) -> None:
    paths = render_all(Path("results"), tmp_path)
    assert isinstance(paths, FigurePaths)
    for p in (
        paths.cover,
        paths.signal_validation,
        paths.dynamics,
        paths.coupling,
        paths.stability,
    ):
        assert p.exists(), f"expected figure missing: {p}"
        size = p.stat().st_size
        assert size > 10 * 1024, f"{p} is suspiciously small ({size} bytes)"
        with p.open("rb") as fh:
            header = fh.read(8)
        assert header == _PNG_MAGIC, f"{p} is not a valid PNG file"


def test_render_all_raises_on_missing_artifact(tmp_path: Path) -> None:
    empty_results = tmp_path / "empty_results"
    empty_results.mkdir()
    with pytest.raises(FileNotFoundError, match="expected artifact missing"):
        render_all(empty_results, tmp_path / "figures")

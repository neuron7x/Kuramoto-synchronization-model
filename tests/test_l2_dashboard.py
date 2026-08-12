"""Tests for the HTML demo dashboard renderer."""

from __future__ import annotations

from pathlib import Path

import pytest

from research.microstructure.dashboard import render_dashboard


def _has_all_inputs() -> bool:
    required = (
        "L2_KILLTEST_VERDICT.json",
        "L2_ROBUSTNESS.json",
        "L2_PURGED_CV.json",
        "L2_SPECTRAL.json",
        "L2_HURST.json",
        "L2_TRANSFER_ENTROPY.json",
        "L2_CONDITIONAL_TE.json",
        "L2_WALK_FORWARD_SUMMARY.json",
    )
    return all(Path("results", name).exists() for name in required)


@pytest.mark.skipif(not _has_all_inputs(), reason="core results fixtures unavailable")
def test_dashboard_renders_valid_html(tmp_path: Path) -> None:
    out = tmp_path / "index.html"
    path = render_dashboard(Path("results"), out)
    assert path == out
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert "<!doctype html>" in text.lower()
    assert "</html>" in text
    assert "VERDICT · PROCEED" in text
    # All five canonical figures referenced
    for fig in (
        "fig0_cover.png",
        "fig1_signal_validation.png",
        "fig2_dynamics.png",
        "fig3_coupling.png",
        "fig4_stability.png",
    ):
        assert fig in text, f"{fig} missing from dashboard"


@pytest.mark.skipif(not _has_all_inputs(), reason="core results fixtures unavailable")
def test_dashboard_embeds_ten_axis_outcomes(tmp_path: Path) -> None:
    out = tmp_path / "index.html"
    render_dashboard(Path("results"), out)
    text = out.read_text(encoding="utf-8")
    for needle in (
        "Kill test",
        "Bootstrap CI",
        "Deflated Sharpe",
        "Purged K-fold",
        "Mutual information",
        "Spectral β",
        "DFA Hurst",
        "Transfer Entropy",
        "Conditional TE",
        "Walk-forward",
    ):
        assert needle in text, f"axis '{needle}' missing"


@pytest.mark.skipif(not _has_all_inputs(), reason="core results fixtures unavailable")
def test_dashboard_uses_only_relative_image_paths(tmp_path: Path) -> None:
    """Dashboard must reference figures relatively so file:// opens work."""
    out = tmp_path / "index.html"
    render_dashboard(Path("results"), out)
    text = out.read_text(encoding="utf-8")
    assert "src='http" not in text
    assert 'src="http' not in text


@pytest.mark.skipif(not _has_all_inputs(), reason="core results fixtures unavailable")
def test_dashboard_has_no_external_script_tags(tmp_path: Path) -> None:
    """Self-contained: no <script src=...>, no CDN dependencies."""
    out = tmp_path / "index.html"
    render_dashboard(Path("results"), out)
    text = out.read_text(encoding="utf-8")
    assert "<script" not in text.lower()

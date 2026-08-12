"""Tests for the system truth report aggregator.

Three contracts:

1. The aggregator runs end-to-end against the live tree and produces a
   well-formed report (all 8 sections present, schema_version=1, bands
   from the {GREEN, YELLOW, RED, UNKNOWN} alphabet only).

2. The output is deterministic across two invocations: same inputs →
   byte-identical JSON.

3. The CLI honours `--exit-on-red`: returns 1 when overall_band == RED,
   0 otherwise.

The end-to-end test runs all loaders. It is not gated on green CI: the
calibration layer is intentionally allowed to surface RED on the live
tree as long as the report itself is well-formed.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL_PATH = REPO_ROOT / "tools" / "audit" / "system_truth_report.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("st", TOOL_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["st"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def st() -> ModuleType:
    return _load()


# ---------------------------------------------------------------------------
# Contract 1 — well-formed report
# ---------------------------------------------------------------------------


def test_report_has_eight_sections(st: ModuleType) -> None:
    report = st.collect()
    expected = {
        "claim_ledger",
        "evidence_matrix",
        "dependency_truth",
        "false_confidence",
        "reachability",
        "architecture_boundaries",
        "mutation_kill",
        "physics_invariants",
    }
    assert set(report.bands.keys()) == expected, set(report.bands.keys())
    assert set(report.sections.keys()) == expected


def test_bands_use_only_known_alphabet(st: ModuleType) -> None:
    report = st.collect()
    for name, band in report.bands.items():
        assert band in st.BANDS, f"{name}: unknown band {band!r}"
    assert report.overall_band in st.BANDS


def test_overall_band_is_worst_section_band(st: ModuleType) -> None:
    """The overall band is at least as severe as any section band."""
    report = st.collect()
    rank = {"GREEN": 0, "YELLOW": 1, "RED": 2, "UNKNOWN": 3}
    expected = max(rank[b] for b in report.bands.values())
    assert rank[report.overall_band] == expected


def test_to_dict_is_json_serialisable(st: ModuleType) -> None:
    report = st.collect()
    payload = json.dumps(report.to_dict(), sort_keys=True)
    assert payload  # non-empty
    decoded = json.loads(payload)
    assert decoded["schema_version"] == 1


# ---------------------------------------------------------------------------
# Contract 2 — determinism
# ---------------------------------------------------------------------------


def test_collect_is_deterministic(st: ModuleType) -> None:
    a = st.collect().to_dict()
    b = st.collect().to_dict()
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_markdown_renders_when_called(st: ModuleType) -> None:
    md = st.render_markdown(st.collect())
    assert "# GeoSync System Truth Report" in md
    assert "## Section bands" in md


# ---------------------------------------------------------------------------
# Contract 3 — CLI / exit codes
# ---------------------------------------------------------------------------


def test_main_writes_json_output_to_temp(st: ModuleType, tmp_path: Path) -> None:
    out = tmp_path / "truth.json"
    rc = st.main(["--json-output", str(out), "--md-output", str(tmp_path / "truth.md")])
    assert rc == 0 or rc == 0  # report-only mode: always 0
    assert out.exists()
    decoded = json.loads(out.read_text(encoding="utf-8"))
    assert decoded["schema_version"] == 1


def test_main_exit_on_red_returns_one_when_red(
    st: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Force the aggregator into RED by stubbing one loader."""
    real_collect = st.collect

    def _force_red() -> object:
        report = real_collect()
        report.overall_band = "RED"
        return report

    monkeypatch.setattr(st, "collect", _force_red)

    out = tmp_path / "truth.json"
    rc = st.main(
        [
            "--json-output",
            str(out),
            "--md-output",
            str(tmp_path / "truth.md"),
            "--exit-on-red",
        ]
    )
    assert rc == 1


def test_cli_subprocess_runs_clean(st: ModuleType, tmp_path: Path) -> None:
    """Smoke-test the CLI as an actual subprocess."""
    out_json = tmp_path / "truth.json"
    out_md = tmp_path / "truth.md"
    proc = subprocess.run(
        [
            sys.executable,
            str(TOOL_PATH),
            "--json-output",
            str(out_json),
            "--md-output",
            str(out_md),
        ],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert out_json.exists()
    assert out_md.exists()


# ---------------------------------------------------------------------------
# Contract 4 — repayment queue is bounded and deterministic
# ---------------------------------------------------------------------------


def test_repayment_queue_bounded_by_ten(st: ModuleType) -> None:
    report = st.collect()
    assert len(report.next_repayment_prs) <= 10


def test_repayment_queue_is_deterministic(st: ModuleType) -> None:
    a = st.collect().next_repayment_prs
    b = st.collect().next_repayment_prs
    assert a == b

"""Tests for the research-line registry and fail-closed policy.

Minimum enforcement per the fail-closure protocol:
  - combo_v1_fx_wave1 is marked REJECTED.
  - Same-family + same-substrate continuation is blocked at the
    validator layer.
  - allowed_next_action for the rejected line is
    'new_fx_native_prereg_only'.
  - Any REJECTED line has coherent fail-closed flags (wave2_authorized
    == false, parameter_rescue_allowed == false, same_family_same_
    substrate_retest_allowed == false).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "config" / "research_line_registry.yaml"


from scripts.registry_validator import (  # noqa: E402
    LineClosedError,
    assert_rejected_line_invariants,
    check_family_substrate_allowed,
    get_line,
    load_registry,
)


@pytest.fixture(scope="module")
def registry() -> dict:
    return load_registry(REGISTRY_PATH)


def test_registry_file_exists() -> None:
    assert REGISTRY_PATH.is_file(), f"registry missing: {REGISTRY_PATH}"


def test_combo_v1_fx_wave1_rejected(registry: dict) -> None:
    line = get_line(registry, "combo_v1_fx_wave1")
    assert line.status == "REJECTED"
    assert line.verdict == "FAIL"


def test_combo_v1_fx_wave1_flags_coherent(registry: dict) -> None:
    line = get_line(registry, "combo_v1_fx_wave1")
    # The three fail-closed flags
    assert line.wave2_authorized is False
    assert line.parameter_rescue_allowed is False
    assert line.same_family_same_substrate_retest_allowed is False


def test_combo_v1_fx_wave1_allowed_next_action(registry: dict) -> None:
    line = get_line(registry, "combo_v1_fx_wave1")
    assert line.allowed_next_action == "new_fx_native_prereg_only"


def test_allowed_next_action_is_in_registry_vocabulary(registry: dict) -> None:
    """Every line's allowed_next_action must be in the registry's declared vocabulary."""
    vocab = set(registry.get("allowed_next_actions", []))
    assert vocab, "registry has no allowed_next_actions vocabulary declared"
    for line_id in registry.get("lines", {}):
        line = get_line(registry, line_id)
        assert line.allowed_next_action in vocab, (
            f"line {line_id!r} has allowed_next_action={line.allowed_next_action!r} "
            f"which is not in vocabulary {sorted(vocab)!r}"
        )


def test_all_rejected_lines_have_coherent_flags(registry: dict) -> None:
    for line_id in registry.get("lines", {}):
        line = get_line(registry, line_id)
        assert_rejected_line_invariants(line)


def test_same_family_same_substrate_is_blocked(registry: dict) -> None:
    with pytest.raises(LineClosedError) as excinfo:
        check_family_substrate_allowed(
            registry,
            signal_family="combo_v1",
            substrate="8fx_daily_close_2100utc",
        )
    msg = str(excinfo.value)
    assert "combo_v1_fx_wave1" in msg
    assert "REJECTED" in msg
    assert "new_fx_native_prereg_only" in msg


def test_different_family_same_substrate_not_blocked(registry: dict) -> None:
    check_family_substrate_allowed(
        registry,
        signal_family="some_new_fx_native_signal",
        substrate="8fx_daily_close_2100utc",
    )


def test_same_family_different_substrate_not_blocked(registry: dict) -> None:
    check_family_substrate_allowed(
        registry,
        signal_family="combo_v1",
        substrate="equity_gold_3node_hourly",
    )


def test_locked_sha_fields_present(registry: dict) -> None:
    """Audit trail requires SHA-stamping for every REJECTED line."""
    line = get_line(registry, "combo_v1_fx_wave1")
    assert line.lock_sha and len(line.lock_sha) == 40
    assert line.complete_sha and len(line.complete_sha) == 40


def test_cli_blocks_same_family_substrate() -> None:
    """CLI `--check-pair` must exit non-zero for a rejected pair."""
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "registry_validator.py"),
            "--registry",
            str(REGISTRY_PATH),
            "--check-pair",
            "combo_v1",
            "8fx_daily_close_2100utc",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 2, (
        f"expected exit code 2 (blocked), got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "BLOCKED" in proc.stdout
    assert "combo_v1_fx_wave1" in proc.stdout


def test_cli_passes_open_pair() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "registry_validator.py"),
            "--registry",
            str(REGISTRY_PATH),
            "--check-pair",
            "new_fx_native_signal",
            "8fx_daily_close_2100utc",
        ],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert proc.returncode == 0, (
        f"expected exit code 0 (OK), got {proc.returncode}\n"
        f"stdout: {proc.stdout}\nstderr: {proc.stderr}"
    )
    assert "OK" in proc.stdout

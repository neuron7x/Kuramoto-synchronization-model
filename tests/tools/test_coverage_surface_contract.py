from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.coverage.surface_contract import (
    is_colocated_test_file,
    list_unmapped_files,
    load_coverage_targets,
    map_file_to_surface,
    validate_target_contract,
)


def _write_targets(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


VALID_TOML = """
[global]
final_aspirational_gate = 98
current_release_gate = 90
diff_coverage_gate = 90

[surfaces.core]
paths = ["core/"]
short_term = 80
mid_term = 90
final = 95
claim_risk = "high"
rationale = "core rationale"

[surfaces.backtest]
paths = ["backtest/"]
short_term = 90
mid_term = 95
final = 98
claim_risk = "critical"
rationale = "backtest rationale"

[surfaces.execution]
paths = ["execution/"]
short_term = 80
mid_term = 90
final = 95
claim_risk = "critical"
rationale = "execution rationale"
""".strip()


def test_valid_coverage_targets_passes(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", VALID_TOML))
    assert validate_target_contract(targets) == []


def test_missing_global_threshold_fails(tmp_path: Path) -> None:
    bad = VALID_TOML.replace("diff_coverage_gate = 90\n", "")
    try:
        load_coverage_targets(_write_targets(tmp_path / "bad.toml", bad))
    except ValueError as exc:
        assert "Missing global threshold" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_invalid_threshold_order_fails(tmp_path: Path) -> None:
    bad = VALID_TOML.replace("short_term = 80", "short_term = 96", 1)
    targets = load_coverage_targets(_write_targets(tmp_path / "bad.toml", bad))
    errors = validate_target_contract(targets)
    assert any("threshold order invalid" in e for e in errors)


def test_threshold_outside_range_fails(tmp_path: Path) -> None:
    bad = VALID_TOML.replace("final = 98", "final = 101", 1)
    targets = load_coverage_targets(_write_targets(tmp_path / "bad.toml", bad))
    errors = validate_target_contract(targets)
    assert any("out of range" in e for e in errors)


def test_missing_rationale_fails(tmp_path: Path) -> None:
    bad = VALID_TOML.replace('rationale = "core rationale"', 'rationale = ""')
    targets = load_coverage_targets(_write_targets(tmp_path / "bad.toml", bad))
    errors = validate_target_contract(targets)
    assert any("missing rationale" in e for e in errors)


def test_known_core_file_maps_to_core(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", VALID_TOML))
    assert map_file_to_surface("core/engine/core.py", targets) == "core"


def test_known_backtest_file_maps_to_backtest(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", VALID_TOML))
    assert map_file_to_surface("backtest/engine.py", targets) == "backtest"


def test_known_execution_file_maps_to_execution(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", VALID_TOML))
    assert map_file_to_surface("execution/oms.py", targets) == "execution"


def test_unknown_file_returns_none(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", VALID_TOML))
    assert map_file_to_surface("docs/readme.md", targets) is None
    assert list_unmapped_files(["docs/readme.md"], targets) == ["docs/readme.md"]


def test_cli_exits_0_for_valid_contract(tmp_path: Path) -> None:
    target_path = _write_targets(tmp_path / "targets.toml", VALID_TOML)
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.coverage.validate_coverage_targets",
            "--targets",
            str(target_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr


def test_cli_exits_1_for_invalid_contract(tmp_path: Path) -> None:
    bad = VALID_TOML.replace("mid_term = 90", "mid_term = -1", 1)
    target_path = _write_targets(tmp_path / "bad.toml", bad)
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.coverage.validate_coverage_targets",
            "--targets",
            str(target_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 1


def test_json_output_written_when_requested(tmp_path: Path) -> None:
    target_path = _write_targets(tmp_path / "targets.toml", VALID_TOML)
    files_path = tmp_path / "files.txt"
    files_path.write_text("core/a.py\ndocs/a.md\n", encoding="utf-8")
    out_path = tmp_path / "result.json"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.coverage.validate_coverage_targets",
            "--targets",
            str(target_path),
            "--files",
            str(files_path),
            "--json-out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["status"] == "pass"


def test_weights_must_sum_to_one(tmp_path: Path) -> None:
    bad = VALID_TOML + "\n\n[weights]\ndivergence = 0.7\nconvergence = 0.4\n"
    targets = load_coverage_targets(_write_targets(tmp_path / "bad_weights.toml", bad))
    errors = validate_target_contract(targets)
    assert any("weights must sum to 1.0" in e for e in errors)


def test_cli_json_includes_weights(tmp_path: Path) -> None:
    weighted = VALID_TOML + "\n\n[weights]\ndivergence = 0.5\nconvergence = 0.5\n"
    target_path = _write_targets(tmp_path / "targets_weighted.toml", weighted)
    out_path = tmp_path / "result_weights.json"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.coverage.validate_coverage_targets",
            "--targets",
            str(target_path),
            "--json-out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["weights"] == {"divergence": 0.5, "convergence": 0.5}


def test_most_specific_surface_prefix_wins(tmp_path: Path) -> None:
    toml = VALID_TOML + "\n\n" + """

[surfaces.risk]
paths = ["risk/", "execution/risk", "core/risk"]
short_term = 90
mid_term = 95
final = 98
claim_risk = "critical"
rationale = "risk rationale"
""".strip()

    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", toml))

    assert map_file_to_surface("core/risk/limits.py", targets) == "risk"
    assert map_file_to_surface("execution/risk/limits.py", targets) == "risk"
    assert map_file_to_surface("risk/limits.py", targets) == "risk"


def test_prefix_matching_is_path_boundary_safe(tmp_path: Path) -> None:
    toml = VALID_TOML + "\n\n" + """

[surfaces.risk]
paths = ["execution/risk"]
short_term = 90
mid_term = 95
final = 98
claim_risk = "critical"
rationale = "risk rationale"
""".strip()

    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", toml))

    assert map_file_to_surface("execution/risk/limits.py", targets) == "risk"
    assert map_file_to_surface("execution/risky.py", targets) == "execution"


def test_windows_style_path_maps_to_surface(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", VALID_TOML))
    assert map_file_to_surface(r"core\engine\core.py", targets) == "core"


def test_relative_dot_prefix_maps_to_surface(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", VALID_TOML))
    assert map_file_to_surface("./execution/oms.py", targets) == "execution"


def test_noncritical_prefix_boundary_does_not_match(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", VALID_TOML))
    assert map_file_to_surface("corex/file.py", targets) is None


def test_specificity_wins_with_trailing_slash_prefixes(tmp_path: Path) -> None:
    toml = VALID_TOML + "\n\n" + """

[surfaces.risk]
paths = ["core/risk/", "execution/risk/"]
short_term = 90
mid_term = 95
final = 98
claim_risk = "critical"
rationale = "risk rationale"
""".strip()
    targets = load_coverage_targets(_write_targets(tmp_path / "targets.toml", toml))
    assert map_file_to_surface("core/risk/limits.py", targets) == "risk"


def test_cli_missing_files_input_returns_structured_error(tmp_path: Path) -> None:
    target_path = _write_targets(tmp_path / "targets.toml", VALID_TOML)
    out_path = tmp_path / "result_missing_files.json"

    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.coverage.validate_coverage_targets",
            "--targets",
            str(target_path),
            "--files",
            str(tmp_path / "does_not_exist.txt"),
            "--json-out",
            str(out_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert run.returncode == 1
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fail"
    assert payload["errors"]


def test_cli_missing_files_input_includes_path_in_error(tmp_path: Path) -> None:
    target_path = _write_targets(tmp_path / "targets.toml", VALID_TOML)
    missing = tmp_path / "does_not_exist.txt"
    run = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.coverage.validate_coverage_targets",
            "--targets",
            str(target_path),
            "--files",
            str(missing),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 1
    assert str(missing) in (run.stdout + run.stderr)


# --------------------------------------------------------------------------- #
# Co-located test files must NOT count as production surface (anti self-inflation)
# --------------------------------------------------------------------------- #
def test_colocated_test_file_is_detected() -> None:
    assert is_colocated_test_file("core/neuro/tests/test_engine.py")
    assert is_colocated_test_file("analytics/signals/tests/test_igs_core.py")
    assert is_colocated_test_file("analytics/tests/__init__.py")
    assert is_colocated_test_file("markets/orderbook/tests/conftest.py")
    assert is_colocated_test_file("geosync/neural_controller/tests/foo_test.py")


def test_production_module_with_test_substring_is_not_colocated_test() -> None:
    # Genuine production modules that merely contain "test" must NOT be excluded.
    assert not is_colocated_test_file("core/engine/backtest_runner.py")
    assert not is_colocated_test_file("analytics/signals/test_harness.py")  # not under tests/
    assert not is_colocated_test_file("core/tests_helpers/util.py")  # dir != "tests"


def test_colocated_test_body_not_counted_as_production_surface(tmp_path: Path) -> None:
    """A co-located test FILE under a source root must map to no surface.

    Without this, the longest-prefix bucketing would credit
    ``core/neuro/tests/test_engine.py`` (a test body) to the ``core`` surface,
    self-inflating measured release coverage with test-on-test lines.
    """
    targets = load_coverage_targets(_write_targets(tmp_path / "t.toml", VALID_TOML))
    # Production module under core/ still maps.
    assert map_file_to_surface("core/neuro/engine.py", targets) == "core"
    # Co-located test bodies under the SAME source root do not.
    assert map_file_to_surface("core/neuro/tests/test_engine.py", targets) is None
    assert map_file_to_surface("core/neuro/tests/__init__.py", targets) is None
    assert map_file_to_surface("execution/tests/test_oms.py", targets) is None


def test_colocated_test_files_listed_as_unmapped(tmp_path: Path) -> None:
    targets = load_coverage_targets(_write_targets(tmp_path / "t.toml", VALID_TOML))
    paths = [
        "core/neuro/engine.py",
        "core/neuro/tests/test_engine.py",
        "execution/oms.py",
    ]
    unmapped = list_unmapped_files(paths, targets)
    assert "core/neuro/tests/test_engine.py" in unmapped
    assert "core/neuro/engine.py" not in unmapped
    assert "execution/oms.py" not in unmapped

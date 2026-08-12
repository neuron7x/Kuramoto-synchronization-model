# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Closure tests for the RES-005 physics-score de-hyping gate.

The GeoSync "physics score" is an INTERNAL READINESS RUBRIC, not scientific
validation; ``88-92`` is a self-set readiness threshold. These tests assert the
gate ``scripts/ci/check_physics_score.py`` fails closed on any surface that
markets the score/band as scientific validation, and that the RES-005 artifacts
carry component traceability + a reported weight-sensitivity + the relabel
verdict.

POSITIVE controls (exit 0):
  * real methodology doc + calibration artifact satisfy the readiness contract
  * scanning the methodology doc (which negates the validation claim) is clean

NEGATIVE controls (exit 1, RED):
  * "physics score 90 = scientifically validated" -> flagged
  * calibration artifact with weight_sensitivity removed -> flagged (missing sensitivity)
  * calibration artifact with verdict flipped to a validation claim -> flagged
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATE = ROOT / "scripts/ci/check_physics_score.py"
METHODOLOGY = ROOT / "docs/physics_score_methodology.md"
CALIBRATION = ROOT / "artifacts/research/physics_score_calibration.json"

EXIT_OK = 0
EXIT_FLAGGED = 1


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


# --------------------------------------------------------------------------- #
# Artifacts exist and are well-formed
# --------------------------------------------------------------------------- #
def test_artifacts_exist() -> None:
    assert METHODOLOGY.exists(), "methodology doc must exist"
    assert CALIBRATION.exists(), "calibration artifact must exist"


def test_calibration_is_valid_json_with_components_and_sensitivity() -> None:
    data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    assert data["verdict"] == "INTERNAL_READINESS_RUBRIC_NOT_VALIDATION"
    assert isinstance(data["components"], list) and len(data["components"]) == 10
    assert "weight_sensitivity" in data and data["weight_sensitivity"]
    # sensitivity must actually be reported with numbers
    sens = data["weight_sensitivity"]
    assert isinstance(sens["monte_carlo_stdev"], (int, float))
    assert sens["fraction_of_random_weightings_landing_in_target_band_88_92"] == 0.0
    # no external criterion is the honest state
    assert data["external_criterion"] is None


def test_components_are_traceable_to_the_scoring_tool() -> None:
    data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    for c in data["components"]:
        for field in ("id", "weight", "score", "measurement_fn", "kind"):
            assert field in c, f"component {c.get('id')} missing {field}"
        # honest classification: no component is a ground-truth measurement
        assert c["is_continuous_measurement_against_ground_truth"] is False


# --------------------------------------------------------------------------- #
# POSITIVE controls
# --------------------------------------------------------------------------- #
def test_positive_validate_artifacts_passes() -> None:
    res = _run("--validate-artifacts")
    assert res.returncode == EXIT_OK, res.stdout + res.stderr
    assert json.loads(res.stdout)["status"] == "PASS"


def test_positive_scanning_methodology_doc_is_clean() -> None:
    # the doc says the score is NOT validation; negation cues clear it
    res = _run("--scan-file", "docs/physics_score_methodology.md")
    assert res.returncode == EXIT_OK, res.stdout + res.stderr
    assert json.loads(res.stdout)["status"] == "PASS"


def test_positive_validation_word_with_measured_class_clears() -> None:
    # a validation word is admissible only if MEASURED/FACT is declared
    res = _run(
        "--scan-text",
        "physics score 90 is validated",
        "--evidence-class",
        "MEASURED",
    )
    assert res.returncode == EXIT_OK, res.stdout + res.stderr


# --------------------------------------------------------------------------- #
# NEGATIVE controls (each MUST fail closed)
# --------------------------------------------------------------------------- #
def test_negative_score_marketed_as_scientific_validation_is_red() -> None:
    res = _run("--scan-text", "physics score 90 = scientifically validated")
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr
    report = json.loads(res.stdout)
    assert report["status"] == "FLAGGED"
    assert any(v["claim_word"] == "validated" for v in report["violations"])


def test_negative_band_marketed_as_proven_is_red() -> None:
    res = _run("--scan-text", "GeoSync 88-92 physics score is proven")
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr


def test_negative_validation_word_with_simulation_class_stays_red() -> None:
    # SIMULATION can back NO validation word -> firewall contradiction
    res = _run(
        "--scan-text",
        "physics score 90 is validated",
        "--evidence-class",
        "SIMULATION",
    )
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr


def test_negative_missing_sensitivity_is_red(tmp_path: Path) -> None:
    data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    data.pop("weight_sensitivity", None)
    broken = tmp_path / "no_sensitivity.json"
    broken.write_text(json.dumps(data), encoding="utf-8")
    res = _run("--validate-artifacts", "--calibration", str(broken))
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr
    problems = json.loads(res.stdout)["problems"]
    assert any("sensitivity" in p.lower() for p in problems)


def test_negative_verdict_flipped_to_validation_is_red(tmp_path: Path) -> None:
    data = json.loads(CALIBRATION.read_text(encoding="utf-8"))
    data["verdict"] = "SCIENTIFICALLY_VALIDATED"
    broken = tmp_path / "flipped_verdict.json"
    broken.write_text(json.dumps(data), encoding="utf-8")
    res = _run("--validate-artifacts", "--calibration", str(broken))
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr


def test_negative_methodology_without_relabel_is_red(tmp_path: Path) -> None:
    fake = tmp_path / "hyped_methodology.md"
    fake.write_text(
        "# Physics Score\n\nThe physics score 90 scientifically validates GeoSync.\n",
        encoding="utf-8",
    )
    res = _run("--validate-artifacts", "--methodology", str(fake))
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr
    problems = json.loads(res.stdout)["problems"]
    assert any("relabel marker" in p for p in problems)


# --------------------------------------------------------------------------- #
# Destroyer regressions: DS-03 (negation disarm scope), DS-04 (validation stem),
# DS-02 (homoglyph evasion) on the physics-score scan gate.
# --------------------------------------------------------------------------- #
def test_ds03_incidental_negation_after_word_still_flags() -> None:
    # A negation word that does NOT attach to "validated" must not disarm it.
    for hype in (
        "physics score 90 is validated, not overfit",
        "physics score 90 is validated for non-linear regimes",
        "physics score 90 is validated; no caveats remain",
    ):
        res = _run("--scan-text", hype)
        assert res.returncode == EXIT_FLAGGED, hype + "\n" + res.stdout + res.stderr
        report = json.loads(res.stdout)
        assert any(v["claim_word"] == "validated" for v in report["violations"]), hype


def test_ds03_genuine_negation_before_word_passes() -> None:
    # A negation directly negating the claim IS a disclaimer -> clean.
    for negated in (
        "physics score 90 is not validated",
        "physics score 90 is not scientifically validated",
    ):
        res = _run("--scan-text", negated)
        assert res.returncode == EXIT_OK, negated + "\n" + res.stdout + res.stderr


def test_ds04_present_tense_validates_flags() -> None:
    res = _run("--scan-text", "the physics score validates the market model")
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr
    assert json.loads(res.stdout)["status"] == "FLAGGED"


def test_ds04_uppercase_validates_still_flags() -> None:
    res = _run("--scan-text", "THE PHYSICS SCORE VALIDATES THE MARKET MODEL")
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr


def test_ds02_homoglyph_validated_is_caught() -> None:
    # Cyrillic 'а' (U+0430) in place of Latin 'a' must not evade the pattern.
    res = _run("--scan-text", "physics score 90 is vаlidаted")
    assert res.returncode == EXIT_FLAGGED, res.stdout + res.stderr
    assert any(v["claim_word"] == "validated" for v in json.loads(res.stdout)["violations"])


# --------------------------------------------------------------------------- #
# DS-03/DS-02 round-2 — intensifier-negation + combining/Greek homoglyph       #
# --------------------------------------------------------------------------- #
import pytest as _pytest  # noqa: E402


@_pytest.mark.parametrize(
    "text",
    [
        "physics score 90 is not merely validated",
        "physics score 90 is not only validated",
        "physics score 90 is not just validated",
        "physics score 90 is validaτed",  # Greek tau homoglyph for t
        "physics score 90 is validáted",  # combining acute over a
    ],
)
def test_ds03r2_and_ds02r2_evasions_now_flag(text: str) -> None:
    # affirming-intensifier negations and Greek/combining homoglyphs must FLAG
    assert _run("--scan-text", text).returncode == EXIT_FLAGGED


@_pytest.mark.parametrize(
    "text",
    [
        "physics score 90 is not validated",
        "physics score 90 has not been fully validated",
        "physics score 90 was never validated",
    ],
)
def test_ds03r2_genuine_negation_still_clears(text: str) -> None:
    # a real disclaiming negation of the validation claim must NOT flag
    assert _run("--scan-text", text).returncode == EXIT_OK

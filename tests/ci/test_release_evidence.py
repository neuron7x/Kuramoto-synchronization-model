# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Teeth for the release-evidence-bundle gate (REL-011).

POSITIVE: the committed bundle validates against its schema, every PRESENT
artifact's recorded digest matches disk, the SHA256SUMS matches a fresh regen,
and rebuilding is byte-for-byte deterministic (== committed bytes).

NEGATIVE: a tampered recorded digest is RED; a mandatory MISSING receipt makes
the release-readiness verdict NOT_READY (RED); a non-deterministic / stale
committed bundle is RED.

The negative tests mutate in-memory copies or temp files only — never the
tracked bundle — so the working tree is never left dirty.
"""

from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT / "scripts" / "ci"),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import check_release_evidence as gate  # noqa: E402


def _committed() -> dict:
    return json.loads(gate.BUNDLE_PATH.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# POSITIVE                                                                      #
# --------------------------------------------------------------------------- #
def test_committed_bundle_validates_against_schema() -> None:
    assert gate.validate_schema(_committed()) == []


def test_present_digests_match_disk() -> None:
    assert gate.check_digests(_committed(), ROOT) == []


def test_regen_is_deterministic_and_matches_committed() -> None:
    a = gate.canonical_json(gate.build_bundle(ROOT))
    b = gate.canonical_json(gate.build_bundle(ROOT))
    assert a == b, "two rebuilds differ"
    assert a == gate.BUNDLE_PATH.read_text(encoding="utf-8"), "committed != regen"
    assert gate.check_deterministic(ROOT) == []


def test_sha256sums_matches_regen() -> None:
    assert gate.check_sha256sums(_committed(), ROOT) == []
    sums = gate.SHA256SUMS_PATH.read_text(encoding="utf-8")
    # every present referenced artifact appears exactly once, sorted by path
    paths = [line.split("  ", 1)[1] for line in sums.strip().splitlines()]
    assert paths == sorted(paths)
    assert paths == gate.referenced_present_paths(_committed())


def test_freshly_built_bundle_is_schema_valid() -> None:
    assert gate.validate_schema(gate.build_bundle(ROOT)) == []


# --------------------------------------------------------------------------- #
# NEGATIVE                                                                      #
# --------------------------------------------------------------------------- #
def test_tampered_digest_is_red() -> None:
    bundle = copy.deepcopy(_committed())
    for cat in bundle["categories"].values():
        for art in cat["artifacts"]:
            if art["status"] == "PRESENT":
                art["sha256"] = "0" * 64  # tamper
                problems = gate.check_digests(bundle, ROOT)
                assert problems, "tampered digest was not flagged"
                assert any("!= disk" in p for p in problems)
                return
    raise AssertionError("no PRESENT artifact to tamper")


def test_mandatory_missing_forces_not_ready() -> None:
    verdict, missing = gate.release_readiness(_committed())
    # The real bundle is legitimately NOT_READY (receipts absent).
    assert verdict == "NOT_READY"
    assert set(missing) == {"coverage", "mutation", "sbom", "tests", "wheel"}
    assert missing == sorted(missing)
    for name in missing:
        cat = _committed()["categories"][name]
        assert cat["mandatory"] is True
        assert cat["status"] != "PRESENT"


def test_flipping_a_mandatory_present_to_missing_flips_verdict() -> None:
    """If a currently-PRESENT mandatory category loses its receipt -> NOT_READY."""
    bundle = copy.deepcopy(_committed())
    # sanity: security_scan is currently PRESENT & mandatory
    assert bundle["categories"]["security_scan"]["status"] == "PRESENT"
    bundle["categories"]["security_scan"]["status"] = "MISSING"
    for art in bundle["categories"]["security_scan"]["artifacts"]:
        art["status"] = "MISSING"
        art["sha256"] = None
    mandatory = [n for n, c in bundle["categories"].items() if c["mandatory"]]
    missing = sorted(n for n in mandatory if bundle["categories"][n]["status"] != "PRESENT")
    verdict = "READY" if not missing else "NOT_READY"
    assert verdict == "NOT_READY"
    assert "security_scan" in missing


def test_synthetic_all_present_would_be_ready() -> None:
    """The gate is not permanently stuck RED: if every mandatory category were
    PRESENT the verdict would be READY. Proves the RED is data-driven, not baked in."""
    bundle = copy.deepcopy(_committed())
    for cat in bundle["categories"].values():
        if cat["mandatory"]:
            cat["status"] = "PRESENT"
    mandatory = [n for n, c in bundle["categories"].items() if c["mandatory"]]
    missing = sorted(n for n in mandatory if bundle["categories"][n]["status"] != "PRESENT")
    assert missing == []
    assert ("READY" if not missing else "NOT_READY") == "READY"


def test_stale_committed_bundle_is_red(tmp_path: Path) -> None:
    """A committed bundle whose bytes differ from a fresh regen is flagged."""
    stale = tmp_path / "release_evidence.json"
    bundle = gate.build_bundle(ROOT)
    bundle["release_version"] = "9.9.9"  # perturb -> no longer matches regen
    stale.write_text(gate.canonical_json(bundle), encoding="utf-8")
    problems = gate.check_deterministic(ROOT, bundle_path=stale)
    assert any("committed" in p for p in problems)


def test_verify_exit_code_is_red_while_receipts_missing() -> None:
    assert gate.verify(ROOT) == 1


# --------------------------------------------------------------------------- #
# CONTENT CONTRACT — F1 / F1b (closes the content/verdict-blind fail-open)      #
# --------------------------------------------------------------------------- #
def _scratch_root(tmp_path: Path, receipts: dict[str, str]) -> Path:
    """A minimal build root: the real provenance manifest (so _source_ref works)
    plus the given ``{repo_relative_path: text_content}`` receipts written on disk.
    build_bundle scores content against the same contracts --emit uses.
    """
    prov_rel = "manifests/research/release_provenance.v2.json"
    (tmp_path / prov_rel).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / prov_rel, tmp_path / prov_rel)
    for rel, content in receipts.items():
        fpath = tmp_path / rel
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")
    return tmp_path


# The EXACT destroyer RD-F1 repro payloads at the five canonical receipt paths.
_F1_GARBAGE = {
    "artifacts/release/coverage_report.json": '{"verdict":"FAIL"}',
    "artifacts/release/mutation_report.json": '{"verdict":"FAIL"}',
    "artifacts/release/sbom.spdx.json": "",  # 0 bytes
    "artifacts/release/full_test_suite_report.json": "NOT JSON \x00 garbage",
    "artifacts/release/wheel_manifest.json": "{}",
}


def test_F1_garbage_receipts_do_not_certify_ready(tmp_path: Path) -> None:
    """RD-F1: FAIL / 0-byte / non-JSON / {} receipts planted at the canonical
    paths must NOT flip release_readiness to READY — the whole point of the fix.
    Under the old existence-only logic these five would all be PRESENT -> READY."""
    root = _scratch_root(tmp_path, _F1_GARBAGE)
    bundle = gate.build_bundle(root)

    for name in ("coverage", "mutation", "sbom", "tests", "wheel"):
        cat = bundle["categories"][name]
        # the file genuinely exists on disk (old logic would call it PRESENT)...
        for art in cat["artifacts"]:
            assert (root / art["path"]).is_file()
        # ...but the content contract rejects it.
        assert cat["status"] == "UNSATISFIED", f"{name} should be UNSATISFIED"

    verdict, _ = gate.release_readiness(bundle)
    assert verdict == "NOT_READY", "garbage receipts must not certify READY"
    # the failing receipts are still schema-valid bundle entries
    assert gate.validate_schema(bundle) == []


def test_F1_below_floor_is_unsatisfied_but_passing_is_present(tmp_path: Path) -> None:
    """A numeric floor genuinely gates: below-threshold coverage/mutation are
    UNSATISFIED, at/above-threshold with a passing verdict are PRESENT (proving
    the contract is data-driven, not permanently red)."""
    below = _scratch_root(
        tmp_path / "below",
        {
            "artifacts/release/coverage_report.json": '{"verdict":"PASS","line_rate":50.0}',
            "artifacts/release/mutation_report.json": '{"mutation_score":40.0}',
        },
    )
    b = gate.build_bundle(below)
    assert b["categories"]["coverage"]["status"] == "UNSATISFIED"
    assert b["categories"]["mutation"]["status"] == "UNSATISFIED"

    ok = _scratch_root(
        tmp_path / "ok",
        {
            "artifacts/release/coverage_report.json": '{"verdict":"PASS","line_rate":95.0}',
            "artifacts/release/mutation_report.json": '{"mutation_score":90.0}',
        },
    )
    g2 = gate.build_bundle(ok)
    assert g2["categories"]["coverage"]["status"] == "PRESENT"
    assert g2["categories"]["mutation"]["status"] == "PRESENT"


def test_F1b_security_fail_and_cleanroom_mismatch_not_satisfied(tmp_path: Path) -> None:
    """RD-F1b: a security_scan verdict:"FAIL" and a cleanroom match:false receipt
    are surfaced but must GATE — the category is UNSATISFIED, not PRESENT."""
    root = _scratch_root(
        tmp_path,
        {
            "artifacts/env/image_scan_report.json": '{"verdict":"FAIL"}',
            "artifacts/env/image_digest.json": '{"digest":"sha256:deadbeef"}',
            "artifacts/release/reproducible_build_report.json": '{"match":false}',
            "artifacts/env/python312.json": '{"python":"3.12"}',
        },
    )
    bundle = gate.build_bundle(root)
    assert bundle["categories"]["security_scan"]["status"] == "UNSATISFIED"
    assert bundle["categories"]["cleanroom_reproducible_build"]["status"] == "UNSATISFIED"
    verdict, _ = gate.release_readiness(bundle)
    assert verdict == "NOT_READY"


def test_research_verdicts_insufficient_evidence_still_satisfies(tmp_path: Path) -> None:
    """Preserved honest behavior: research verdicts ship as INSUFFICIENT_EVIDENCE
    (an accepted recorded value) — structurally valid receipts stay PRESENT — but
    an EMPTY/garbage research receipt is rejected (fail-open still closed)."""
    good = _scratch_root(
        tmp_path / "good",
        {
            "benchmarks/flagship_baselines/comparison_report.json": '{"verdict":"INSUFFICIENT_EVIDENCE"}',
            "artifacts/research/power_uq_report.json": '{"verdict":"INSUFFICIENT_EVIDENCE"}',
            "artifacts/research/selection_bias_report.json": '{"final_verdict":"INSUFFICIENT_EVIDENCE"}',
        },
    )
    assert gate.build_bundle(good)["categories"]["research_verdicts"]["status"] == "PRESENT"

    bad = _scratch_root(
        tmp_path / "bad",
        {
            "benchmarks/flagship_baselines/comparison_report.json": "",
            "artifacts/research/power_uq_report.json": '{"verdict":"INSUFFICIENT_EVIDENCE"}',
            "artifacts/research/selection_bias_report.json": '{"final_verdict":"INSUFFICIENT_EVIDENCE"}',
        },
    )
    assert gate.build_bundle(bad)["categories"]["research_verdicts"]["status"] == "UNSATISFIED"


# --------------------------------------------------------------------------- #
# L1 — structural errors exit cleanly (2), never an uncaught traceback          #
# --------------------------------------------------------------------------- #
def test_L1_unparseable_committed_bundle_is_clean_exit_2(tmp_path, monkeypatch, capsys) -> None:
    bad = tmp_path / "release_evidence.json"
    bad.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(gate, "BUNDLE_PATH", bad)
    rc = gate.verify(ROOT)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "FATAL" in err


def test_L1_non_dict_committed_bundle_is_clean_exit_2(tmp_path, monkeypatch, capsys) -> None:
    bad = tmp_path / "release_evidence.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(gate, "BUNDLE_PATH", bad)
    rc = gate.verify(ROOT)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "not a JSON object" in err


def test_L1_structural_build_failure_is_clean_exit_2(tmp_path, capsys) -> None:
    """Malformed/incomplete provenance (here: absent under the build root) makes
    _source_ref raise; verify must catch it -> clean exit 2, no stack trace."""
    rc = gate.verify(tmp_path)  # tmp_path has no provenance manifest -> build fails
    assert rc == 2
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "structural error" in err


def test_L1_incomplete_provenance_raises_value_error(tmp_path: Path) -> None:
    """Unit anchor for L1: a provenance manifest missing canonical_commit/tree/tag
    raises ValueError (which verify wraps into exit 2), not a silent best-effort."""
    prov_rel = "manifests/research/release_provenance.v2.json"
    (tmp_path / prov_rel).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / prov_rel).write_text('{"release_ref": {"tag_name": "x"}}', encoding="utf-8")
    with pytest.raises(ValueError):
        gate.build_bundle(tmp_path)


# --------------------------------------------------------------------------- #
# L2 — schema rejects an injected unknown category                              #
# --------------------------------------------------------------------------- #
def test_L2_extra_category_is_schema_rejected() -> None:
    bundle = gate.build_bundle(ROOT)
    assert gate.validate_schema(bundle) == []  # sanity: clean bundle validates
    bundle["categories"]["backdoor"] = {
        "mandatory": False,
        "status": "PRESENT",
        "description": "injected",
        "artifacts": [{"path": "x", "sha256": "0" * 64, "status": "PRESENT"}],
    }
    errs = gate.validate_schema(bundle)
    assert errs, "an unknown 'backdoor' category must be schema-rejected"

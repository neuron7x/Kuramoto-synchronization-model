# SPDX-License-Identifier: MIT
"""Tier-0 metadata-only open-data discovery (network isolated here only).

Queries the public DANDI Archive REST API for extracellular-ephys
dandisets and maps coarse metadata to OpenDataCandidate. NO arrays are
downloaded. Coarse metadata can confirm spikes/LFP/size/subjects but
cannot confirm >=2 areas / trial structure / an INDEPENDENT routing
label — those stay None and the pure gate fails closed. Offline mock
mode makes the whole CLI deterministic for unit tests.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from research.ctc_falsify.c_real.open_data.candidate import (
    OpenDataCandidate,
    classify_candidate,
    explain_candidate_blockers,
    terminal_verdict,
)

_PKG = Path(__file__).resolve().parent
SCHEMA_PATH = _PKG / "schema" / "open_data_manifest.schema.json"
MANIFEST_PATH = _PKG / "open_data_candidates.yaml"
# Curated dual-run narrative lives in OPEN_DATA_REPORT.md (hand-authored,
# records the live finding too); --offline writes only this machine view.
REPORT_PATH = _PKG / "OPEN_DATA_RUN_REPORT.md"
AGATE_PATH = _PKG / "evidence" / "a_gate_open_data_binding.json"
_DANDI = "https://api.dandiarchive.org/api"
_BIND_TOOLING = ("pynwb", "dandi", "remfile")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_json(url: str, timeout: float = 15.0) -> dict[str, Any]:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "geosync-ctc-discovery/0"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data: dict[str, Any] = json.load(resp)
    return data


def _binding_tooling_present() -> bool:
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in _BIND_TOOLING)


def _candidate_from_dandiset(ident: str, name: str) -> OpenDataCandidate:
    info = _get_json(f"{_DANDI}/dandisets/{ident}/versions/draft/info/")
    asum = info.get("metadata", {}).get("assetsSummary", {})
    var = {str(v).lower() for v in asum.get("variableMeasured", [])}
    size = asum.get("numberOfBytes")
    subjects = asum.get("numberOfSubjects")
    has_spikes = ("units" in var) or None
    has_lfp = any("electricalseries" in v or "lfp" in v for v in var) or None
    # Coarse metadata cannot establish areas / trials / independent label.
    return OpenDataCandidate(
        dataset_id=f"DANDI:{ident}",
        source="DANDI Archive",
        source_url=f"https://dandiarchive.org/dandiset/{ident}",
        license_or_access_status="public",
        data_format="NWB",
        estimated_size_bytes=int(size) if isinstance(size, int) else None,
        access_method="dandi-api-metadata",
        has_spikes=has_spikes,
        has_lfp=has_lfp,
        has_two_or_more_areas=None,
        has_trials=None,
        has_independent_routing_label=None,
        candidate_routing_label_name=None,
        sessions_count_estimate=None,
        subject_count_estimate=int(subjects) if isinstance(subjects, int) else None,
        access_reproducible=True,
        checked_at_utc=_utc(),
        evidence_urls=(f"{_DANDI}/dandisets/{ident}/versions/draft/info/",),
    )


def discover(query: str = "neuropixels", limit: int = 6) -> list[OpenDataCandidate]:
    """Live metadata-only discovery. Network failure ⇒ [] (fail-closed)."""
    try:
        listing = _get_json(
            f"{_DANDI}/dandisets/?search={query}&page_size={limit}&ordering=-modified"
        )
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return []
    out: list[OpenDataCandidate] = []
    for d in listing.get("results", [])[:limit]:
        ident = str(d.get("identifier", "")).strip()
        if not ident:
            continue
        try:
            out.append(_candidate_from_dandiset(ident, str(d.get("name", ""))))
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
    return sorted(out, key=lambda c: c.dataset_id)


def _offline_fixture() -> list[OpenDataCandidate]:
    """Deterministic mock for CI/offline: shapes mirror real DANDI ecephys
    metadata (spikes/LFP detectable, areas/trials/label NOT)."""
    return [
        OpenDataCandidate(
            dataset_id="DANDI:MOCK0001",
            source="DANDI Archive (offline mock)",
            source_url="https://dandiarchive.org/dandiset/MOCK0001",
            license_or_access_status="public",
            data_format="NWB",
            estimated_size_bytes=120 * 1024**3,
            access_method="dandi-api-metadata",
            has_spikes=True,
            has_lfp=True,
            has_two_or_more_areas=None,
            has_trials=None,
            has_independent_routing_label=None,
            candidate_routing_label_name=None,
            sessions_count_estimate=None,
            subject_count_estimate=12,
            access_reproducible=True,
            checked_at_utc="1970-01-01T00:00:00+00:00",
            evidence_urls=("https://api.dandiarchive.org/api/dandisets/MOCK0001/",),
        )
    ]


def _to_row(c: OpenDataCandidate) -> dict[str, Any]:
    verdict = classify_candidate(c)
    return {
        "dataset_id": c.dataset_id,
        "source": c.source,
        "source_url": c.source_url,
        "license_or_access_status": c.license_or_access_status,
        "data_format": c.data_format,
        "estimated_size_bytes": c.estimated_size_bytes,
        "access_method": c.access_method,
        "has_spikes": c.has_spikes,
        "has_lfp": c.has_lfp,
        "has_two_or_more_areas": c.has_two_or_more_areas,
        "has_trials": c.has_trials,
        "has_independent_routing_label": c.has_independent_routing_label,
        "candidate_routing_label_name": c.candidate_routing_label_name,
        "sessions_count_estimate": c.sessions_count_estimate,
        "subject_count_estimate": c.subject_count_estimate,
        "access_reproducible": c.access_reproducible,
        "checked_at_utc": c.checked_at_utc,
        "evidence_urls": list(c.evidence_urls),
        "admissibility_verdict": verdict,
        "blockers": list(explain_candidate_blockers(c)),
    }


def build_manifest(candidates: list[OpenDataCandidate]) -> dict[str, Any]:
    rows = [_to_row(c) for c in candidates]
    tooling = _binding_tooling_present()
    term = terminal_verdict(
        [r["admissibility_verdict"] for r in rows], binding_tooling_present=tooling
    )
    return {
        "schema_version": 1,
        "binding_tooling_present": tooling,
        "binding_tooling_required": list(_BIND_TOOLING),
        "terminal_verdict": term,
        "candidates": rows,
    }


def _config_hash() -> str:
    h = hashlib.sha256()
    for p in (_PKG / "candidate.py", Path(__file__)):
        h.update(p.read_bytes())
    return h.hexdigest()


def write_artifacts(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.write_text(yaml.safe_dump(manifest, sort_keys=True))
    schema = json.loads(SCHEMA_PATH.read_text())
    from jsonschema import Draft202012Validator

    Draft202012Validator(schema).validate(manifest)

    term = manifest["terminal_verdict"]
    agate = {
        "selected_dataset_id": None,
        "selected_source": None,
        "selected_access_uri": None,
        "can_run_c_real": False,
        "verdict": term,
        "blockers": sorted(
            {b for r in manifest["candidates"] for b in r["blockers"]}
            | (set() if manifest["binding_tooling_present"] else {"binding_tooling_missing"})
        ),
        "binding_tooling_present": manifest["binding_tooling_present"],
        "n_candidates": len(manifest["candidates"]),
        "config_hash": _config_hash(),
    }
    agate["repro_hash"] = hashlib.sha256(
        json.dumps(agate, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    AGATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGATE_PATH.write_text(json.dumps(agate, indent=2, sort_keys=True) + "\n")

    lines = [
        "# C-real Open-Data Acquisition Report",
        "",
        "Tier-0 metadata-only discovery (DANDI REST API). No arrays "
        "downloaded; no CTC-theory claim; fail-closed.",
        "",
        f"- terminal_verdict: **{term}**",
        f"- binding_tooling_present (pynwb/dandi/remfile): {manifest['binding_tooling_present']}",
        f"- candidates: {len(manifest['candidates'])}",
        "",
        "| dataset | spikes | lfp | areas≥2 | trials | indep.label | verdict |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in manifest["candidates"]:
        lines.append(
            f"| {r['dataset_id']} | {r['has_spikes']} | {r['has_lfp']} | "
            f"{r['has_two_or_more_areas']} | {r['has_trials']} | "
            f"{r['has_independent_routing_label']} | {r['admissibility_verdict']} |"
        )
    lines += [
        "",
        "## Honest limitation",
        "",
        "Coarse archive metadata confirms spikes/LFP/size/subjects but "
        "**cannot** confirm ≥2 areas, trial structure, or an INDEPENDENT "
        "routing label (attention/opto/microstim). The frozen C-real "
        "prereg makes the independent label mandatory; it is never "
        "metadata-inferable, so every metadata-only candidate stays "
        "`UNKNOWN_NEEDS_MANUAL_REVIEW` and the stage fails closed. This is "
        "the designed outcome, not a defect.",
        "",
        "## Next action (only on explicit user vector)",
        "",
        "Per-asset NWB introspection (needs pynwb/dandi/remfile + a "
        "specific dandiset whose docs declare an experimental ON/OFF "
        "manipulation), or a user-provided local paired dataset path.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="C-real open-data Tier-0 discovery")
    ap.add_argument("--metadata-only", action="store_true", default=True)
    ap.add_argument("--offline", action="store_true", help="deterministic mock, no network")
    ap.add_argument("--query", default="neuropixels")
    ns = ap.parse_args(argv)
    cands = _offline_fixture() if ns.offline else discover(ns.query)
    manifest = build_manifest(cands)
    write_artifacts(manifest)
    print(f"TERMINAL_VERDICT: {manifest['terminal_verdict']}")
    print(f"candidates={len(cands)} tooling={manifest['binding_tooling_present']}")
    print(f"manifest={MANIFEST_PATH}")
    print(f"a_gate={AGATE_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

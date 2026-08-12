#!/usr/bin/env python3
# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Q.replication — reviewer packet + hash-locked expected outputs.

Tribunal for the gate ``Q.replication``. A result a third party cannot
reproduce is hearsay. This probe emits a reviewer packet (exact install +
replay commands, cold-rerun instructions, failure interpretation) and a
hash-locked ``expected_hashes.json`` that pins the *reproducible projection*
of every proof artifact.

A projection deliberately excludes non-deterministic fields (temp install
paths, wall-clock latency, machine fingerprints) and keeps only the fields a
clean re-run must reproduce bit-for-bit: control verdicts, kernel result
hashes, scope declarations, schema tiers. ``--verify`` recomputes each
projection from the current artifacts and compares it to the committed
``expected_hashes.json``; any drift is RED.

Output: ``artifacts/replication/REVIEWER_PACKET.md`` and
``artifacts/replication/expected_hashes.json``. Exit 0 iff every projection
matches (verify) or the packet was written (generate).
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Callable

from scripts.ci.proof_common import ROOT, canonical_sha256, write_artifact

PACKET = "artifacts/replication/REVIEWER_PACKET.md"
EXPECTED = "artifacts/replication/expected_hashes.json"


def _load(rel: str) -> dict[str, Any] | None:
    path = ROOT / rel
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # unreadable artifact ⇒ no projection (fail-closed)
        return None


# --- reproducible projections (deterministic subset of each artifact) -------
def _proj_clean_clone(a: dict[str, Any]) -> dict[str, Any]:
    stages = {s["stage"]: bool(s["ok"]) for s in a.get("stages", [])}
    wheel = next((s for s in a.get("stages", []) if s["stage"] == "wheel_contents"), {})
    return {
        "status": a.get("status"),
        "stages_ok": stages,
        "non_geosync": sorted(wheel.get("non_geosync_packages", [])),
    }


def _proj_falsification(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "promotion_allowed": a.get("promotion_allowed"),
        "verdicts": {c["name"]: c["verdict"] for c in a.get("controls", [])},
        "output_hashes": {c["name"]: c["output_sha256"] for c in a.get("controls", [])},
    }


def _proj_execution(a: dict[str, Any]) -> dict[str, Any]:
    return {
        "scope": a.get("scope"),
        "status": a.get("status"),
        "excluded_dimensions": sorted(a.get("excluded_dimensions", [])),
    }


def _proj_benchmark(a: dict[str, Any]) -> dict[str, Any]:
    # kernel result hash is hardware-independent and reproducible; latency is not
    return {"result_hashes": {k: v.get("result_hash") for k, v in a.get("cases", {}).items()}}


def _proj_real_data(a: dict[str, Any]) -> dict[str, Any]:
    return {"status": a.get("status"), "required_fields": sorted(a.get("required_fields", []))}


PROJECTIONS: dict[str, tuple[str, Callable[[dict[str, Any]], dict[str, Any]]]] = {
    "E.clean_clone": ("artifacts/release_gate/clean_clone.json", _proj_clean_clone),
    "H.falsification": ("artifacts/falsification/ledger.json", _proj_falsification),
    "K.execution": ("artifacts/execution/contract.json", _proj_execution),
    "M.benchmarks": ("artifacts/benchmarks/baseline.json", _proj_benchmark),
    "G.real_data": ("artifacts/evidence/real_data_manifest.json", _proj_real_data),
}


def _fingerprints() -> tuple[dict[str, str], list[str]]:
    fps: dict[str, str] = {}
    missing: list[str] = []
    for gate, (rel, proj) in PROJECTIONS.items():
        art = _load(rel)
        if art is None:
            missing.append(gate)
            continue
        fps[gate] = canonical_sha256(proj(art))
    return fps, missing


_INSTALL_CMD = "python -m pip wheel --no-deps -w dist .  &&  pip install dist/geosync-*.whl"
_REPLAY_CMD = (
    "python scripts/ci/release_gate.py --deep --json artifacts/release_gate/scorecard.json"
)


def _render_packet(fps: dict[str, str], expected_sha: str) -> str:
    rows = "\n".join(f"| `{g}` | `{PROJECTIONS[g][0]}` | `{fps[g]}` |" for g in sorted(fps))
    return f"""# GeoSync Reviewer Packet — Replication (Gate Q)

This packet lets an independent reviewer reproduce every proof artifact from a
clean clone and confirm the release verdict. No claim here is prose-only: each
row is hash-locked to a deterministic projection of a machine artifact.

## 1. Exact install (clean clone)

```bash
git clone https://github.com/neuron7xLab/GeoSync.git && cd GeoSync
python -m venv .venv && . .venv/bin/activate
pip install -e .            # or, for the isolated install proof:
{_INSTALL_CMD}
```

## 2. Exact replay (regenerate all artifacts + verdict)

```bash
python scripts/ci/probe_clean_clone.py
python scripts/ci/falsification_ledger.py
python scripts/ci/execution_contract.py
python scripts/ci/benchmark_spine.py            # establishes baseline on first run
python scripts/ci/real_data_probe.py            # exits nonzero while real data is absent
python scripts/ci/replication_packet.py --verify
{_REPLAY_CMD}
```

## 3. Expected hash-locked projections

These fingerprints are over the *reproducible* fields only (verdicts, kernel
result hashes, scope, schema tier). Non-deterministic fields (temp install
paths, wall-clock latency, host fingerprint) are excluded by construction.

| Gate | Artifact | Reproducible fingerprint (sha256) |
|------|----------|-----------------------------------|
{rows}

Aggregate expected-hashes fingerprint: `{expected_sha}`

## 4. Minimal dataset manifest

The deterministic proofs require **no external dataset** — controls run on
seeded synthetic inputs (`seed=20260622/42/7/11`). The **G.real_data** gate is
the only data-dependent gate and is intentionally `BLOCKED`: the repository
ships only synthetic single-session fixtures (`data/sample_ohlc.csv`,
`forbidden_use: not for live trading`). Reproducing a non-BLOCKED G tier
requires staging a real venue session under
`artifacts/evidence/real_data/<id>.json` per the schema in
`scripts/ci/real_data_probe.py`.

## 5. Cold-rerun instructions

1. From a fresh clone (no caches), run section 2 top-to-bottom.
2. `replication_packet.py --verify` must exit 0 — every projection matches.
3. `release_gate.py --deep` prints the scorecard and exits 0 **only** when
   every gating probe is GREEN. While `G.real_data` is BLOCKED the gate is RED
   by design — this is the correct fail-closed state, not a bug.

## 6. Failure interpretation

| Symptom | Meaning |
|---------|---------|
| `verify` reports drift on `H.falsification` | a falsifier verdict changed — a control was REFUTED or the machinery regressed; **do not** promote. |
| `verify` drift on `M.benchmarks` result_hashes | a core kernel became non-deterministic — investigate before any perf claim. |
| `E.clean_clone` status FAIL | wheel no longer builds/installs in isolation, or an entrypoint's own-package wiring broke. |
| `G.real_data` status BLOCKED | expected until real multi-session venue data with license/provenance is staged. |
| `release_gate --deep` exit 1 | at least one gating probe is RED/MANUAL; read the scorecard `results[]`. |

Generated by `scripts/ci/replication_packet.py`. Do not hand-edit — regenerate.
"""


def run_generate() -> dict[str, Any]:
    fps, missing = _fingerprints()
    payload = {
        "gate": "Q.replication",
        "schema_version": "1.0",
        "install_command": _INSTALL_CMD,
        "replay_command": _REPLAY_CMD,
        "fingerprints": fps,
        "missing_artifacts": missing,
    }
    path = write_artifact(EXPECTED, payload)
    written = json.loads(path.read_text(encoding="utf-8"))
    packet = _render_packet(fps, written["artifact_sha256"])
    (ROOT / PACKET).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / PACKET).write_text(packet, encoding="utf-8")
    return {"status": "GENERATED", "fingerprints": fps, "missing": missing}


def run_verify() -> dict[str, Any]:
    expected = _load(EXPECTED)
    if expected is None:
        return {"status": "BLOCKED", "reason": "expected_hashes.json absent — run generate first"}
    current, missing = _fingerprints()
    want = expected.get("fingerprints", {})
    drift = {
        g: {"expected": want.get(g), "actual": current.get(g)}
        for g in PROJECTIONS
        if want.get(g) != current.get(g)
    }
    ok = not drift and not missing
    return {"status": "PASS" if ok else "FAIL", "drift": drift, "missing": missing}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify", action="store_true", help="verify current artifacts against expected_hashes"
    )
    args = parser.parse_args(argv)
    payload = run_verify() if args.verify else run_generate()
    print(
        f"[Q.replication] mode={'verify' if args.verify else 'generate'} status={payload['status']}"
    )
    if payload.get("drift"):
        for g, d in payload["drift"].items():
            print(f"  DRIFT {g}: expected={d['expected']} actual={d['actual']}")
    if payload.get("missing"):
        print(f"  MISSING artifacts: {payload['missing']}")
    return 0 if payload["status"] in ("PASS", "GENERATED") else 1


if __name__ == "__main__":
    raise SystemExit(main())

# Copyright (c) 2023-2026 Yaroslav Vasylenko (neuron7xLab)
# SPDX-License-Identifier: MIT
"""Signed, reproducible provenance for the inference-integrity artifacts.

Product maturity (L5) requires that a verdict is not hand-editable and is
derivable from source. This audit provides both:

* REPRODUCIBLE — every tool-generated artifact is regenerated through its own
  ``main(--out)`` and must be byte-identical to the committed file. A verdict you
  cannot reproduce from source is not a verdict.
* SIGNED (content-addressed) — every inference artifact is sha256-pinned and the
  pins are chained into a single ``provenance_root``. Any edit to any artifact
  changes the root, so tampering is detectable (the release gate recomputes it).

Honest boundary: this is content-addressed, tamper-evident provenance (SLSA/
in-toto style hash chain), not a PKI signature — issuing a KMS-backed signature
over ``provenance_root`` is a deploy-time step, out of repo scope.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

SCHEMA_ID = "geosync.inference_provenance.v1"

# Artifacts regenerated through their generator tool; must be byte-reproducible.
_REGENERATED: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("tools/audit_homeostasis_contract.py", "artifacts/neuro/homeostasis_contract.json", ()),
    ("tools/audit_opponency_lyapunov.py", "artifacts/neuro/opponency_lyapunov.json", ()),
    ("tools/audit_kuramoto_synchrony.py", "artifacts/physics/kuramoto_synchrony.json", ()),
    (
        "tools/audit_no_ungrounded_act.py",
        "artifacts/inference/no_ungrounded_act.json",
        ("--root", "."),
    ),
    (
        "tools/audit_final_inference_verdict.py",
        "artifacts/inference/final_inference_verdict.json",
        ("--root", "."),
    ),
)

# Additional inference-integrity artifacts that are hash-pinned (declarative or
# generated elsewhere) but not regenerated here.
_PINNED_ONLY: tuple[str, ...] = (
    "artifacts/inference/apex_adversarial_report.json",
    "artifacts/inference/apparatus_transfer_report.json",
    "artifacts/state/mutable_state_registry.json",
    "artifacts/concurrency/concurrency_matrix.json",
    "artifacts/time/causal_prefix_matrix.json",
    "artifacts/cache/feature_cache_freshness_matrix.json",
    "artifacts/messaging/event_bus_lifecycle_matrix.json",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _regenerate(tool_rel: str, args: tuple[str, ...], root: Path) -> bytes:
    spec = importlib.util.spec_from_file_location("_prov_tool", root / tool_rel)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError(f"cannot load {tool_rel}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as handle:
        tmp = Path(handle.name)
    try:
        module.main([*args, "--out", str(tmp)])
        return tmp.read_bytes()
    finally:
        tmp.unlink(missing_ok=True)


def build_provenance(root: Path) -> dict[str, Any]:
    """Verify reproducibility and compute the content-addressed provenance root."""

    records: list[dict[str, Any]] = []
    all_reproducible = True

    for tool_rel, artifact_rel, args in _REGENERATED:
        committed = root / artifact_rel
        present = committed.is_file()
        reproducible = False
        digest = ""
        if present:
            digest = _sha256(committed)
            # A generator that cannot run at all is a loud failure, not a silent
            # "non-reproducible" — let it raise so the provenance audit surfaces it.
            regenerated = _regenerate(tool_rel, args, root)
            reproducible = regenerated == committed.read_bytes()
        all_reproducible = all_reproducible and present and reproducible
        records.append(
            {
                "path": artifact_rel,
                "sha256": digest,
                "reproducible": bool(reproducible),
                "generator": tool_rel,
            }
        )

    for artifact_rel in _PINNED_ONLY:
        committed = root / artifact_rel
        present = committed.is_file()
        all_reproducible = all_reproducible and present
        records.append(
            {
                "path": artifact_rel,
                "sha256": _sha256(committed) if present else "",
                "reproducible": None,
                "generator": None,
            }
        )

    records.sort(key=lambda r: r["path"])
    chain = "\n".join(f"{r['path']}\t{r['sha256']}" for r in records)
    provenance_root = hashlib.sha256(chain.encode("utf-8")).hexdigest()
    return {
        "schema": SCHEMA_ID,
        "boundary": (
            "Content-addressed tamper-evident provenance (SLSA/in-toto style hash "
            "chain), not a PKI signature. A KMS-backed signature over provenance_root "
            "is a deploy-time step, out of repo scope."
        ),
        "artifacts": records,
        "provenance_root": provenance_root,
        "verdict": "PASS" if all_reproducible else "FAIL",
    }


def exit_code(report: dict[str, Any], *, report_only: bool) -> int:
    if report["verdict"] == "FAIL" and not report_only:
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Inference-integrity provenance audit")
    p.add_argument("--root", default=".", help="repository root holding the artifacts")
    p.add_argument("--out", help="write the provenance JSON here (else stdout)")
    p.add_argument("--report-only", action="store_true", help="always exit 0, mark report_only")
    args = p.parse_args(argv)

    report = build_provenance(Path(args.root))
    report["report_only"] = bool(args.report_only)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
    else:
        sys.stdout.write(text)
    print(
        f"provenance: {report['verdict']} root={report['provenance_root'][:12]}",
        file=sys.stderr,
    )
    return exit_code(report, report_only=bool(args.report_only))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from geosync.epistemic.rational_certificates import (  # noqa: E402
    iteration_006_certificates,
    verify_rational_certificate,
)

OUT = ROOT / "artifacts/epistemic_control_plane/iteration_006/exact_certificates.json"


def main() -> int:
    rows = []
    for cert in iteration_006_certificates():
        verification = verify_rational_certificate(cert)
        rows.append({"certificate": cert.as_dict(), "verification": verification.as_dict()})
        if not verification.valid:
            raise SystemExit(f"certificate failed: {cert.certificate_id}")
    payload = {
        "schema": "ecp-as-exact-quorum-certificates/v1",
        "iteration": "006",
        "certificates": rows,
        "claim_boundary": (
            "These certificates prove exact extrema for the frozen best Iteration 005 triplet and 2-of-3 quorum. "
            "They do not estimate which compatible joint distribution occurs in deployment."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({r["certificate"]["certificate_id"]: r["verification"]["valid"] for r in rows}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

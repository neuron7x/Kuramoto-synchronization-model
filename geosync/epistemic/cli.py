"""Minimal ECP-AS CLI demonstrator."""
from __future__ import annotations

import argparse
import json
import sys

from .admission import AdmissionController
from .models import Claim, ClaimState


def main() -> int:
    parser = argparse.ArgumentParser(description="ECP-AS epistemic control plane")
    parser.add_argument("--claim-id", default="demo")
    parser.add_argument("--proposition", default="Demonstration claim")
    args = parser.parse_args()

    claim = Claim(args.claim_id, args.proposition, "demo", "demo", ClaimState.UNOBSERVED)
    controller = AdmissionController()
    _, decision = controller.promote(claim, ClaimState.CONJECTURE, ())
    payload = {
        "claim_id": claim.claim_id,
        "allowed": decision.allowed,
        "target": decision.target_state.value,
        "blockers": list(decision.blockers),
    }
    sys.stdout.write(json.dumps(payload, sort_keys=True) + "\n")
    return 0 if decision.allowed else 2


if __name__ == "__main__":
    raise SystemExit(main())

"""Minimal ECP-AS CLI demonstrator."""
from __future__ import annotations
import argparse, json
from .admission import AdmissionController
from .models import Claim, ClaimState

def main() -> int:
    p=argparse.ArgumentParser(description="ECP-AS epistemic control plane")
    p.add_argument("--claim-id",default="demo")
    p.add_argument("--proposition",default="Demonstration claim")
    args=p.parse_args()
    claim=Claim(args.claim_id,args.proposition,"demo","demo",ClaimState.UNOBSERVED)
    ctl=AdmissionController()
    _,d=ctl.promote(claim,ClaimState.CONJECTURE,())
    print(json.dumps({"claim_id":claim.claim_id,"allowed":d.allowed,"target":d.target_state.value,
                      "blockers":list(d.blockers)},sort_keys=True))
    return 0 if d.allowed else 2

if __name__=="__main__": raise SystemExit(main())

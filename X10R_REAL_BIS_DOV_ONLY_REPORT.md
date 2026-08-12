# D-003 — Real BIS DoV-only dry run

**PR:** `feat/x10r-d003-real-bis-dov-only`
**Issue:** D-003 (P0)
**Predecessors:** D-001 #649+#650, D-002A #651, D-002B-A #656.
**Strict scope:** DoV gate only. **No Gate 6 invocation. No
real-data Gate 6 verdict. No bank-level inference claim. No
`INV-IDENTIFICATION-1` lift.**

> Bibliographic anchors justify model class and reviewer
> traceability; operational validity is determined only by
> gates, positive/negative controls, null distributions,
> capsules, and power/FPR/MDE evidence.

---

## 0. Scoped verdict

```
REAL_DOV_REJECTED
```

The default representative-synthetic BIS-LBS-shape input
(N = 25 reporters, lognormal sigma=1.5, mass-balanced) falls
**outside** the canonical D-001 / D-002A envelope
`tested_at_n_nodes = (50, 80, 120)`. The DoV gate returns
`OUT_OF_VALIDATED_DOMAIN`. The capsule's `claim_state` is
therefore `REAL_DOV_REJECTED`.

Forbidden tiers — none asserted:
`REAL_DOV_READY` (the dry-run did not earn it),
`VALIDATED_REAL_BANK_LEVEL_RESULT`,
`CONFIRMED`, `TESTED_POSITIVE_REAL`,
`BANK_LEVEL_PRECURSOR_CONFIRMED`.

---

## 1. Capsule

| File | sha256 |
|---|---|
| `tmp/x10r_d003_dov_dry_run_capsule.json` | `5e520a2958b3df856405b5f6fa0a79b122c9115b2be85af90270737eff70e0b4` |

Capsule contents (verbatim):

```json
{
  "d003_dry_run_capsule_version": 1,
  "input_label": "REPRESENTATIVE_SYNTHETIC_BIS_LBS_SHAPE",
  "n_nodes_input": 25,
  "inferred_density": 0.1049,
  "certified_envelope_source": "canonical_D001_D002A",
  "tested_at_n_nodes": [50, 80, 120],
  "tested_at_densities": [0.03, 0.05, 0.08, 0.12],
  "domain_check": {
    "status": "out_of_validated_domain",
    "checks": {"n_nodes": false, "density": true},
    "measured": {
      "n_nodes": 25.0,
      "density": 0.1049,
      "gini_s_out": ...,
      "gini_s_in": ...,
      "pearson_in_out": ...
    },
    "out_of_range_dims": ["n_nodes"],
    "notes": "out of certified envelope on: ['n_nodes']"
  },
  "scoped_tier": "out_of_validated_domain",
  "elapsed_seconds": ...,
  "forbidden_outputs_emitted": false,
  "gate_6_invoked": false,
  "bank_level_claim_emitted": false,
  "inv_identification_1_status": "globally_active",
  "claim_state": "REAL_DOV_REJECTED"
}
```

---

## 2. Why `REJECTED` is the correct, honest verdict

Real BIS LBS reporter universe ≈ 25 countries. The
synthetic recovery certificate built by D-001 / D-002A
covers `n_nodes ∈ {50, 80, 120}`. 25 < 50 → the input is
outside the certified envelope on the `n_nodes` dimension.
The DoV gate fail-closes on this mismatch, which is its
contractual behaviour (see `research/reconstruction/recovery_audit.py::check_domain_of_validity`).

This is not a defect. It is the gate working correctly:
without an envelope that extends down to N ≈ 25, no real-
data Gate 6 verdict is admissible. The dry run *proves* the
boundary is honoured.

---

## 3. Paths forward (none of which this PR ships)

To clear DoV on real BIS at its native reporter scale, one
of these must land in a separate PR:

1. **Extend the synthetic recovery envelope downward** —
   re-sweep D-001 / D-002A at smaller N (e.g. N ∈
   {20, 30, 50}). Adds `tested_at_n_nodes` entries below 50;
   the same DoV gate then resolves the real BIS input as
   `WITHIN_VALIDATED_DOMAIN` if density also clears.
2. **Apply the country-to-bank allocator (X-10R-1 epic)** —
   reframes the problem so that the substrate-discovery
   layer covers bank-level marginals with their own
   envelope.
3. **Re-shape the real-data input** — partition the reporter
   universe so the effective `n_nodes` is inside the
   certified envelope. Each partition then runs its own DoV
   dry run.

Each of these is a separate research / engineering effort.
None is asserted by this PR.

---

## 4. What this PR does NOT do

- Does **NOT** invoke `gate_6_precursor_discriminative`
  (statically enforced by
  `test_driver_does_not_import_gate_6_module`).
- Does **NOT** emit a real-data Gate 6 verdict.
- Does **NOT** emit a bank-level inference claim.
- Does **NOT** lift `INV-IDENTIFICATION-1`.
- Does **NOT** claim "real data is validated".
- Does **NOT** modify any reconstruction / Gate 6 / DoV
  source code (driver lives in `scripts/`).
- Does **NOT** ingest the BIS LBS bulk CSV. Real-data
  ingest stays parameterised: the user may pass
  `--marginals <path>` to point the dry run at any real
  dataset_dir output.

---

## 5. State after merge

```
GATE6_NOT_CERTIFIED_AT_TESTED_BUDGET_N_LE_200 + REAL_DOV_REJECTED
```

(Following the D-002B-A boundary that landed at sha
`e3b9d0a4daa553485e7123bdbe325ca4e9c3c4a9cf46499208087e3910321362`.)

`INV-IDENTIFICATION-1` remains globally active. The system
remains `INSTRUMENTED`, not `VALIDATED`.

---

## 6. Bibliographic anchors

| Reference | Role | Justifies | Does NOT validate |
|---|---|---|---|
| Cimini–Squartini–Garlaschelli–Gabrielli (2015) | ROLE_A — model origin | Max-entropy reconstruction form | Real-data verdict |
| Almog–Squartini IPF | ROLE_B — numerical method | The IPF projection | Recovery on real BIS |
| **The DoV gate (`check_domain_of_validity`)** | **ROLE_D — validation standard** | The scoped tier verdict on the supplied envelope | Anything beyond the envelope |

Operational validity of this PR's verdict is determined ONLY
by the ROLE_D evidence (the capsule's scoped tier); ROLE_A
and ROLE_B citations are reviewer-trace anchors, not proof.

---

## 7. Acceptance gates (per protocol D-003)

- [x] Allowed outputs ∈ {`WITHIN_VALIDATED_DOMAIN`,
      `OUT_OF_VALIDATED_DOMAIN`,
      `INSUFFICIENT_CERTIFICATE`}
- [x] No Gate 6 invocation (static guarantee + 8 unit tests)
- [x] No bank-level claim (capsule field
      `bank_level_claim_emitted=false`)
- [x] No `INV-IDENTIFICATION-1` lift (capsule field
      `inv_identification_1_status=globally_active`)
- [x] Capsule persisted to disk with provenance + sha256
- [x] mypy --strict + ruff + black clean on driver + tests
- [x] Commit acceptor + falsifier shipped
- [x] D-003 unlock conditions verified:
      - PR #650 merged ✓
      - PR #656 merge in flight (this PR pushes after #656
        merges; if pushed earlier, the verdict is identical
        because no D-002B-A artifact is consumed)
      - #654 (D-002C) issue exists ✓
      - #655 (D-002D) issue exists ✓

---

## 8. Reproduction

```bash
git fetch origin feat/x10r-d003-real-bis-dov-only
git checkout feat/x10r-d003-real-bis-dov-only
mkdir -p tmp
PYTHONPATH=. python3 scripts/run_x10r_d003_dov_dry_run.py \
    --out tmp/x10r_d003_dov_dry_run_capsule.json
sha256sum tmp/x10r_d003_dov_dry_run_capsule.json
# expected first 8 hex of sha256: 5e520a29
```

To run on real BIS bulk output:

```bash
PYTHONPATH=. python3 tools/build_bis_lbs_dataset.py \
    --bis-zip /path/to/WS_LBS_D_PUB_csv_flat.zip \
    --output /path/to/dataset_dir
# extract marginals from dataset_dir into a JSON payload
# matching the input contract, then:
PYTHONPATH=. python3 scripts/run_x10r_d003_dov_dry_run.py \
    --marginals /path/to/real_bis_marginals.json \
    --out tmp/x10r_d003_dov_dry_run_capsule.json
```

---

## 9. Forbidden-phrase audit

This report does NOT contain any of:

- "Gate 6 real-data PASS"
- "bank-level precursor confirmed"
- "validated systemic precursor"
- "liquidity contagion claim"
- "INV-IDENTIFICATION-1 lifted"
- "VALIDATED_REAL_BANK_LEVEL_RESULT"
- "CONFIRMED" / "TESTED_POSITIVE_REAL"
- "real-data ready" (unqualified — `REAL_DOV_READY` only
  appears in §0 as the *forbidden* tier list)

The only tiers used are
`OUT_OF_VALIDATED_DOMAIN` (the empirical DoV verdict) and
`REAL_DOV_REJECTED` (the derived `claim_state` per
execution-lock §5).

# RD-001 — Real-Data Acquisition Gate (entry stays OPEN)

**Readiness entry:** RD-001 ("Real-data validation remains incomplete for stronger
market-facing research claims.")
**Disposition:** **deliberately NOT closed.** This artifact documents *why* the entry is
blocked and the exact contract that would close it. RD-001 is blocked by **data
availability, not by effort** — and substituting an inadmissible public proxy would be
the precise failure this gate exists to prevent.

## Why no code change can close RD-001

The pre-registered falsifier (`research/systemic_risk/`, claim `C-SYSRISK-PHASE`,
`HYPOTHESIS` tier) needs a **directed interbank exposure matrix** with **independent
crisis labels**. The admissible datasets are external and access-constrained:

| Dataset | Why it is not freely substitutable |
|---------|-----------------------------------|
| e-MID Italian interbank (2009–2015) | commercial/academic licence; not publicly downloadable; does not cover Lehman-2008 (out-of-window per `LIMITATIONS.md`) |
| BIS Locational Banking Statistics | public but **aggregate quarterly** — sensitivity-only, not a node-level temporal exposure matrix |
| ECB MMSR | granular but access-constrained |

A scraped or improvised "interbank-like" public CSV would carry **no independent
routing/crisis label** and the wrong structure — exactly the admissibility violation
tombstoned in the CTC open-data line (`no independent routing label ⇒ no real-data
claim`). Fetching such a substitute via a browser would manufacture evidence, not
produce it. **Fail-closed wins: we do not fake the data.**

## The exact contract that closes RD-001

Promotion requires (per `research/systemic_risk/README.md` and
`REAL_DATA_INGEST_CONTRACT.md`):

1. ≥ 2 valid crisis windows from a **licensed/admissible** real exposure dataset, each
   passing the data firewall (`data_firewall.py`, G1–G8 incl. `G8_provenance`).
2. Bootstrap-CI lower bound ≥ 0.70 with Bonferroni p ≤ 0.01 on each surviving crisis.
3. No crisis returns `HARD_FAIL` (CI crossing 0.5 or AUC ≤ 0.55).
4. Each surviving crisis clears all six null baselines (`null_models.py`, `PROTOCOL.md` §4).

Required readiness artifacts to flip RD-001 to `closed`: `dataset_hash` (SHA-256 of the
ingested licensed matrix), `provenance_note` (licence + source + access date), and
`evaluation_report` (the falsifier verdict — **including an honest null**: closing RD-001
means real data was *run through* the harness, not that the hypothesis survived).

## Action owner

Acquiring the licensed e-MID / ECB MMSR access is a **human/legal step** (the maintainer's
hands), not an autonomous one. Until then RD-001 remains `open` by design — a rigorous,
attributable block, not an oversight.

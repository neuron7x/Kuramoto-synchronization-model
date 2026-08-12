# EBSVAP — provenance

**Instruments:** Evidence-Bound Scoped Verified-Authority Protocol governance
surface — atomic claim compiler (WP1), proof-carrying action gateway (WP3),
process-validity / near-miss oracle (WP4).

**Origin:** ported from branch `research/ebsvap-authority-v1` @ `612ffce52988`
(pre-migration lineage, sealed release `final-convergence-2026-07-15-c21b5bfe`).
That lineage was re-rooted during the `geosync/… → core/…` namespace migration and
shares no mergeable ancestor with `main`; this is a content port, not a graph merge.

**Reproduced on `main`:** WP1 (recall=1.0, false_rejection=0.0) and WP3
(certificate_bypass_rate=0.0, deny_side_effect_rate=0.0) regenerate here via
`scripts/ci/ebsvap_wp1_run.py` / `ebsvap_wp3_run.py`; all invariants (incl. WP4)
are gated by `tests/ebsvap/test_ebsvap_governance.py` (100% module coverage).

**Standing verdict (unchanged):** CLAIM_INTEGRITY + ACTION_GOVERNANCE validated
**LIMITED_SCOPE**. Scientific / intervention authority **DENIED**. These instruments
test that governance *behaves* — they assert nothing about any target claim's truth.

# L2 Ricci Evidence-Protocol Hardening (P1-3)

Report for the diff-bound commit acceptor
`.claude/commit_acceptors/p13-ricci-l2-hardening.yaml`.

## Scope

This PR **extends** the merged #1116 L2 Ricci evidence-bearing session protocol.
It is strictly additive: it adds new resolution gates and tightens the semantic
validator, and it does not relax any gate #1116 established. The line remains
pinned at `HYPOTHESIS` / `semantic_validation_status: PLACEHOLDER` — no real
depth-5 capture exists, and registering reference objects is **not** registering
a result.

## What was hardened (evidence-theater closures)

1. **Placeholder mode cannot carry a real-data fixture.** A `PLACEHOLDER` session
   that carries any real (non-zero) `data_sha256`, `config_sha256`, or `git_sha`
   is rejected. A real-data session cannot masquerade as an inert skeleton to
   dodge the promotion gates.
2. **Semantic `PASS` requires real provenance.** A `PASS` status demands non-zero
   `data_sha256`, `config_sha256`, and `git_sha` (already enforced by #1116;
   retained and reinforced).
3. **Negative evidence must cover a null-model axis AND a lookahead axis.** An
   evidence session missing either required falsification axis is rejected
   (retained from #1116).
4. **Replay must be executable or explicitly blocked.** An evidence session
   requires an executable `python`/`python3` replay command and `replay_blocked`
   not `true` (a blocked replay is not a replay). Any non-evidence session whose
   `replay_command` is not executable must set `replay_blocked: true`; a
   silently-non-runnable command is rejected. The `--dry-run` skeleton now sets
   `replay_blocked: true` honestly.
5. **`baseline_id` / `null_model_id` / `falsifier_id` must resolve to a registry.**
   A new reference registry `config/research/l2_ricci_registry.yaml` describes the
   baselines, null models, and falsifiers a real session would be judged against.
   `tools/research/check_l2_registry_refs.py` rejects any id that does not resolve
   to a described entry, and the evidence gate reuses the same resolver. The
   `*_unset` ids the skeleton emits are deliberately unregistered, so a
   placeholder never resolves.

## Files

- `schemas/research/l2_ricci_session.schema.json` — adds `replay_blocked`; documents executable-or-blocked replay and registry resolution.
- `tools/research/run_l2_ricci_session.py` — placeholder hardening (all hashes), replay enforcement, registry-resolution wiring; skeleton flags replay blocked.
- `tools/research/check_l2_registry_refs.py` — new standalone registry-resolution gate.
- `config/research/l2_ricci_registry.yaml` — new reference registry (baselines / null_models / falsifiers).
- `docs/research/l2_ricci_evidence_protocol.md` — promotion gates + registry-resolution section.
- `tests/research/test_l2_ricci_session_schema.py` — extended hardening cases.
- `tests/research/test_l2_registry_refs.py` — new registry-resolution contract tests.
- `docs/reports/ricci_l2_evidence_hardening.md` — this report.
- `.claude/commit_acceptors/p13-ricci-l2-hardening.yaml` — diff-bound acceptor.

## Validation

```sh
python tools/research/run_l2_ricci_session.py --dry-run
pytest -q tests/research/test_l2_ricci_session_schema.py
pytest -q tests/research/test_l2_registry_refs.py
```

## Honest outcome

The gate **blocks** promotion: with the unset placeholder ids, the missing real
capture, and the blocked replay, an L2 Ricci session cannot reach evidence-bearing
status. That is the correct, fail-closed result — no real depth-5 data exists, so
the line stays `HYPOTHESIS`-tier.

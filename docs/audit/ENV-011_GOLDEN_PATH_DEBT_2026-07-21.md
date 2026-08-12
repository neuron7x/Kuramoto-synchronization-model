# ENV-011 — golden-path verification + legacy debt (2026-07-21)

**Deliverable:** `scripts/ci/check_golden_paths.py` — a fail-closed gate that parses the root
Makefile's real targets and verifies every `make <target>` a doc advertises **in a code context**
(inline `` `make x` `` or a fenced block; prose like "make sure" is excluded) actually resolves.
Teeth: `tests/ci/test_golden_paths_gate.py` — a NEW dangling citation → RED.

**Finding:** the gate surfaced **37 pre-existing documented `make` commands that do not exist**
(docs advertising a make-workflow that was never implemented or was renamed) — genuine
documentation rot. Example target names (written bare, not as commands, so this debt doc does
not itself trip the ratchet): docs-build, docs-check-links, codegen, chaos-suite,
registry-validate. Full list: `.github/golden_path_baseline.json`.

**Closure model (ratchet, not fake-green):** implementing 34 no-op targets would be fake, and
allowlisting the 37 as "fine" would hide them. Instead they are **baselined** (the same ratchet
pattern the repo uses for debt/teeth/meta gates): the gate blocks any NEW dangling golden path
(0 allowed) while the 37 legacy are explicitly recorded for paydown. When a doc is corrected, the
gate demands the baseline tighten (a fixed entry → RED until removed).

**Paydown (tracked follow-up, not faked):** the 37 split into (a) docs-tooling targets with a
near-equivalent (`make docs`, `make docs-lint` exist) — fix the citation; (b) genuinely
unimplemented workflows — either build the target or mark the doc as planned. Owner: docs; not
claimed done here. This gate makes golden paths **verified and non-regressing**; the legacy
paydown is the residual, stated not hidden.

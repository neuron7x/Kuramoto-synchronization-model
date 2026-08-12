# Waiver / Exception Protocol (GOV-004)

## Principle

A governance gate exists to fail closed. The *only* legitimate way to let a
known deviation ship is a **waiver**: a time-boxed, accountable, self-expiring
exception. This repo forbids the alternative that rots every codebase — the
indefinite allowlist entry, the expiry-less ratchet carve-out, the "temporary"
suppression that outlives the person who added it.

Two invariants make the protocol trustworthy:

- **Fail-closed on expiry.** Every waiver carries a dated `expiry`. The moment
  that date passes, `scripts/ci/check_waivers.py` returns RED on its own. No
  human has to remember; the gate remembers.
- **Determinism.** The checker never reads the wall clock inside its decision
  logic. The current date is injected with `--now YYYY-MM-DD`. CI passes today;
  tests pass a fixed date. Every run is reproducible.

## Hard rules (enforced by the gate)

| # | Rule                                                                                   | Effect       |
|---|----------------------------------------------------------------------------------------|--------------|
| 1 | Every required field present and non-empty.                                            | else RED     |
| 2 | `expiry` is a real `YYYY-MM-DD` date. **No expiry is forbidden.**                       | else RED     |
| 3 | `expiry` is not before `--now`. An **expired waiver is automatically RED.**             | else RED     |
| 4 | **A `P0` finding can NEVER be waived.**                                                 | P0 → RED     |
| 5 | A **`P1` waiver requires two distinct approvers.** Any waiver requires at least one.    | else RED     |
| 6 | Each file is valid YAML with a top-level `waiver:` mapping.                             | else RED (2) |

Required fields: `id`, `gate`, `priority`, `rationale`, `scope`,
`compensating_control`, `owner`, `approvers`, `expiry`, `revalidation_command`.
The authoritative field reference is `governance/waivers/SCHEMA.md`.

## Priority tiers

| Priority | Waivable? | Approval                    |
|----------|-----------|-----------------------------|
| `P0`     | **Never** | — (categorically forbidden) |
| `P1`     | Yes       | **≥ 2 distinct approvers**  |
| `P2`     | Yes       | ≥ 1 approver                |

`P0` maps to a life-critical / release-blocking finding. There is no rationale,
no compensating control, and no seniority that buys a P0 waiver: the tier is
fixed and the gate refuses it unconditionally.

## Lifecycle

1. **Raise** — copy `governance/waivers/EXAMPLE-P1-flaky-latency-probe.yaml` to a
   new file `governance/waivers/WVR-<year>-<id>.yaml`. Fill every field. Pick an
   honest, near-term `expiry` — the shortest window that lets the real fix land.
2. **Approve** — record accountable humans in `approvers` (two distinct names
   for P1). The `owner` is the single person answerable for closing it.
3. **Merge** — CI runs `python scripts/ci/check_waivers.py --now <today>`. The
   build is GREEN only while the waiver is well-formed and in-date.
4. **Revalidate** — run the `revalidation_command` to prove the deviation is
   gone. When it is, **delete the waiver file** (do not extend the expiry as a
   habit; an extension is a fresh decision requiring fresh approval).
5. **Auto-expire** — if nobody acts, `expiry` passes and the gate goes RED,
   forcing the deviation back onto the table. This is the safety net, not the
   plan.

## Running the gate

```bash
# CI (today's date)
python scripts/ci/check_waivers.py --now "$(date -u +%F)"

# Deterministic / local reproduction
python scripts/ci/check_waivers.py --now 2026-07-19
```

Exit codes: `0` all waivers permitted and in-date · `1` at least one expired,
forbidden (P0), under-approved (P1 < 2), or malformed · `2` waivers directory
missing or a file is not valid YAML (fail-closed).

## Tests

`tests/ci/test_waivers.py` is the falsification battery. It proves the gate
turns RED for each forbidden shape (expired, P0, P1-under-approved, no-expiry)
and GREEN for a valid unexpired P1 with two approvers:

```bash
python -m pytest tests/ci/test_waivers.py -q
```

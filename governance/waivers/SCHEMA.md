# Waiver Schema (`governance/waivers/*.yaml`)

A waiver is a **time-boxed, accountable exception** to a governance gate. It is
the *only* legitimate way to let a known deviation ship — and it is fail-closed:
the moment a waiver expires, the gate goes RED again on its own. There is no
such thing as a permanent, expiry-less, or indefinite exception in this repo.

Each `.yaml` file under `governance/waivers/` contains a single top-level
`waiver:` mapping with the following fields. Every field is **required**;
`scripts/ci/check_waivers.py` fails closed when any is missing or malformed.

| Field                  | Type            | Rule enforced by the gate                                              |
|------------------------|-----------------|------------------------------------------------------------------------|
| `id`                   | string          | Non-empty. Stable identifier (e.g. `WVR-2026-001`).                    |
| `gate`                 | string          | Non-empty. The gate / allowlist / ratchet the deviation touches.       |
| `priority`             | `P0`\|`P1`\|`P2` | Must be a known priority. **`P0` can NEVER be waived** → RED.          |
| `rationale`            | string          | Non-empty. Why the deviation is tolerated *right now*.                 |
| `scope`                | string          | Non-empty. Exactly what the waiver covers (bounded, not blanket).      |
| `compensating_control` | string          | Non-empty. What mitigates the risk while the waiver is live.           |
| `owner`                | string          | Non-empty. The single accountable human.                               |
| `approvers`            | list[string]    | **`P1` requires ≥ 2 distinct approvers**; any waiver requires ≥ 1.     |
| `expiry`               | `YYYY-MM-DD`    | **Required, dated.** No expiry → RED. `expiry < now` → RED.            |
| `revalidation_command` | string          | Non-empty. The exact command that re-proves the deviation is gone.     |

## Fail-closed conditions (each forces exit non-zero / gate RED)

1. **Missing field** — any required field absent or empty.
2. **No expiry** — `expiry` missing or not a `YYYY-MM-DD` date.
3. **Expired** — `expiry` is strictly before the supplied `--now` date.
4. **P0 waiver** — `priority: P0` is categorically forbidden.
5. **P1 under-approved** — `priority: P1` with fewer than two distinct approvers.
6. **Malformed file** — not valid YAML, or no `waiver:` mapping (fail-closed).

## Determinism

The checker never reads the wall clock inside its decision logic. The current
date is injected explicitly:

```
python scripts/ci/check_waivers.py --now 2026-07-19
```

CI passes today's date; tests pass a fixed date so every run is reproducible.
See `docs/WAIVER_PROTOCOL.md` for the full protocol and lifecycle.

# Security reachability model

Source-of-truth: [`tools/security/reachability_graph.py`](../../tools/security/reachability_graph.py)
Tests: [`tests/security/test_reachability_graph.py`](../../tests/security/test_reachability_graph.py)
First-case follow-up: [issue #446](https://github.com/neuron7xLab/GeoSync/issues/446)

## Why this exists

The 2026-04-26 audit identified two recurring overclaims:

- treating a CVE advisory as proof of an active exploit
- treating a vulnerable lockfile pin as proof of a reachable exploit

The reachability model refuses both. It produces a tier per advisory
based ONLY on what the source code allows the runtime to do.

## Reachability tiers (ordered)

| Tier | Means |
|---|---|
| `UNUSED` | The package is not imported in any runtime code path. |
| `PACKAGE_PRESENT` | The package is imported, but no runtime route uses it. |
| `ROUTE_PRESENT` | A runtime route is mounted that uses the package. |
| `AUTH_SURFACE_PRESENT` | A route is mounted AND a FastAPI `Depends(...)` (or middleware) is wired at that mount. |
| `EXPLOIT_PATH_CONFIRMED` | A runtime test reproduces the exploit. **Static analysis cannot set this tier.** It is set only by a hand-curated entry in `CONFIRMED_EXPLOIT_PATHS` pointing at the test that reproduces the path. |

The static classifier deliberately stops at `AUTH_SURFACE_PRESENT`. Going
to `EXPLOIT_PATH_CONFIRMED` requires runtime evidence; the
`confirmed_exploit_paths` block of the report is the only place that
distinction lives.

## Output

```json
{
  "facts": [
    {
      "package_name": "strawberry-graphql",
      "advisory_id": "GHSA-vpwc-v33q-mq89",
      "locked_version": "0.315.2",
      "fixed_version": "0.312.3",
      "imported": true,
      "runtime_route": true,
      "websocket_surface": true,
      "auth_boundary": "YES",
      "exploit_path_confirmed": false,
      "reachability": "AUTH_SURFACE_PRESENT",
      "evidence_paths": [
        "application/api/graphql_api.py",
        "application/api/service.py"
      ],
      "followup_issue": 446,
      "notes": "Triggered at WebSocket handshake; needs route + auth analysis."
    }
  ],
  "confirmed_exploit_paths": {}
}
```

## First-case wiring (strawberry-graphql / GraphQLRouter / /graphql)

Two seed advisories are encoded in `SEED_ADVISORIES`:

- `GHSA-vpwc-v33q-mq89` — auth bypass via legacy `graphql-ws` subprotocol
- `GHSA-hv3w-m4g2-5x77` — DoS via unbounded WebSocket subscriptions

Both target Strawberry's `GraphQLRouter`. Both are linked to **issue #446**
via the `FOLLOWUP_ISSUES` mapping. Both currently classify at
`AUTH_SURFACE_PRESENT` on the live tree:

- `imported`: TRUE — `application/api/graphql_api.py` does
  `from strawberry.fastapi import GraphQLRouter`
- `runtime_route`: TRUE — the factory `create_graphql_router` is mounted
  via `app.include_router(graphql_router, prefix="/graphql", ...)` in
  `application/api/service.py`
- `websocket_surface`: TRUE — file-level evidence; the `service.py` file
  also contains an unrelated `@app.websocket("/ws/stream")` endpoint, so
  this flag is conservatively set to TRUE
- `auth_boundary`: YES — the `include_router` call passes
  `dependencies=[Depends(enforce_public_rate_limit)]`
- `exploit_path_confirmed`: FALSE — no test in this repo reproduces the
  GHSA-vpwc bypass against this configuration; that work is the scope of
  issue #446
- `locked_version`: 0.315.2 — already above `fixed_version: 0.312.3`,
  so version risk is closed (PR #445); the open question is the
  reachability classification of the residual surface

The classifier's job is to keep all of those facts mechanically observable
so that flipping any of them (e.g. someone bumps strawberry but the lock
goes back to 0.287.x) becomes a test failure.

## How tier promotion works

```
                ┌──────────────┐
                │  UNUSED      │
                └──────┬───────┘
                       │ import found in runtime tree
                       ▼
                ┌──────────────┐
                │ PACKAGE_     │
                │   PRESENT    │
                └──────┬───────┘
                       │ include_router() mounts the construct
                       │ (direct OR via factory)
                       ▼
                ┌──────────────┐
                │ ROUTE_       │
                │   PRESENT    │
                └──────┬───────┘
                       │ Depends(...) at the mount call
                       ▼
                ┌──────────────┐
                │ AUTH_SURFACE_│
                │   PRESENT    │
                └──────┬───────┘
                       │ MANUAL: CONFIRMED_EXPLOIT_PATHS entry +
                       │ a runtime test that reproduces the exploit
                       ▼
                ┌──────────────┐
                │ EXPLOIT_     │
                │   PATH_      │
                │   CONFIRMED  │
                └──────────────┘
```

## What the model deliberately does NOT do

- It does NOT promote a tier without source-level evidence. A vulnerable
  lockfile pin alone gets `PACKAGE_PRESENT` at most; the WS handshake
  authn surface mapping (issue #446) is the only thing that can promote
  the GeoSync GraphQL case beyond `AUTH_SURFACE_PRESENT`.
- It does NOT replace pip-audit / osv-scanner. Those tools answer
  "is this version vulnerable?". This tool answers "if the version is
  vulnerable, can the exploit reach our runtime?".
- It is NOT an AST/Tree-sitter analyser. All detection is line-grep
  level, deliberately conservative. The two-pass analyser (direct +
  factory-mediated) covers the GeoSync pattern but will under-report
  exotic factory chains. Treat low-tier results as a floor, not a
  ceiling.
- It does NOT classify per-route. `service.py` may host five routes;
  the classifier reports `runtime_route = TRUE` if any of them mounts
  the construct. This is conservative; tightening it to per-route
  granularity would require AST parsing.

## Skipped trees

The classifier skips: `tools/`, `tests/`, `docs/`, `scripts/`, `spikes/`,
`benchmarks/`, `fixtures/`, `research/`, `.claude/`. These are
non-runtime; counting them would create false positives (e.g. this
documentation file mentioning `GraphQLRouter` should not bump the tier).

## Running

```bash
# Classify all seed advisories (always exits 0):
python tools/security/reachability_graph.py

# Persist:
python tools/security/reachability_graph.py --output reports/reachability.json

# Gate mode (exits non-zero if any advisory is at EXPLOIT_PATH_CONFIRMED):
python tools/security/reachability_graph.py --exit-on-confirmed-exploit
```

## Adding an advisory

1. Append a new `Advisory(...)` to `SEED_ADVISORIES` with:
   - `affected_modules`: top-level dotted module names (e.g. `strawberry.fastapi`)
   - `affected_constructs`: class / function names exported by those
     modules (e.g. `GraphQLRouter`)
2. If the advisory has a follow-up issue, add it to `FOLLOWUP_ISSUES`.
3. Run the classifier and verify the tier matches reality.
4. Add a test case under `tests/security/test_reachability_graph.py`
   for the new advisory.

## Promoting to `EXPLOIT_PATH_CONFIRMED`

1. Write a runtime integration test that reproduces the advisory against
   a live server (e.g. `tests/integration/test_graphql_ws_authn.py` for
   GHSA-vpwc-v33q-mq89).
2. Make the test PASS today (the path is exploitable) or FAIL today
   (the path is rejected).
3. If the test demonstrates the path IS exploitable: add the test path
   to `CONFIRMED_EXPLOIT_PATHS`. The classifier will promote the
   advisory to `EXPLOIT_PATH_CONFIRMED` and gate CI.
4. If the test demonstrates the path is NOT reachable: leave the entry
   out of `CONFIRMED_EXPLOIT_PATHS`; mark issue #446 with the negative
   result; the classifier stays at `AUTH_SURFACE_PRESENT` (which is the
   correct state).

The classifier never confirms an exploit on its own. That asymmetry is
intentional.

## Origin

Same arc:

- F03 trap: vulnerable Strawberry pin was conflated with reachable auth
  bypass. The audit refused that conflation; this tool turns the refusal
  into machine-readable form.
- The first-case wiring matches the issue #446 follow-up plan:
  reachability stays at `AUTH_SURFACE_PRESENT` until the WS handshake
  authn integration test resolves the question one way or the other.

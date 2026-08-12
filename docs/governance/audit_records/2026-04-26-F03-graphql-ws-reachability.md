# F03 reachability — GraphQL WebSocket integration witness (2026-04-26)

**Audit protocol:** CNS → Exploration → ЦШС → Tests → Falsifiers → Ledger → Compression
**Issue:** [#446](https://github.com/neuron7xLab/GeoSync/issues/446)
**PR:** #452 (`fix(security): F03 reachability — GraphQL WS integration witness`)
**Replaces:** `SEC-GRAPHQL-WS-AUTHN-REACHABILITY` (REJECTED)
**Records:** `SEC-GRAPHQL-WS-PUBLIC-SURFACE` (FACT, ACTIVE)

## Why this record exists

PR #445 closed F03 *version risk* (Strawberry 0.315.2, above the
0.312.3 fix floor for `GHSA-vpwc-v33q-mq89` and `GHSA-hv3w-m4g2-5x77`).
The reachability question was deliberately deferred: claim
`SEC-GRAPHQL-WS-AUTHN-REACHABILITY` stayed at SPECULATION because
Strawberry's `GraphQLRouter` auto-registers WebSocket subprotocols
even when the schema declares no Subscription type, and no integration
test had observed what actually happens at handshake time on `/graphql`.

This record is the integration witness.

## Method

The witness is `tests/integration/test_graphql_ws_reachability.py`. It
mounts the SAME `create_graphql_router` factory the production service
uses, under the SAME path (`/graphql`), with the SAME pre-existing
public rate-limit dependency wiring (`enforce_public_rate_limit`),
then drives an unauthenticated WebSocket handshake with each of:

```
Sec-WebSocket-Protocol: graphql-ws
Sec-WebSocket-Protocol: graphql-transport-ws
```

The harness records four observable facts per attempt:

1. whether the connection was accepted at the HTTP upgrade
2. which subprotocol the server agreed to
3. whether the registered FastAPI dependency was invoked
4. whether `connection_init` returns `connection_ack`

It does NOT exploit anything. It does NOT make a vulnerability claim.

## Observed reachability

| subprotocol | tier | accepted_subprotocol | dependency_invoked | post-init recv |
|---|---|---|---|---|
| `graphql-ws` | `PROTOCOL_HANDSHAKE_ACCEPTED` | `'graphql-ws'` | True | `{'type': 'connection_ack'}` |
| `graphql-transport-ws` | `PROTOCOL_HANDSHAKE_ACCEPTED` | `'graphql-transport-ws'` | True | `{'type': 'connection_ack'}` |

Schema introspection at the same time:

```
schema._schema.subscription_type is None
```

## Translation to advisory reachability

### `GHSA-vpwc-v33q-mq89` — Authentication bypass via legacy `graphql-ws`

**Reachability: N/A by design.**

The advisory describes a class of bug where a server that *expected*
authentication on subscriptions could be bypassed by negotiating the
legacy `graphql-ws` subprotocol. Reachability requires **an
authentication surface to bypass**.

The `/graphql` endpoint in this repository has no authentication
configured. It is a public read-only API behind a public rate-limit.
There is no auth surface to bypass; the advisory's class does not
apply to this configuration. The witness confirms the rate-limit
dependency *is* invoked at WS upgrade — so a layer-7 boundary exists
— but that boundary is rate-limit, not authentication.

This is NOT the same statement as "the WS surface is unreachable". The
WS surface is reachable. Both subprotocols complete their handshake.
The point is that the advisory's *attack class* requires the existence
of an authentication step to bypass; that step is absent by design.

### `GHSA-hv3w-m4g2-5x77` — DoS via unbounded WebSocket subscriptions

**Reachability: N/A by design.**

The schema declares no Subscription type. After
`connection_init → connection_ack`, no subscription operation is
available because the schema does not advertise one. Strawberry's
runtime-level `max_subscriptions_per_connection` default (100) does
not even come into play, because there are no subscriptions to hit
the cap.

The witness includes a guard
(`test_no_subscription_type_in_schema`) that fires if a Subscription
type is ever added. At that moment, this advisory's reachability MUST
be re-derived; the claim is no longer FACT-with-this-statement.

## Ledger transitions

```
SEC-GRAPHQL-WS-AUTHN-REACHABILITY
  before:  SPECULATION / PARTIAL / non_testable_reason="follow-up scope of #446"
  after:   REJECTED + rejection_reason
           superseded_by: SEC-GRAPHQL-WS-PUBLIC-SURFACE
```

The original framing was wrong (it asked a question that didn't apply
to the actual configuration). The entry stays in the ledger as a
negative reference so the same overclaim ("WS handshake bypass on
/graphql is operationally exploitable") cannot return without a
matching ledger update that explains why.

```
SEC-GRAPHQL-WS-PUBLIC-SURFACE
  status: ACTIVE
  tier:   FACT
  evidence: INTEGRATION_TEST + 2 × MANUAL_INSPECTION + EXTERNAL_ADVISORY
  test:   tests/integration/test_graphql_ws_reachability.py
  falsifier: any of three named integration-test failures
```

## Falsifier (executed during PR #452)

Probe: instantiate a synthetic schema with a real Subscription type,
verify `test_no_subscription_type_in_schema` would fail against it.

```python
schema_with_sub = strawberry.Schema(query=Query, subscription=Subscription)
router_with_sub = GraphQLRouter(schema_with_sub)
assert router_with_sub.schema._schema.subscription_type is not None
# -> "FALSIFIER OK: regression test would fire if Subscription is added"
```

`git diff --exit-code application/api/graphql_api.py` clean — production
code never modified. The falsifier proves the regression test catches
the future-drift case (someone adds a Subscription without re-deriving
reachability) without requiring a code edit.

## What this audit record does NOT do

- It does NOT claim the codebase is invulnerable to all WebSocket
  vectors. It addresses the two named advisories on the version PR #445
  closed.
- It does NOT claim no future change can re-open this question. The
  three falsifiers in the integration test are the guards against
  exactly that.
- It does NOT alter the public-by-design semantics of `/graphql`. If
  the team decides `/graphql` should require authentication, that's a
  product decision; this record only states what the witness observed
  about the current configuration.

## What this audit record DOES do

- Promotes one claim to FACT with named integration evidence.
- Marks the previous claim REJECTED with explicit rejection_reason and
  preserves it as a negative reference.
- Names three concrete falsifiers any future PR that touches the
  GraphQL surface MUST satisfy.
- Closes issue #446.

# GeoSync Resurrection Agent

Implementation of **SYSTEM_ARTIFACT_v9.0** — a deterministic cognitive control
agent that restores precursor-capable substrate, maintains liveness, and
routes only physically valid tasks into GeoSync's research pipeline.

The agent is **not** a trader. It is a substrate-control organism that
enforces the hard invariant from the spec's §0:

> OHLC close bars do not contain precursor-grade microstructure.
> Therefore: no precursor claim from close-only topology.

## Entry point

```bash
python -m agent.main
python -m agent.main --panel data/askar_full/panel_hourly_extended.parquet
```

Each invocation runs one deterministic pass of the state machine and
writes five audit artefacts into `agent/reports/`:

| file                     | purpose                                     |
|--------------------------|---------------------------------------------|
| `provider_manifest.json` | every configured/unconfigured vendor        |
| `substrate_health.json`  | `SubstrateHealth` snapshot                  |
| `schema_audit.json`      | per-asset precursor capability              |
| `action_intent.json`     | the `ActionIntent` emitted this tick        |
| `replay_hash.sha256`     | deterministic payload hash for audit replay |

On the committed Askar panel (`data/askar_full/panel_hourly.parquet`,
close-only), the agent immediately labels the substrate
`LATE_GEOMETRY_ONLY` and emits `DISCOVER_SOURCES` with `substrate_status
= DEAD` — this is the programmatic enforcement of the conclusion we
reached manually across PRs #190–#198.

## Closing the "which vendor?" gap

The v9.0 spec is silent on which provider actually delivers bid/ask/OFI
for XAUUSD and equity hourly data. Without a concrete answer, any
implementation of `POST /api/v1/collect` would loop forever in
`COLLECT`. `agent/providers.py` closes this gap by enumerating seven
real vendors, every one of which is `configured=False` by default:

| `source_id`            | provider          | covers                         | L1 | L2  | env var                 | pricing        |
|------------------------|-------------------|--------------------------------|----|-----|-------------------------|----------------|
| `dukascopy_historical` | Dukascopy Bank    | XAUUSD, FX, indices            | ✅ | ❌  | `DUKASCOPY_DOWNLOAD_DIR`| free           |
| `oanda_v20`            | OANDA Corp        | XAU/XAG, FX                    | ✅ | ❌  | `OANDA_API_TOKEN`       | free demo      |
| `databento`            | Databento Inc.    | CME, ICE, NASDAQ futures/ETFs  | ✅ | ✅  | `DATABENTO_API_KEY`     | ~$500+/mo      |
| `polygon_io`           | Polygon.io        | US equities, options, FX       | ✅ | ❌  | `POLYGON_API_KEY`       | $29–$199/mo    |
| `interactive_brokers`  | IBKR              | Full Askar universe            | ✅ | ✅  | `IBKR_GATEWAY_HOST`     | IBKR account   |
| `binance_futures`      | Binance           | Crypto only (pipeline test)    | ✅ | ✅  | `BINANCE_WS_ENDPOINT`   | free           |
| `askar_ots_raw_l2`     | Askar / OTS       | Original claim, not delivered  | ✅ | ✅  | `ASKAR_L2_ENDPOINT`     | escalation     |

When no `env var` is set, `ProviderCandidate.is_configured()` returns
`False`, `active_sources()` yields an empty list, and the policy layer's
`RULE_01` fires, transitioning the agent to `DORMANT`-adjacent
`DISCOVER_SOURCES`. **The agent never spins in a vendor-less COLLECT
loop** — it stops and reports the exact credential gap.

To activate, for example, Dukascopy:

```bash
export DUKASCOPY_DOWNLOAD_DIR=/var/data/dukascopy
python -m agent.main
```

On the next tick, `dukascopy_historical` flips to `auth_ok=True`;
the next-tier gates (`CHECK_CONNECTIVITY`, `CHECK_LIVENESS`,
`AUDIT_SCHEMA`) then fire in order and block at whichever one fails
first. The agent makes progress strictly on what the operator plugs
in; nothing is hallucinated.

## Architecture (per §4 / §16)

```
agent/
├── __init__.py
├── main.py                  — deterministic single-pass entry point
├── models.py                — every data structure from §7 as a dataclass
├── invariants.py            — INV_001..INV_012 as pure functions
├── state_machine.py         — legal transitions declaratively
├── policy.py                — RULE_01..RULE_15 deterministic selector
├── providers.py             — seven concrete vendor candidates
├── adapters/
│   ├── __init__.py
│   └── filesystem.py        — FileSystemSubstrateAdapter (read-only probe)
└── modules/
    ├── __init__.py
    ├── feed_sentinel.py     — SubstrateHealth computation
    ├── schema_auditor.py    — per-asset precursor capability detection
    └── reporter.py          — atomic JSON artefact writer + replay hash
```

### What is NOT implemented in this PR

Per the fail-closed honesty contract, the adapter's write-side methods
(`collect`, `backfill`, `enrich`) raise `NotImplementedError`. They can
only be honoured by a real vendor adapter plugged in through the
provider registry — the agent refuses to fake microstructure from
close bars.

The remaining sub-agents from §4 (A Source Scout, D Gap Repair, E
Canonicalizer, F Microstructure Enricher, G Topology Engine Router,
H Adversarial Validator, I Claim Governor) are scaffolded conceptually
but not yet coded. They are scheduled for follow-up PRs once a real
vendor is connected.

## Invariants enforced today (§6)

| id        | rule                                                             | passed on committed panel |
|-----------|------------------------------------------------------------------|---------------------------|
| INV_001   | `OHLC_CLOSE_ONLY → precursor_claim = false`                       | ❌ (close-only)           |
| INV_002   | missing all([bid, ask, trades, depth]) → DEGRADED                 | ❌                         |
| INV_003   | stale feed → no validation                                        | ❌ (last bar > 30 days)    |
| INV_004   | `nan_rate > 0` → abort current pipeline                           | ✅                         |
| INV_005   | asset coverage ≥ 10 for cross-asset topology                      | ✅ (53 assets)             |
| INV_006   | orthogonality not measured → no verdict                           | ❌ (no verdict yet)        |
| INV_007   | lead_capture not measured → no precursor claim                    | ❌                         |
| INV_008   | `p_value ≥ MAX_P (0.10)` → REJECT                                 | ❌ (no verdict)            |
| INV_009   | `IC < MIN_IC (0.08)` → REJECT                                     | ❌ (no verdict)            |
| INV_010   | missing audit artefacts → pipeline INVALID                        | ✅                         |
| INV_011   | schema drift → quarantine                                         | ❌ (drift = no precursor)  |
| INV_012   | protectors always override generators (GeoSync physics doctrine)  | ✅ (design constant)       |

## Relationship to the Askar research track

The agent is the formal closure of PRs #188–#198. Across eleven
experiments we established:

1. Close-only topology (Ricci, Betti-1, Unity, ensemble) gives no
   tradable IC on Askar's hourly substrate.
2. All these features are orthogonal to VIX/HYG *returns* but share
   the same correlation-density coupling with SPX realised vol.
3. The only honest next step is to obtain bid/ask/L2/trade tape —
   substrate upgrade, not another close-only sprint.

The agent translates this conclusion into a running policy: every
future contributor who clones the repo and runs `python -m agent.main`
gets the same `DISCOVER_SOURCES / DEAD` verdict until they plug in
one of the seven named providers. No one can accidentally run a
precursor claim on dead substrate again.

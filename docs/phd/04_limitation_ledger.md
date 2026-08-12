# 04 — Limitation Ledger

Honest, enumerated limitations. Each is a known boundary, not a hidden gap. A
dissertation is strengthened, not weakened, by a precise limitation ledger.

| # | Limitation | Status / evidence | Why it stands | Path to close |
|---|---|---|---|---|
| L1 | **B.wheel ≠ 0** | `check_wheel_contract.py --strict` → FAIL | wheel still ships non-`geosync` legacy | re-home or evacuate the connected legacy component |
| L2 | **13 legacy packages** in wheel | `artifacts/wheel_contract.json::non_geosync_packages` | one entrypoint-anchored connected component (scripts/core/application/tools + closure) | sequenced re-home (mostly BLOCKED, see L4) |
| L3 | **70 latent import failures** | `artifacts/wheel_contract.json::import_failures` | packaged modules import unpackaged first-party (e.g. `facade.py`→`rl`,`runtime`) | frozen monotone-down; each fix tightens the ledger |
| L4 | **core / application BLOCKED by import graph** | `artifacts/import_graph/tp_kuramoto.json` (35M/21I/INV), `geosync_server.json` (93M/runtime) | bulk move = scientific/runtime behavior risk; #945 out-of-scope | wrapper-first done; deeper migration only with CI-proven behavior parity |
| L5 | **No market alpha / profitability claim** | by construction (claim-tier governance) | system measures admissibility, not returns | out of scope — never to be claimed without dataset-backed study |
| L6 | **No real L2 empirical validation** | no recorded depth-5 session + replay present | live venue capture unavailable in this environment | `05` — run as falsification study only |
| L7 | **Falsifier adequacy unmeasured** | `FALSIFIER_LEDGER.yaml` proves *executable*, not *powerful* | adequacy needs real data + power analysis | per-null power study in the empirical chapter |
| L8 | **Claim scanner is scope-narrow** | RQ1 negative finding | bare-word bans over-reject honest disclaimers | negation-aware detection (future work) |
| L9 | **Local green ≠ merge-ready** | CI is the oracle; merges only on full CI green | local runs miss hidden gates (5 caught this campaign) | unchanged policy — feature, not bug |

## Promotion discipline (binding)

No entry in this ledger may be re-narrated as resolved without (a) the
corresponding CI gate turning the relevant verdict, and (b) the artifact/ledger
agreeing. "Partial" stays "partial". Admissibility never silently becomes
empirical truth.

# GeoSync Dashboard — neuron7xLab.md (cream editorial) Audit

## Update — truth-mode (PR #2)

Every physics-originating number is now read live from a real engine
(`ui/dashboard/live_server.py` → `/api/state`). No panel fabricates values;
on engine failure the UI collapses to `—` and the footer surfaces the reason.

Live under truth-mode:

- `metrics.sharpe / ic / alpha / max_dd` — causal annualised Sharpe
  (pnl[t] = pos[t-1]·ret[t]), Spearman-rank IC, ann. alpha vs the raw
  spread-return, max drawdown of the cumulative PnL.
- `dro_ara.{state, H, gamma, r_s, r2, trend, signal, stationary}` — direct
  `core.dro_ara.engine.geosync_observe` output. INV-DRO1 / INV-DRO2 asserted
  live in the UI rules list.
- `kuramoto.{r_t, k_kc, N, gate}` — local RK4 trajectory on N=128 Lorentzian
  natural frequencies, K/K_c = 1.42. INV-K1 / INV-K3 asserted in watch list.
- `kelly.{f_star, applied, cap}` — f* = μ/σ² from the realised return stream;
  INV-KELLY2 asserted.
- `gamma_regime` — γ = 2H derived from DRO-ARA, state mapped per §2.5.
- `pnl.{total, realised, unrealised, fees, pct, run_rate, turnover}` —
  cumulative execution of the z-score mean-reversion overlay on the
  DRO-ARA regime gate (`pos = engagement · (−tanh(z))`). Strategy string
  returned in `origin.strategy`.

Price source: a seed-deterministic Ornstein–Uhlenbeck spread
(θ=0.18, μ=0, σ=0.9, seed=42), labelled in `origin.price_source`. A raw
BTC/ETH price has a unit root by construction and maps to INVALID per the
engine; DRO-ARA is for *spreads*, so the dashboard is fed a spread.

## Original PR #1 contract audit follows

Contract: `./DESIGN.md` at repo root (= `./neuron7xLab.md`, warm-minimalism research-paper aesthetic).
Previous Linear contract archived at `./DESIGN.md.linear.bak`.
Scope: `ui/dashboard/` — vanilla-JS trading dashboard (`*.css.js` style modules + `demo.html`).

## neuron7xLab tokens (source: DESIGN.md)

| Category | Token | Value |
|---|---|---|
| bg canvas | `--bg-canvas` | `#F2EDE4` warm cream |
| bg elevated | `--bg-elevated` | `#EBE5D9` |
| bg sunken | `--bg-sunken` | `#E4DDCE` |
| bg overlay | `--bg-overlay` | `#F7F3EC` |
| ink primary | `--ink-primary` | `#1F1D1A` charcoal |
| ink secondary | `--ink-secondary` | `#4A4640` |
| ink tertiary | `--ink-tertiary` | `#8A8278` |
| ink inverse | `--ink-inverse` | `#F7F3EC` |
| rule hairline | `--rule-hairline` | `#CEC6B5` |
| rule medium | `--rule-medium` | `#A89F8C` |
| sig accent | `--sig-accent` | `#6A3416` terracotta (≤3 uses/view) |
| sig positive | `--sig-positive` | `#2F6B3A` editorial green |
| sig negative | `--sig-negative` | `#8A2A1E` oxblood |
| sig caution | `--sig-caution` | `#8F6A1F` ochre |
| sig neutral | `--sig-neutral` | `#3D5A7A` blue-slate |
| type display | IBM Plex Sans 600 · `-0.01em` at display sizes | |
| type body | IBM Plex Sans 400/500 · `0` tracking | |
| type mono | IBM Plex Mono · `tabular-nums` on every numeric | |
| radii | 0 / 2 / 4 / 8 / 999 (default 0 or 2) | |
| motion | single editorial curve `150ms cubic-bezier(0.2,0,0,1)`; pulse 1800ms only | |
| signatures | γ-indicator top-right · ⊛ footer glyph · CANON·2026 version line · "7" as proportion | |

## Delta vs previous Linear pass

| Axis | Linear pass | neuron7xLab pass |
|---|---|---|
| canvas | `#08090a` near-black | `#F2EDE4` warm cream |
| ink | `#f7f8f8` off-white | `#1F1D1A` charcoal |
| accent | `#5e6ad2` indigo-violet | `#6A3416` terracotta |
| borders | semi-transparent white | solid hairline `#CEC6B5` |
| radii default | 8 px card | 4 px card, 0 / 2 elsewhere |
| type family | Inter Variable + cv01/ss03 | IBM Plex Sans + IBM Plex Mono |
| type weights | 400 / 510 / 590 | 400 / 500 / 600 |
| tracking | display `-1.056px@48` | display `-0.01em` |
| elevation | border-as-shadow ring | background tonal shift + hairline |
| signatures | none | γ-indicator + ⊛ + CANON·2026 + "7" proportion |

## Violation table — pre-refactor → neuron7xLab contract

| # | Surface | Source state | neuron7xLab rule | Severity |
|---|---|---|---|---|
| V01 | canvas | multi-gradient dark `#020617`/`#0a0f1e` + aurora + noise | flat `#F2EDE4` cream | **P0** |
| V02 | panels | `rgba(10,15,30,0.95)` dark glass | `#EBE5D9` elevated + hairline | **P0** |
| V03 | cards | `rgba(15,23,42,0.8)` + backdrop-blur | `#EBE5D9` flat + hairline | **P0** |
| V04 | borders | `rgba(99,179,237,0.25)` cyan | `#CEC6B5` hairline solid | **P0** |
| V05 | accents | cyan + violet + emerald + amber gradients | single terracotta `#6A3416` | **P0** |
| V06 | text colour | tinted whites on dark | charcoal `#1F1D1A` on cream | **P0** |
| V07 | font family | Inter 400/600/700 | IBM Plex Sans 400/500/600 + IBM Plex Mono | **P0** |
| V08 | weight 700 | frequent | forbidden — max 600 per §3.2 | **P0** |
| V09 | gradient text | `-webkit-background-clip: text` on H1/H2/stat-value | forbidden per §11 | **P0** |
| V10 | mono / tabular-nums | absent | mandatory on every numeric per §3.1 | **P0** |
| V11 | drop-shadow on text | `filter: drop-shadow(0 0 30px cyan)` | forbidden | **P0** |
| V12 | radii | 16–28 px cards, 999 px pills everywhere | card 4, pill 999 **only** for badges | P1 |
| V13 | shadows | cyan glow `0 32px 80px -40px` | none; hairline only | **P0** |
| V14 | progress bars | gradient animated + glow | flat ink on sunken track, no animation | P1 |
| V15 | pill styling | weight 700 + drop-shadow | weight 500, tracking +0.02em, 12% tinted fill | P1 |
| V16 | button styling | gradient fill, transform scale, shadow | primary = ink fill; secondary = hairline; ghost = underline | **P0** |
| V17 | aurora / float / shine / glow pulse animations | 5+ keyframes | single pulse 1800 ms on live dot, rest forbidden | **P0** |
| V18 | noise SVG overlay | present | forbidden | **P0** |
| V19 | backdrop-filter | 12+ call sites | forbidden on cream paper | **P0** |
| V20 | card hover | `translateY(-8px)` + colour swap | tone shift only, no transform | P1 |
| V21 | decorative CAPS + letter-spacing | `text-transform: uppercase; letter-spacing: 0.1em` | only `+0.02em` on eyebrow/captions; no CAPS on titles | P1 |
| V22 | data density | 1 stat/card, 200 px min | 4-up primary row + dense tables, zero decorative padding | **P0** |
| V23 | 6 trading priorities | missing | required: PnL / metrics / DRO-ARA / combo_v1 / positions / crisis-alpha | **P0** |
| V24 | latency indicators | absent | `tick ms`, `slip bp`, `age ms` visible everywhere | **P0** |
| V25 | neuron7xLab signatures | absent | γ-indicator, ⊛ footer, CANON·2026 version line, "7" hero proportion — all mandatory per §7 | **P0** |
| V26 | timestamps | relative (`2 min ago`) | ISO-8601 UTC only per §8 | P1 |
| V27 | numeric units | absent | `--ink-tertiary` unit chip (`USD`, `ms`, `bp`) after value per §8 | P1 |
| V28 | error voice | generic "something went wrong" | invariant-named (e.g. `INV-DRO1 violated: γ=0.43 outside [0.85,1.15]`) | P1 |

## How this PR enforces the contract

Rewriting `:root{--tp-*}` values into cream-editorial equivalents so every legacy `tp-*` class inherits the paper theme automatically. Then an **overrides** layer in cascade-last position strips every remaining gradient, glow, aurora, blur, text-gradient and rebinds typography to IBM Plex with mandatory `tabular-nums`. Finally `demo.html` ships as a standalone cream editorial surface demonstrating all 6 trading priorities + all 4 neuron7xLab signatures.

## Priority → neuron7xLab section mapping (in `demo.html`)

| Priority | Surface | Section § | Notes |
|---|---|---|---|
| 1 | Live PnL feed | §9.1 hero + PnL card | `+12,847.02 USD` mono-tab, sparkline single ink stroke, area fill 6% green |
| 2 | Sharpe / IC / alpha / Max DD | §9.2 primary metrics row | exactly 4 cards; **Sharpe as "7" proportion** at `7rem` |
| 3 | DRO-ARA regime indicator | §9.3 regime / gate card | CRITICAL state, H/γ/r_s/R² inline metrics, INV-DRO1/INV-DRO2 rule footer |
| 4 | combo_v1 signal stream | §9.4 signal stream | 6 rows mono, side pill, 1 px strength bar ink |
| 5 | Position table | §9.5 position table | 6 cols: symbol/qty/avg/mark/uPnL/age |
| 6 | Crisis-alpha marker | chart reference line | `crisis-alpha 2022 · +47.6%` dashed terracotta on PnL chart |

## Signature coverage per §7

| § | Element | Placement in demo.html | Verified |
|---|---|---|---|
| 7.1 | ⊛ footer glyph | right-aligned page footer | ✔ |
| 7.2 | γ-indicator | top-right of topbar, persistent, `γ 1.02 · stable` | ✔ |
| 7.3 | version & context line | bottom-left of side-nav + left-aligned page footer | ✔ |
| 7.4 | "7" proportion | Sharpe metric rendered at `7rem` | ✔ |

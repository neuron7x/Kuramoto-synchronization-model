# GeoSync Dashboard → neuron7xLab.md Migration Plan

**Contract**: `./DESIGN.md` == `./neuron7xLab.md` (cream editorial, IBM Plex, warm minimalism).
**Previous Linear contract**: archived at `./DESIGN.md.linear.bak` (context only, not load-bearing).
**Entry date**: 2026-04-20.

## Shipped in PR #2 — truth-mode

- `ui/dashboard/live_server.py` (new) — stdlib HTTP server that exposes
  `/api/state` powered by **real** physics: `core.dro_ara.engine.geosync_observe`
  (H via DFA-1, γ = 2H + 1 INV-DRO1, r_s INV-DRO2, regime, signal), local RK4
  Kuramoto N = 128 (R(t), K/K_c), in-sample Kelly f* = μ/σ², ann. Sharpe,
  rank IC, max-drawdown, invariants watch list. Fail-closed: returns
  `{"engine":"offline","origin":{...reason}}` when any physics call fails.
- `ui/dashboard/demo.html` — replaces the prior random-walk simulation with
  `fetch('/api/state')` each second. Every panel originating from physics
  renders `—` until the engine delivers; no fabricated numbers anywhere.
  Origin line in footer names the exact module
  (`core.dro_ara.engine.geosync_observe` + `local RK4 N=128 γ=0.5 K/K_c=1.420`).
  The price source itself is a **synthetic Ornstein–Uhlenbeck spread**
  (θ = 0.06, μ = 0, σ = 0.9, seed = 42) — stationary by construction so
  DRO-ARA legitimately enters CRITICAL. A raw BTC/ETH price has a unit root
  and always maps to INVALID per the engine contract; we disclose this and
  do not fake around it.

### Truth-mode scope (load-bearing live)

- Sharpe / IC / alpha / Max DD — live or `—` (guarded: alpha requires ≥ 64 bars, Sharpe/IC require ≥ 32).
- Live PnL headline, run-rate, pct, realised/unrealised/fees/turnover.
- DRO-ARA state / H / γ / r_s / R² / trend / signal — **INV-DRO1/2 checked in UI**.
- Kuramoto R(t) / K/K_c / gate — **INV-K1/K3 checked in UI**.
- Kelly f* / applied / cap / sign — **INV-KELLY2 checked in UI**.
- γ-indicator (§7.2) — derived from H via §2.5 mapping, live.
- Invariants watch panel — live list (K1, K3, KELLY2, DRO1).
- Equity curve sparkline — redrawn from real cumulative PnL each tick.
- Engine badge in footer — `engine: live · <modules>` or `engine: offline · <reason>`.

### Explicit static labels (not truth-mode yet)

- Signal stream rows, Position ledger rows — require OMS/order-book state wiring; Phase 5.
- Slippage p50 / p95 — constants; to be replaced by real execution telemetry; Phase 4.

## Shipped in PR #1 — contract swap

| # | Change | File |
|---|---|---|
| 1 | Import contract at repo root | `neuron7xLab.md` (new, 415 lines) |

| # | Change | File |
|---|---|---|
| 1 | Import contract at repo root | `neuron7xLab.md` (new, 415 lines) |
| 2 | Install as active design contract | `DESIGN.md` (overwritten from `neuron7xLab.md`) |
| 3 | Archive prior contract | `DESIGN.md.linear.bak` (ex Linear) |
| 4 | Rewrite token dictionary under neuron7xLab tokens + legacy `--tp-*` alias bridge | `ui/dashboard/src/styles/tokens.css.js` |
| 5 | Replace Linear overrides with cream editorial overrides | `ui/dashboard/src/styles/neuron7xLab_overrides.css.js` (new) |
| 6 | Drop prior Linear overrides file | `ui/dashboard/src/styles/linear_overrides.css.js` (removed) |
| 7 | Wire new module names in style cascade | `ui/dashboard/src/core/dashboard_ui.js` |
| 8 | Replace `demo.html` with cream editorial dashboard + 4 signatures + 6 priorities | `ui/dashboard/demo.html` |
| 9 | Refresh audit | `ui/dashboard/AUDIT.md` |
| 10 | UI Contract block (carried from prior PR) | `CLAUDE.md` |

## Cascade order

```
NEURON7XLAB_TOKENS         ← first: defines --bg/--ink/--rule/--sig/--t/--s/--r + remaps --tp-*
BASE_STYLES             ← legacy tp-* utility & class rules
TABLE_STYLES
CHART_STYLES
ONBOARDING_STYLES
NEURON7XLAB_OVERRIDES      ← last: strips gradients/blur/aurora/glow + forces IBM Plex + tabular-nums
```

Every rule that declares a hard-coded cyan/violet hex, a gradient, a backdrop-filter, a text-gradient, a glow shadow, a transform on hover, or a drop-shadow filter is overridden to the cream editorial equivalent.

## neuron7xLab signature coverage (demo.html)

| § | Element | Placement | Status |
|---|---|---|---|
| 7.1 | ⊛ footer glyph | right-aligned page footer, terracotta | ✔ |
| 7.2 | γ-indicator | top-right of topbar, persistent, `γ 1.02 · stable` | ✔ |
| 7.3 | version & context line | `neuron7xLab · CANON·2026 · build 291aac9` bottom-left nav + left page footer | ✔ |
| 7.4 | "7" as proportion | Sharpe metric at `7rem`  | ✔ |

## Trading priority coverage

| Priority | Panel | File section |
|---|---|---|
| 1 | Live PnL feed | §9.1/Live PnL card with sparkline |
| 2 | Sharpe / IC / alpha / Max DD | §9.2 4-up primary metrics row |
| 3 | DRO-ARA regime indicator | §9.3 regime / gate card |
| 4 | combo_v1 signal stream | §9.4 mono table, side pill, 1 px strength bar |
| 5 | Position table | §9.5 6-column dense mono table |
| 6 | Crisis-alpha marker | `crisis-alpha 2022 · +47.6%` dashed terracotta reference line |

## Remaining work (follow-up PRs)

### Phase 2 — Sweep hard-coded hex in `*.css.js` modules

| File | Lines with cyan/violet hex | Action |
|---|---|---|
| `src/styles/base.css.js` | ~200 `#06b6d4`/`#22d3ee`/`#8b5cf6`/`#3b82f6`/`rgba(6,182,212,…)` | Replace with `var(--sig-accent)` / `var(--ink-primary)` / `var(--rule-hairline)` or remove |
| `src/styles/table.css.js` | `rgba(99,179,237,0.3)` + gradient + box-shadow | Bind via tokens |
| `src/styles/chart.css.js` | accent-soft cyan fallback | Bind via tokens |
| `src/styles/onboarding.css.js` | `#22d3ee`, `#38bdf8` | Bind via tokens |

### Phase 3 — Strip decorative artefacts at source

- Remove `.tp-app::before` aurora and `.tp-app::after` dot grid from `base.css.js`.
- Remove `@keyframes tpAurora | tpFloat | tpGradientShift | tpPulse | tpShine | tpGlowPulse | tpBorderRotate`.
- Remove `.tp-noise` utility and its SVG data URI.
- Remove all `backdrop-filter` declarations (12 call sites).
- Remove `filter: drop-shadow(...)` on text (3 call sites).

### Phase 4 — Wire priorities + signatures into live views

- **§7.2 γ-indicator** → extract from DRO-ARA engine (`core/dro_ara/engine.py → regime_state.gamma`), surface in `core/dashboard_ui.js::renderHeader` as a persistent `<span class="gamma-indicator">`.
- **§7.1 ⊛ footer glyph** → append to `renderDashboard` shell, right-aligned in page footer.
- **§7.3 version line** → inject `process.env.GIT_SHA` (or `.git/HEAD` at build time) into bottom-left of side nav.
- **§7.4 "7" proportion** → apply `7rem` treatment to hero-KPI metric in the relevant view (Sharpe on Overview, R(t) on Kuramoto view, γ on DRO-ARA view).
- `views/pnl_quotes.js` → add Sharpe / IC / alpha / Max DD row above chart (§9.2), inject crisis-alpha 2022 reference line into `renderAreaChart`.
- **New** `views/regime.js` → DRO-ARA regime gate panel consuming `core/dro_ara/engine.py` output.
- `views/signals.js` → filter `signal_type == 'combo_v1'` into dedicated stream panel, adopt 1 px strength bar.

### Phase 5 — Typography upgrade

- Ship IBM Plex Sans / Plex Mono / Plex Serif via self-host under `ui/dashboard/public/fonts/` to avoid third-party font fetch in prod.
- Set `font-feature-settings` per face (Plex Sans: `"kern","ss01"`; Plex Mono: `"tnum","zero"`).
- Remove all `font-weight: 700` throughout — replace 700 → 600, 600 → 500.
- Replace any remaining `uppercase + letter-spacing` body text with standard title case.

### Phase 6 — Playwright / a11y re-baseline

- Re-run `playwright test` to capture new screenshots under `tests/e2e/__screenshots__/`. Archive dark-era under `tests/e2e/__screenshots__/pre-neuron7xLab/`.
- Re-run `@axe-core/playwright` — contrast ratios must meet §10 (4.5:1 body, 7:1 primary metrics).
- Verify `prefers-reduced-motion: reduce` disables `n7-pulse` and tick crossfades.
- Verify ISO-8601 UTC timestamps throughout (no relative-time copy).

## Acceptance checks for this PR

- [x] `neuron7xLab.md` at repo root (415 lines).
- [x] `DESIGN.md` mirrors neuron7xLab; `DESIGN.md.linear.bak` preserved.
- [x] `CLAUDE.md` carries UI Contract block (retained from prior PR).
- [x] `demo.html` renders cream editorial dashboard with:
  - [x] all 6 trading priorities
  - [x] §7.1 ⊛ footer glyph
  - [x] §7.2 γ-indicator top-right
  - [x] §7.3 version & context line bottom-left nav + page footer
  - [x] §7.4 "7" proportion on Sharpe metric (7rem)
  - [x] tabular-nums + IBM Plex Mono on every numeric
  - [x] ISO-8601 UTC timestamps
  - [x] tick / slip / age latency chips
- [x] No drop-shadows, no gradients, no backdrop-filter in new CSS.
- [x] `prefers-reduced-motion: reduce` kills pulse animation.
- [x] `node --check` passes on new modules.
- [ ] Phases 2–6 tracked in follow-up issues.

## CANON·2026 gate (self-check per §12)

- **Remove any element → degrades?**
  - 4-up metric row · remove any card loses Sharpe/IC/alpha/Max DD axis.
  - PnL + sparkline · remove and lose equity curve + crisis-alpha reference.
  - DRO-ARA gate · remove and lose regime eligibility.
  - Signal stream · remove and lose combo_v1 surface.
  - Position table · remove and lose open exposure.
  - Execution / risk / phase triplet · remove any and lose fills-and-slip / Kelly / Kuramoto R(t).
  - γ-indicator / ⊛ / CANON·2026 line / "7" proportion · mandatory per §7; removal violates contract.
  - Verdict: every element is load-bearing.

- **Add anything → degrades?**
  - Second accent colour, hover lift, card shadow, background texture, relative-time label, placeholder mascot — each listed as forbidden per §11. Nothing outside the contract can enter without breaking the three core tests.

- **Architecture reads as only possible solution?**
  - Token layer first + overrides last is the minimal edit that rebinds the 3 746-line legacy CSS tree. A full rewrite of `base.css.js` is scheduled for Phase 2 because it touches every view test and should not be folded into the contract swap.

Gate: **PASS**. Phases 2–6 documented; removing `neuron7xLab_overrides.css.js` before Phase 2 reverts the cascade and is therefore gated.

# neuron7xLab.md
## Visual Design Contract · neuron7xLab

> Editorial research aesthetic. Warm minimalism. Academic publication meets
> engineering precision. Cream canvas, charcoal typography, zero decoration.
> The page reads like a physics paper. The dashboard reads like a well-typeset
> instrument panel.

---

## 1 · Philosophy

- **Paper, not screen.** Default mental model is a printed research page, not a
  dark trading terminal. Content earns attention through typography and
  whitespace, not through glow or saturation.
- **Information dignity.** Every datum deserves room to breathe. Density comes
  from careful hierarchy, not from packing pixels.
- **Silent infrastructure.** UI chrome is near-invisible. The work — the
  numbers, the equations, the flow — is the only thing that speaks.
- **CANON·2026 compliance.** Remove any element → degrades. Add anything →
  degrades. The layout reads as the only possible solution.

---

## 2 · Color Tokens

All colors defined as CSS custom properties. Never hard-code hex outside this
table.

### 2.1 Surface

| Token                 | Hex       | Usage                                   |
|-----------------------|-----------|-----------------------------------------|
| `--bg-canvas`         | `#F2EDE4` | Page background. Warm cream.            |
| `--bg-elevated`       | `#EBE5D9` | Cards, panels, table zebra.             |
| `--bg-sunken`         | `#E4DDCE` | Input fields, code blocks, inset areas. |
| `--bg-overlay`        | `#F7F3EC` | Modals, floating panels.                |

### 2.2 Ink (text & glyphs)

| Token                 | Hex       | Usage                                   |
|-----------------------|-----------|-----------------------------------------|
| `--ink-primary`       | `#1F1D1A` | Body text, headlines.                   |
| `--ink-secondary`     | `#4A4640` | Captions, metadata, labels.             |
| `--ink-tertiary`      | `#8A8278` | Hints, placeholders, disabled state.    |
| `--ink-inverse`       | `#F7F3EC` | Text on dark fills.                     |

### 2.3 Rule (dividers, borders)

| Token                 | Hex       | Usage                                   |
|-----------------------|-----------|-----------------------------------------|
| `--rule-hairline`     | `#CEC6B5` | 1px separators.                         |
| `--rule-medium`       | `#A89F8C` | Emphasized separators, card borders.    |
| `--rule-strong`       | `#1F1D1A` | Section terminators, print-style rules. |

### 2.4 Semantic (signals — used sparingly)

| Token                 | Hex       | Usage                                   |
|-----------------------|-----------|-----------------------------------------|
| `--sig-positive`      | `#2F6B3A` | PnL up, healthy state, gate OPEN.       |
| `--sig-negative`      | `#8A2A1E` | PnL down, error, gate BLOCKED.          |
| `--sig-caution`       | `#8F6A1F` | Warning, degraded, stale data.          |
| `--sig-neutral`       | `#3D5A7A` | Information, passive indicators.        |
| `--sig-accent`        | `#6A3416` | Terracotta — single primary accent.     |

> Accent color appears ≤ 3 times per view. Never as background fill.

### 2.5 γ-state mapping (project-specific)

Reserved for NeoSynaptex / NFI / regime indicators:

- `γ ∈ [0.95, 1.05]` → `--sig-positive` (metastable)
- `γ ∈ [0.85, 1.15]` → `--sig-caution` (drift)
- `γ outside` → `--sig-negative` (broken coherence)

---

## 3 · Typography

### 3.1 Families

```css
--font-display: "IBM Plex Sans", "Inter", ui-sans-serif, system-ui;
--font-body:    "IBM Plex Sans", "Inter", ui-sans-serif, system-ui;
--font-mono:    "IBM Plex Mono", "JetBrains Mono", ui-monospace;
--font-serif:   "IBM Plex Serif", Georgia, serif;  /* headings only, optional */
```

All numerics: `font-variant-numeric: tabular-nums;` **always**. No exceptions.

### 3.2 Scale (modular, ratio 1.25)

| Token             | Size   | Line   | Weight | Use                               |
|-------------------|--------|--------|--------|-----------------------------------|
| `--t-caption`     | 11px   | 1.4    | 500    | Metadata, timestamps, unit labels |
| `--t-body-sm`     | 13px   | 1.55   | 400    | Secondary body, table cells       |
| `--t-body`        | 15px   | 1.6    | 400    | Default body text                 |
| `--t-metric`      | 18px   | 1.2    | 500    | Inline metric values              |
| `--t-h4`          | 18px   | 1.3    | 600    | Card titles                       |
| `--t-h3`          | 22px   | 1.3    | 600    | Section titles                    |
| `--t-h2`          | 28px   | 1.25   | 600    | Page titles                       |
| `--t-h1`          | 36px   | 1.2    | 600    | Hero titles only                  |
| `--t-display`     | 48px   | 1.1    | 600    | Large metric display (rare)       |

### 3.3 Rules

- No uppercasing for headings. Use weight and size for hierarchy.
- No italic except for scientific notation (variables, vectors) or Latin
  abbreviations (`e.g.`, `cf.`).
- Letter-spacing: `-0.01em` for display sizes, `0` for body, `+0.02em` for
  captions only.
- Labels use `--ink-secondary` + `--t-caption`. Values use `--ink-primary` +
  `--t-metric` or larger.

---

## 4 · Layout & Spacing

### 4.1 Spacing scale (4px base)

```
--s-1: 4px    --s-2: 8px    --s-3: 12px   --s-4: 16px
--s-5: 24px   --s-6: 32px   --s-7: 48px   --s-8: 64px
--s-9: 96px
```

### 4.2 Grid

- 12-column grid, gutter `--s-4` (16px), max content width 1280px.
- Dashboard views: 3-column or 2-column card grid with gap `--s-5` (24px).
- Reading views (articles, docs): single column, 720px max, centered.

### 4.3 Radii

```
--r-none: 0       /* print-style hard corners — default for data tables */
--r-sm:   2px     /* inputs, small chips */
--r-md:   4px     /* cards, panels */
--r-lg:   8px     /* modals, large containers */
--r-pill: 999px   /* status badges only */
```

> **Default is `--r-none` or `--r-sm`.** The cream-paper aesthetic rejects
> rounded-everything. Soft UI is not the mode.

### 4.4 Elevation

No shadows as depth cues. Elevation is rendered through:

1. Background tonal shift (`--bg-elevated` vs `--bg-canvas`).
2. Hairline border (`1px solid --rule-hairline`).
3. Optional subtle inner line for inset feel.

Reserved — if absolutely required:
```css
--shadow-subtle: 0 1px 2px rgba(31, 29, 26, 0.06);
```

Never use `box-shadow` larger than this.

---

## 5 · Components

### 5.1 Cards

```
background: var(--bg-elevated);
border: 1px solid var(--rule-hairline);
border-radius: var(--r-md);
padding: var(--s-5);
```

Card title: `--t-h4` + `--ink-primary`. Optional eyebrow label above title:
`--t-caption` + `--ink-secondary`.

### 5.2 Metrics block

Pattern: eyebrow label (caption) → value (display or metric) → sub-delta
(caption, semantic color).

```
┌────────────────────────┐
│ SHARPE · YTD           │  ← --t-caption, --ink-secondary, letter-spacing +0.02em
│ 2.41                   │  ← --t-display, --ink-primary, tabular-nums
│ target ≥ 1.50  +0.91   │  ← --t-caption, --sig-positive on +0.91
└────────────────────────┘
```

### 5.3 Tables

- Zebra striping via `--bg-elevated` / `--bg-canvas`, not explicit borders.
- Hairline row separators only when zebra is disabled.
- Numeric columns: right-aligned, `--font-mono`, `tabular-nums`.
- Headers: `--t-caption`, `--ink-secondary`, letter-spacing `+0.02em`, no
  background fill, hairline underline.
- No hover glow. Hover row = shift one tone lighter (`--bg-sunken` → `--bg-elevated`).

### 5.4 Buttons

```
/* Primary */
background: var(--ink-primary);
color: var(--ink-inverse);
border-radius: var(--r-sm);
padding: var(--s-2) var(--s-4);
font: 500 var(--t-body-sm)/1 var(--font-body);

/* Secondary */
background: transparent;
color: var(--ink-primary);
border: 1px solid var(--rule-medium);

/* Ghost */
background: transparent;
color: var(--ink-primary);
border: 0;
text-decoration: underline;
text-decoration-thickness: 1px;
text-underline-offset: 3px;
```

No gradient buttons. Ever.

### 5.5 Badges / chips (status)

Pill shape (`--r-pill`), `--t-caption`, weight 500, letter-spacing `+0.02em`,
padding `2px 8px`. Background at 12% opacity of semantic color, text at full.

### 5.6 Inputs

```
background: var(--bg-sunken);
border: 1px solid var(--rule-hairline);
border-radius: var(--r-sm);
color: var(--ink-primary);
padding: var(--s-2) var(--s-3);
font: 400 var(--t-body)/1.4 var(--font-body);
```

Focus: `border-color: var(--ink-primary)`, no glow.

### 5.7 Charts

- Grid lines: `--rule-hairline`, 0.5px.
- Axes: `--rule-medium`, 1px.
- Axis labels: `--t-caption`, `--ink-secondary`, `--font-mono`.
- Series palette in order: `--ink-primary`, `--sig-accent`, `--sig-neutral`,
  `--sig-positive`, `--sig-negative`.
- PnL equity curve: single-color line, `--ink-primary`, 1.5px stroke. Above-water
  fill at 6% `--sig-positive`, below-water fill at 6% `--sig-negative`.
- No drop shadows, no gradients under lines, no 3D.

---

## 6 · Motion

- Default transition: `150ms cubic-bezier(0.2, 0, 0, 1)`.
- No parallax, no hover-lift, no entrance animations on page load.
- Only two legitimate uses of motion:
  1. State feedback (focus, hover tone shift) — `150ms`.
  2. Data updates (streaming numbers, PnL tick) — crossfade `120ms`, no slide.
- Live indicator: pulsing 2px dot, `--sig-positive`, `1800ms ease-in-out infinite`.

---

## 7 · neuron7xLab Signature

Mandatory on every top-level view. Non-negotiable.

### 7.1 Footer glyph

Right-aligned in page footer: `⊛ neuron7xLab` in `--t-caption`, `--ink-tertiary`,
`--font-mono`. The `⊛` character is the lab's registered glyph — circled
asterisk, read as "seven-fold star."

### 7.2 γ-indicator

Top-right of every dashboard page, persistent:

```
γ 1.02 · stable
```

Format: `--font-mono`, `--t-body-sm`, value in `--ink-primary`, state word
(`stable` / `drift` / `broken`) in corresponding semantic color. Updates live.

### 7.3 Version & context line

Bottom-left of every view:

```
neuron7xLab · CANON·2026 · build <git-sha-short>
```

`--t-caption`, `--ink-tertiary`, `--font-mono`.

### 7.4 "7" as proportion

Key accent metric on hero views (hero number, main KPI) should occupy the
viewport at a size of `7vh` or `7rem` when space allows. A quiet reference to
the lab's namesake constant.

---

## 8 · Content Voice (UI copy)

- Labels are nouns, not verbs. `EXECUTION` not `Executing`.
- All caps forbidden in titles. Reserved for eyebrow labels only.
- Timestamps: ISO-8601 UTC (`2026-04-20 18:27:41 UTC`). Never relative ("2 min
  ago") unless accompanied by absolute.
- Numerics include units in `--ink-tertiary`: `12,847.02 USD`, `12 ms`, `0.8 bp`.
- Error messages state the invariant that was violated, not a generic apology.
  Bad: "Something went wrong." Good: `invariant I₂ violated: γ = 0.43 outside [0.85, 1.15]`.
- Empty states carry a reason, not a mascot.

---

## 9 · Dashboard-Specific Patterns (GeoSync / NeoSynaptex / neurophase)

### 9.1 Hero row

Single line: `Overview · <strategy> · <symbol> · <timeframe>` in `--t-h3`,
followed by right-aligned live status: `●live · tick <ms> · slip <bp> · <ts UTC>`.

### 9.2 Primary metrics row

Exactly 4 cards: `Sharpe`, `IC`, `alpha (ann.)`, `Max DD`. No more. If more
needed, second row.

### 9.3 Regime / gate card

Mandatory for any system with a gate. Pattern:

```
┌─────────────────────────────────┐
│ DRO-ARA · regime gate           │
│ state                CRITICAL   │  ← status badge, semantic color
│ H  0.514   γ  1.02   r_s  0.97  │  ← inline metrics, mono, tabular
│ trend  CONVERGING               │
│ ─────────────────────────────── │
│ rule: γ=2H+1 · INV-DRO1    ok   │
│ rule: r_s ∈ [0,1] · INV-DRO2 ok │
│ stationary · ADF p=0.003        │
└─────────────────────────────────┘
```

### 9.4 Signal stream

Table, max 6 visible rows, monospace throughout, side column as pill badge
(`BUY` — `--sig-positive` pill, `SELL` — `--sig-negative`, `FLAT` —
`--ink-tertiary`). Strength as 1px-height bar, width proportional, color
`--ink-primary`.

### 9.5 Position table

Dense, mono, 6 columns max: `symbol · qty · avg · mark · uPnL · age`. uPnL
semantic color. Aging indicator in last column as `--t-caption` `--ink-tertiary`.

---

## 10 · Accessibility

- Minimum contrast 4.5:1 for body text. 7:1 for primary metrics.
- All interactive elements have focus state: 2px outline `--ink-primary`,
  offset 2px.
- Motion respects `prefers-reduced-motion: reduce` — disable pulse, tick
  crossfades, any transitions.
- Touch targets ≥ 44×44px even when visual element is smaller.

---

## 11 · What this design rejects

Explicitly forbidden:

- ❌ Glassmorphism, blur effects
- ❌ Gradient backgrounds, gradient text
- ❌ Neon accent colors (electric blue, hot pink, lime)
- ❌ Rounded-full everything (`--r-pill` is for status badges only)
- ❌ Drop shadows as depth cue
- ❌ Emojis as UI (use only ⊛ and γ as brand glyphs)
- ❌ Animated illustrations, Lottie files
- ❌ Placeholder avatars with gradients
- ❌ "AI-generated" aesthetics: purple-to-pink gradients, star-sparkle icons,
      generic "Figma community" card layouts
- ❌ shadcn/ui default styling without full token override

---

## 12 · Compliance check (CANON·2026 gate)

Before merging any UI PR, answer three questions:

1. **Remove any element → does the view degrade?** If no, remove it.
2. **Add anything → does the view degrade?** If no, do not add it.
3. **Does the architecture read as the only possible solution?** If no,
   redesign.

If any answer fails, the diff is rejected. No exceptions.

---

## 13 · Reference implementations

- Page background + typography: inspired by IBM Plex specimen pages, Edward
  Tufte's book designs, and the Anthropic Claude brand minimum site.
- Data table + mono numerics: inspired by Bloomberg terminal density applied
  to a paper substrate.
- Card + hairline construction: inspired by Swiss Style editorial layouts
  (Müller-Brockmann grid principles) rather than contemporary web SaaS.

---

*⊛ neuron7xLab · CANON·2026 · v1.0 · 2026-04-20*

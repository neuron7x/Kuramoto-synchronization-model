// neuron7xLab.md overrides — appended LAST in the cascade so it wins against base/table/chart/onboarding.
// Strips aurora/noise/glow/blur, rebinds typography to IBM Plex, forces cream surfaces + charcoal ink.
export const NEURON7XLAB_OVERRIDES = `
  html, body {
    background: var(--bg-canvas);
    color: var(--ink-primary);
    font-family: var(--font-body);
    font-feature-settings: "kern", "ss01";
    font-weight: 400;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  /* Canvas: kill aurora/noise/gradient/blur */
  .tp-app, .tp-app::before, .tp-app::after {
    background: var(--bg-canvas) !important;
    background-image: none !important;
    animation: none !important;
    filter: none !important;
  }
  .tp-app { padding: 0 !important; overflow: visible !important; color: var(--ink-primary) !important; }
  .tp-app::before, .tp-app::after { content: none !important; }
  .tp-shell, .tp-shell > * { background: transparent; }

  /* Cards / panels / tables: flat cream, hairline border, no blur */
  .tp-card,
  .tp-github-panel,
  .tp-live-table__viewport,
  .tp-live-table__head {
    background: var(--bg-elevated) !important;
    background-image: none !important;
    border: 1px solid var(--rule-hairline) !important;
    border-radius: var(--r-md) !important;
    box-shadow: none !important;
    backdrop-filter: none !important;
    -webkit-backdrop-filter: none !important;
    color: var(--ink-primary) !important;
  }
  .tp-card:hover,
  .tp-live-table__viewport:hover {
    transform: none !important;
    background: var(--bg-overlay) !important;
    border-color: var(--rule-medium) !important;
    box-shadow: none !important;
  }

  /* Hero: editorial surface */
  .tp-hero {
    background: var(--bg-elevated) !important;
    background-image: none !important;
    border: 1px solid var(--rule-hairline) !important;
    border-radius: var(--r-md) !important;
    box-shadow: none !important;
    backdrop-filter: none !important;
    color: var(--ink-primary) !important;
  }

  /* Text: never gradient, never drop-shadow; editorial scale */
  .tp-hero h1, .tp-hero__title,
  .tp-view__title, .tp-card__title, .tp-card h3,
  .tp-stat-value, .tp-section-title, .tp-text-gradient {
    background: transparent !important;
    background-image: none !important;
    -webkit-background-clip: initial !important;
    -webkit-text-fill-color: initial !important;
    background-clip: initial !important;
    color: var(--ink-primary) !important;
    filter: none !important;
    text-shadow: none !important;
    font-family: var(--font-display) !important;
    font-weight: 600 !important;
  }
  .tp-hero h1, .tp-hero__title {
    font-size: var(--t-h1) !important;
    line-height: 1.2 !important;
    letter-spacing: -0.01em !important;
  }
  .tp-view__title {
    font-size: var(--t-h2) !important;
    line-height: 1.25 !important;
    letter-spacing: -0.01em !important;
  }
  .tp-card__title, .tp-card h3 {
    font-size: var(--t-h4) !important;
    line-height: 1.3 !important;
    letter-spacing: 0 !important;
    color: var(--ink-primary) !important;
  }
  .tp-view__subtitle, .tp-text-subtle, .tp-section-subtitle {
    color: var(--ink-secondary) !important;
    font-weight: 400 !important;
  }

  /* Numerics everywhere: tabular + mono */
  .tp-stat, .tp-stat-value,
  .tp-live-table__cell[data-align="right"],
  .tp-live-table__cell--right,
  time, .tp-hero__stat-number,
  .tp-github-badge__value,
  .tp-quality__metric-value,
  .n7-num, .num {
    font-family: var(--font-mono) !important;
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum", "zero" !important;
    color: var(--ink-primary) !important;
  }

  /* Pills / chips: editorial badge with 12% tinted bg + full ink */
  .tp-pill, .tp-indicator {
    background: rgba(31, 29, 26, 0.06) !important;
    background-image: none !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--rule-hairline) !important;
    border-radius: var(--r-pill) !important;
    padding: 2px 8px !important;
    font-family: var(--font-body) !important;
    font-size: var(--t-caption) !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    text-transform: none !important;
    box-shadow: none !important;
  }
  .tp-pill--positive {
    color: var(--sig-positive) !important;
    background: rgba(47, 107, 58, 0.12) !important;
    border-color: rgba(47, 107, 58, 0.32) !important;
  }
  .tp-pill--negative {
    color: var(--sig-negative) !important;
    background: rgba(138, 42, 30, 0.12) !important;
    border-color: rgba(138, 42, 30, 0.32) !important;
  }
  .tp-pill--neutral {
    color: var(--ink-tertiary) !important;
    background: transparent !important;
    border-color: var(--rule-hairline) !important;
  }
  .tp-pill--warning, .tp-pill--amber {
    color: var(--sig-caution) !important;
    background: rgba(143, 106, 31, 0.12) !important;
    border-color: rgba(143, 106, 31, 0.32) !important;
  }

  /* Buttons: primary = ink fill; secondary = hairline; ghost = underline */
  .tp-button, .tp-cta, button.tp-btn {
    background: transparent !important;
    background-image: none !important;
    color: var(--ink-primary) !important;
    border: 1px solid var(--rule-medium) !important;
    border-radius: var(--r-sm) !important;
    padding: var(--s-2) var(--s-4) !important;
    font-family: var(--font-body) !important;
    font-weight: 500 !important;
    font-size: var(--t-body-sm) !important;
    box-shadow: none !important;
    transform: none !important;
    letter-spacing: 0 !important;
  }
  .tp-button--primary,
  .tp-button:first-child:not(.tp-button--ghost):not(.tp-button--secondary) {
    background: var(--ink-primary) !important;
    color: var(--ink-inverse) !important;
    border-color: var(--ink-primary) !important;
  }
  .tp-button--primary:hover { background: #000 !important; border-color: #000 !important; }
  .tp-button:hover { transform: none !important; background: var(--bg-sunken) !important; }
  .tp-button--ghost {
    border: 0 !important;
    text-decoration: underline !important;
    text-decoration-thickness: 1px !important;
    text-underline-offset: 3px !important;
    padding: var(--s-1) var(--s-2) !important;
  }

  /* Progress bars: flat ink on sunken track */
  .tp-progress {
    background: var(--bg-sunken) !important;
    border: 1px solid var(--rule-hairline) !important;
    border-radius: var(--r-pill) !important;
    box-shadow: none !important;
  }
  .tp-progress__bar {
    background: var(--ink-primary) !important;
    background-image: none !important;
    box-shadow: none !important;
    animation: none !important;
  }

  /* Tables: editorial density + mono numerics */
  .tp-live-table__table { min-width: 560px !important; color: var(--ink-primary) !important; }
  .tp-live-table__head { background: transparent !important; }
  .tp-live-table__head th {
    color: var(--ink-secondary) !important;
    font-family: var(--font-body) !important;
    font-weight: 500 !important;
    font-size: var(--t-caption) !important;
    letter-spacing: 0.02em !important;
    text-transform: none !important;
    padding: var(--s-2) var(--s-3) !important;
    border-bottom: 1px solid var(--rule-medium) !important;
    background: transparent !important;
  }
  .tp-live-table__cell {
    padding: var(--s-2) var(--s-3) !important;
    font-size: var(--t-body-sm) !important;
    color: var(--ink-primary) !important;
    border-bottom: 1px solid var(--rule-hairline) !important;
  }
  .tp-live-table__row:nth-child(odd) { background: transparent !important; }
  .tp-live-table__row:nth-child(even) { background: rgba(31, 29, 26, 0.03) !important; }
  .tp-live-table__row:hover { background: var(--bg-overlay) !important; }

  /* Kill all decorative motion and overlays */
  .tp-card::before, .tp-card::after,
  .tp-card--interactive::before,
  .tp-border-glow::before, .tp-noise::after,
  .tp-hero__visual, .tp-hero__orb, .tp-hero__grid,
  .tp-indicator--live::before {
    animation: none !important;
  }
  .tp-hero__orb, .tp-hero__grid, .tp-noise::after { display: none !important; }

  /* Eyebrow / tiny labels */
  .tp-hero__eyebrow, .tp-stat-label, .tp-caption {
    color: var(--ink-secondary) !important;
    font-family: var(--font-body) !important;
    font-size: var(--t-caption) !important;
    font-weight: 500 !important;
    letter-spacing: 0.02em !important;
    text-transform: none !important;
  }

  /* Focus: editorial 2px outline */
  :focus-visible {
    outline: 2px solid var(--ink-primary) !important;
    outline-offset: 2px !important;
    box-shadow: none !important;
    border-radius: var(--r-sm);
  }

  /* Selection */
  ::selection { background: rgba(106, 52, 22, 0.20); color: var(--ink-primary); }
`;

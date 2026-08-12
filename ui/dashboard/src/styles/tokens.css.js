// neuron7xLab.md design tokens — single source of truth per ./DESIGN.md at repo root.
// Cream editorial aesthetic (warm minimalism, IBM Plex, charcoal ink on cream canvas).
// Every legacy --tp-* alias is remapped to the cream system so existing tp-* utility
// classes inherit the research-paper theme automatically.
export const NEURON7XLAB_TOKENS = `
  :root {
    color-scheme: light;

    /* ========== neuron7xLab canonical tokens ========== */

    /* 2.1 Surface */
    --bg-canvas: #F2EDE4;
    --bg-elevated: #EBE5D9;
    --bg-sunken: #E4DDCE;
    --bg-overlay: #F7F3EC;

    /* 2.2 Ink */
    --ink-primary: #1F1D1A;
    --ink-secondary: #4A4640;
    --ink-tertiary: #8A8278;
    --ink-inverse: #F7F3EC;

    /* 2.3 Rule */
    --rule-hairline: #CEC6B5;
    --rule-medium: #A89F8C;
    --rule-strong: #1F1D1A;

    /* 2.4 Semantic (used sparingly) */
    --sig-positive: #2F6B3A;
    --sig-negative: #8A2A1E;
    --sig-caution: #8F6A1F;
    --sig-neutral: #3D5A7A;
    --sig-accent: #6A3416;

    /* 3.1 Type families */
    --font-display: "IBM Plex Sans", "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    --font-body: "IBM Plex Sans", "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    --font-mono: "IBM Plex Mono", "JetBrains Mono", ui-monospace, "SF Mono", Menlo, Consolas, monospace;
    --font-serif: "IBM Plex Serif", Georgia, "Times New Roman", serif;

    /* 3.2 Type scale */
    --t-caption: 11px;
    --t-body-sm: 13px;
    --t-body: 15px;
    --t-metric: 18px;
    --t-h4: 18px;
    --t-h3: 22px;
    --t-h2: 28px;
    --t-h1: 36px;
    --t-display: 48px;

    /* 4.1 Spacing (4px base) */
    --s-1: 4px;
    --s-2: 8px;
    --s-3: 12px;
    --s-4: 16px;
    --s-5: 24px;
    --s-6: 32px;
    --s-7: 48px;
    --s-8: 64px;
    --s-9: 96px;

    /* 4.3 Radii */
    --r-none: 0;
    --r-sm: 2px;
    --r-md: 4px;
    --r-lg: 8px;
    --r-pill: 999px;

    /* 4.4 Elevation (reserved, rarely used) */
    --shadow-subtle: 0 1px 2px rgba(31, 29, 26, 0.06);

    /* 6 Motion */
    --motion-base: 150ms cubic-bezier(0.2, 0, 0, 1);
    --motion-tick: 120ms cubic-bezier(0.2, 0, 0, 1);

    /* ========== Legacy alias bridge: --tp-* → neuron7xLab tokens ========== */
    /* Surfaces: swap dark → cream paper stack */
    --tp-surface-900: var(--bg-canvas);
    --tp-surface-800: var(--bg-elevated);
    --tp-surface-700: var(--bg-elevated);
    --tp-surface-600: var(--bg-sunken);
    --tp-surface-glass: var(--bg-elevated);

    /* Borders: hairline-first, never tinted */
    --tp-border-strong: var(--rule-medium);
    --tp-border-soft: var(--rule-hairline);
    --tp-border-glow: var(--rule-hairline);

    /* Text: charcoal on cream, never gradient */
    --tp-text-muted: var(--ink-primary);
    --tp-text-subtle: var(--ink-secondary);
    --tp-text-dim: var(--ink-tertiary);

    /* Accent: single terracotta, not multi-chromatic */
    --tp-accent: var(--sig-accent);
    --tp-accent-strong: var(--sig-accent);
    --tp-accent-vibrant: var(--sig-accent);
    --tp-accent-soft: rgba(106, 52, 22, 0.10);

    /* Status: editorial green/red */
    --tp-positive: var(--sig-positive);
    --tp-positive-glow: var(--sig-positive);
    --tp-positive-soft: rgba(47, 107, 58, 0.12);
    --tp-negative: var(--sig-negative);
    --tp-negative-glow: var(--sig-negative);
    --tp-negative-soft: rgba(138, 42, 30, 0.12);
    --tp-warning: var(--sig-caution);
    --tp-warning-glow: var(--sig-caution);
    --tp-warning-soft: rgba(143, 106, 31, 0.12);

    /* Focus */
    --tp-focus-ring: var(--ink-primary);
    --tp-focus-ring-subtle: rgba(31, 29, 26, 0.20);

    /* Gradients collapse to flat ink / cream — contract forbids gradient backgrounds */
    --tp-gradient-primary: var(--ink-primary);
    --tp-gradient-accent: var(--sig-accent);
    --tp-gradient-warm: var(--sig-caution);
    --tp-gradient-success: var(--sig-positive);
    --tp-gradient-purple: var(--ink-primary);
    --tp-gradient-cosmic: var(--bg-canvas);
    --tp-gradient-glass: var(--bg-elevated);

    /* Shadows collapse — hairline border carries depth */
    --tp-shadow-glow: none;
    --tp-shadow-ambient: none;
    --tp-shadow-card: none;

    /* Kill decorative noise */
    --tp-noise-opacity: 0;
    --tp-noise-pattern: none;

    /* Motion curves collapse to single editorial curve */
    --tp-transition-smooth: cubic-bezier(0.2, 0, 0, 1);
    --tp-transition-bounce: cubic-bezier(0.2, 0, 0, 1);
    --tp-transition-spring: cubic-bezier(0.2, 0, 0, 1);
  }

  @media (prefers-reduced-motion: reduce) {
    :root {
      --motion-base: 0ms;
      --motion-tick: 0ms;
    }
  }
`;

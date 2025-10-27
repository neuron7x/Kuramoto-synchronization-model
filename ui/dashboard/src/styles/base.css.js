export const BASE_STYLES = `
  :root {
    color-scheme: dark;
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    --tp-surface-900: rgba(15, 23, 42, 0.92);
    --tp-surface-800: rgba(15, 23, 42, 0.78);
    --tp-surface-700: rgba(15, 23, 42, 0.62);
    --tp-border-strong: rgba(148, 163, 184, 0.6);
    --tp-border-soft: rgba(148, 163, 184, 0.28);
    --tp-text-muted: rgba(226, 232, 240, 0.92);
    --tp-text-subtle: rgba(203, 213, 225, 0.9);
    --tp-accent: #38bdf8;
    --tp-accent-strong: #2563eb;
    --tp-positive: #4ade80;
    --tp-negative: #f87171;
    --tp-focus-ring: #38bdf8;
    --tp-focus-ring-subtle: rgba(56, 189, 248, 0.35);
  }

  :focus-visible {
    outline: 2px solid var(--tp-focus-ring);
    outline-offset: 3px;
  }

  .tp-text-muted {
    color: var(--tp-text-muted);
  }

  .tp-text-subtle {
    color: var(--tp-text-subtle);
  }

  @keyframes tpAurora {
    0% {
      transform: translate3d(-15%, -25%, 0) scale(1.05) rotate(0deg);
      opacity: 0.35;
    }
    50% {
      transform: translate3d(10%, -10%, 0) scale(1.1) rotate(12deg);
      opacity: 0.5;
    }
    100% {
      transform: translate3d(-5%, 0%, 0) scale(1.08) rotate(-4deg);
      opacity: 0.35;
    }
  }

  @keyframes tpBadgePulse {
    0%,
    100% {
      box-shadow: 0 0 0 0 rgba(56, 189, 248, 0.45);
    }
    70% {
      box-shadow: 0 0 0 8px rgba(56, 189, 248, 0);
    }
  }

  @keyframes tpGlowSweep {
    0% {
      transform: translateX(-100%);
    }
    100% {
      transform: translateX(100%);
    }
  }

  @keyframes tpHeroFloat {
    0%,
    100% {
      transform: translate3d(-4%, -2%, 0) scale(1.02);
    }
    50% {
      transform: translate3d(6%, 4%, 0) scale(1.08);
    }
  }

  @keyframes tpHeroPulse {
    0%,
    100% {
      opacity: 0.35;
    }
    50% {
      opacity: 0.65;
    }
  }

  @keyframes tpHeroGrid {
    0% {
      background-position: 0% 0%;
    }
    100% {
      background-position: 120% 120%;
    }
  }

  .tp-app {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    min-height: 100vh;
    background: radial-gradient(circle at top left, #0d1b2a, #010409);
    color: #f8fafc;
    overflow: hidden;
  }

  .tp-skip-link {
    position: absolute;
    top: 1rem;
    left: 1.5rem;
    transform: translateY(-200%);
    padding: 0.65rem 1.25rem;
    border-radius: 10px;
    background: var(--tp-accent-strong);
    color: #f8fafc;
    font-weight: 600;
    letter-spacing: 0.02em;
    transition: transform 0.2s ease;
    z-index: 30;
  }

  .tp-skip-link:focus-visible {
    transform: translateY(0);
    box-shadow: 0 0 0 4px rgba(2, 6, 23, 0.45);
  }

  .tp-app::before {
    content: '';
    position: fixed;
    inset: -40%;
    background: conic-gradient(from 180deg at 50% 50%, rgba(56, 189, 248, 0.15), rgba(37, 99, 235, 0.05), rgba(56, 189, 248, 0.15));
    filter: blur(120px);
    pointer-events: none;
    animation: tpAurora 28s ease-in-out infinite alternate;
    z-index: 0;
  }

  @media (min-width: 1080px) {
    .tp-app {
      grid-template-columns: 280px minmax(0, 1fr);
    }
  }

  .tp-shell {
    position: relative;
    display: grid;
    grid-template-rows: auto 1fr;
    gap: 1.5rem;
    padding: 2rem;
    z-index: 1;
  }

  .tp-nav {
    position: relative;
    display: flex;
    flex-direction: column;
    background: rgba(15, 23, 42, 0.65);
    border-right: 1px solid var(--tp-border-soft);
    backdrop-filter: blur(24px);
    z-index: 2;
  }

  .tp-nav__mobile-bar {
    display: none;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.5rem;
    border-bottom: 1px solid var(--tp-border-soft);
    background: rgba(15, 23, 42, 0.8);
  }

  .tp-nav__brand {
    font-size: 1.05rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: rgba(226, 232, 240, 0.85);
  }

  .tp-nav__panel {
    display: grid;
    gap: 1.5rem;
    padding: 2rem 2rem 2.5rem 2rem;
  }

  .tp-nav__panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
  }

  .tp-nav__title {
    font-size: clamp(1.35rem, 2.5vw, 1.75rem);
    font-weight: 700;
    letter-spacing: -0.01em;
    margin: 0;
  }

  .tp-nav__links {
    display: grid;
    gap: 0.75rem;
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .tp-nav__link:focus-visible,
  .tp-nav__toggle:focus-visible,
  .tp-nav__close:focus-visible,
  .tp-nav__locale-select:focus-visible {
    outline: 2px solid var(--tp-focus-ring);
    outline-offset: 3px;
    box-shadow: 0 0 0 4px var(--tp-focus-ring-subtle);
  }

  .tp-nav__locale {
    display: grid;
    gap: 0.4rem;
    padding-top: 1rem;
    border-top: 1px solid var(--tp-border-soft);
  }

  .tp-nav__locale-label {
    font-size: 0.8rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: rgba(226, 232, 240, 0.65);
  }

  .tp-nav__locale-select {
    appearance: none;
    width: 100%;
    padding: 0.65rem 0.85rem;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.35);
    border: 1px solid rgba(148, 163, 184, 0.25);
    color: inherit;
    font-size: 0.95rem;
    line-height: 1.2;
    box-shadow: inset 0 1px 2px rgba(2, 6, 23, 0.35);
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
  }

  .tp-nav__locale-select:focus {
    outline: none;
    border-color: rgba(56, 189, 248, 0.6);
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.35);
  }

  .tp-nav__locale-helper {
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.65);
  }

  .tp-nav__link {
    display: inline-flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-radius: 12px;
    position: relative;
    background: rgba(15, 23, 42, 0.35);
    border: 1px solid transparent;
    color: inherit;
    text-decoration: none;
    transition: background 0.3s ease, border-color 0.3s ease, transform 0.3s ease;
    overflow: hidden;
  }

  .tp-nav__link:hover {
    background: rgba(56, 189, 248, 0.2);
    border-color: rgba(56, 189, 248, 0.35);
    transform: translateX(4px);
  }

  .tp-nav__link--active {
    background: rgba(56, 189, 248, 0.28);
    border-color: rgba(56, 189, 248, 0.55);
    color: #f0f9ff;
  }

  .tp-nav__link--active::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(120deg, rgba(56, 189, 248, 0.35), rgba(37, 99, 235, 0));
    opacity: 0.75;
    mix-blend-mode: screen;
    transform: translateX(-100%);
    animation: tpGlowSweep 1.8s ease-in-out infinite;
    pointer-events: none;
  }

  .tp-nav__badge {
    font-size: 0.75rem;
    font-weight: 600;
    padding: 0.25rem 0.6rem;
    border-radius: 999px;
    background: rgba(37, 99, 235, 0.65);
    color: #f8fafc;
    position: relative;
    animation: tpBadgePulse 4s ease-in-out infinite;
  }

  .tp-nav__toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.6rem;
    padding: 0.55rem 1rem;
    border-radius: 999px;
    border: 1px solid var(--tp-border-strong);
    background: rgba(15, 23, 42, 0.82);
    color: #f8fafc;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    cursor: pointer;
    transition: background 0.3s ease, border-color 0.3s ease, transform 0.3s ease;
  }

  .tp-nav__toggle:hover {
    background: rgba(37, 99, 235, 0.4);
    border-color: rgba(37, 99, 235, 0.75);
    transform: translateY(-1px);
  }

  .tp-nav__toggle-text {
    font-size: 0.9rem;
  }

  .tp-nav__toggle-bars,
  .tp-nav__toggle-bars::before,
  .tp-nav__toggle-bars::after {
    display: block;
    width: 20px;
    height: 2px;
    border-radius: 999px;
    background: currentColor;
    transition: transform 0.3s ease, opacity 0.3s ease;
    content: '';
    position: relative;
  }

  .tp-nav__toggle-bars::before {
    position: absolute;
    top: -6px;
    left: 0;
    content: '';
  }

  .tp-nav__toggle-bars::after {
    position: absolute;
    top: 6px;
    left: 0;
    content: '';
  }

  .tp-nav[data-enhanced='true'][data-state='expanded'] .tp-nav__toggle-bars {
    transform: rotate(45deg);
  }

  .tp-nav[data-enhanced='true'][data-state='expanded'] .tp-nav__toggle-bars::before {
    transform: rotate(-90deg) translate(-6px, 0);
  }

  .tp-nav[data-enhanced='true'][data-state='expanded'] .tp-nav__toggle-bars::after {
    opacity: 0;
  }

  .tp-nav__close {
    display: none;
    align-items: center;
    justify-content: center;
    width: 2.25rem;
    height: 2.25rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.35);
    background: rgba(15, 23, 42, 0.45);
    color: rgba(226, 232, 240, 0.85);
    cursor: pointer;
    transition: background 0.3s ease, border-color 0.3s ease, transform 0.3s ease;
  }

  .tp-nav__close:hover {
    background: rgba(56, 189, 248, 0.2);
    border-color: rgba(56, 189, 248, 0.55);
    transform: translateY(-1px);
  }

  .tp-nav__close span {
    font-size: 1.35rem;
    line-height: 1;
  }

  .tp-nav__overlay {
    display: none;
  }

  .tp-nav[data-enhanced='true'][data-state='expanded'] .tp-nav__overlay {
    display: none;
  }

  .tp-sr-only {
    position: absolute !important;
    width: 1px !important;
    height: 1px !important;
    padding: 0 !important;
    margin: -1px !important;
    overflow: hidden !important;
    clip: rect(0, 0, 0, 0) !important;
    white-space: nowrap !important;
    border: 0 !important;
  }

  .tp-view {
    position: relative;
    background: var(--tp-surface-900);
    border: 1px solid var(--tp-border-soft);
    border-radius: 20px;
    padding: 1.75rem;
    box-shadow: 0 24px 48px -32px rgba(15, 23, 42, 0.8);
    transition: transform 0.45s ease, box-shadow 0.45s ease, border-color 0.45s ease;
    overflow: hidden;
  }

  .tp-view::after {
    content: '';
    position: absolute;
    inset: -40% -60% auto -60%;
    height: 120%;
    background: radial-gradient(circle at top, rgba(56, 189, 248, 0.18), rgba(56, 189, 248, 0));
    opacity: 0.6;
    pointer-events: none;
    transition: transform 0.6s ease, opacity 0.6s ease;
  }

  .tp-view:hover {
    transform: translateY(-4px);
    border-color: rgba(56, 189, 248, 0.35);
    box-shadow: 0 32px 60px -30px rgba(37, 99, 235, 0.55);
  }

  .tp-view:hover::after {
    transform: translateY(12%);
    opacity: 0.85;
  }

  .tp-view--overview {
    display: grid;
    gap: 2rem;
  }

  .tp-hero {
    position: relative;
    display: grid;
    gap: 1.75rem;
    padding: clamp(1.75rem, 3vw, 2.5rem);
    border-radius: 24px;
    overflow: hidden;
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(37, 99, 235, 0.15));
    border: 1px solid rgba(56, 189, 248, 0.35);
    box-shadow: 0 28px 60px -32px rgba(37, 99, 235, 0.45);
  }

  .tp-hero::after {
    content: '';
    position: absolute;
    inset: 12% 10% -30% 10%;
    background: radial-gradient(circle at top, rgba(56, 189, 248, 0.45), transparent 60%);
    filter: blur(42px);
    opacity: 0.6;
    pointer-events: none;
    animation: tpHeroPulse 12s ease-in-out infinite alternate;
  }

  .tp-hero__content {
    position: relative;
    z-index: 2;
    display: grid;
    gap: 1.1rem;
    max-width: 28rem;
  }

  .tp-hero__eyebrow {
    margin: 0;
    font-size: 0.85rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(226, 232, 240, 0.75);
  }

  .tp-hero__title {
    margin: 0;
    font-size: clamp(2.05rem, 4vw, 2.75rem);
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .tp-hero__subtitle {
    margin: 0;
    font-size: 1rem;
    color: rgba(226, 232, 240, 0.8);
    max-width: 26ch;
  }

  .tp-hero__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
    align-items: center;
  }

  .tp-hero__stats {
    display: grid;
    gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    margin: 0;
    padding: 1.1rem 1.25rem;
    border-radius: 18px;
    background: rgba(15, 23, 42, 0.45);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.22);
    backdrop-filter: blur(16px);
  }

  .tp-hero__stat {
    display: grid;
    gap: 0.35rem;
  }

  .tp-hero__stat-label {
    margin: 0;
    font-size: 0.75rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.8);
  }

  .tp-hero__stat-value {
    display: flex;
    align-items: baseline;
    gap: 0.35rem;
    margin: 0;
  }

  .tp-hero__stat-number {
    font-size: 1.8rem;
    font-weight: 700;
    letter-spacing: -0.015em;
  }

  .tp-hero__stat-unit {
    font-size: 0.85rem;
    color: rgba(226, 232, 240, 0.75);
    text-transform: uppercase;
    letter-spacing: 0.1em;
  }

  .tp-hero__stat-trend {
    margin: 0;
    font-size: 0.85rem;
    font-weight: 600;
    color: rgba(148, 163, 184, 0.85);
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
  }

  .tp-hero__stat-trend::before {
    content: '●';
    font-size: 0.55rem;
    color: currentColor;
  }

  .tp-hero__stat-trend--positive {
    color: rgba(74, 222, 128, 0.85);
  }

  .tp-hero__stat-trend--negative {
    color: rgba(248, 113, 113, 0.85);
  }

  .tp-hero__stat-trend--neutral {
    color: rgba(148, 163, 184, 0.85);
  }

  .tp-hero__repo {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.45rem 0.9rem;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.35);
    box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.25);
    font-weight: 600;
    font-size: 0.95rem;
  }

  .tp-hero__action {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.55rem 1.15rem;
    border-radius: 999px;
    background: linear-gradient(120deg, rgba(56, 189, 248, 0.95), rgba(37, 99, 235, 0.85));
    color: #0f172a;
    font-weight: 600;
    text-decoration: none;
    box-shadow: 0 14px 28px -18px rgba(56, 189, 248, 0.8);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
  }

  .tp-hero__action:hover {
    transform: translateY(-3px);
    box-shadow: 0 18px 36px -18px rgba(56, 189, 248, 0.9);
  }

  .tp-hero__action:focus-visible {
    outline: 2px solid rgba(37, 99, 235, 0.85);
    outline-offset: 2px;
  }

  .tp-hero__action-icon {
    width: 1.05rem;
    height: 1.05rem;
  }

  .tp-hero__visual {
    position: absolute;
    inset: 0;
    pointer-events: none;
    overflow: hidden;
  }

  .tp-hero__orb {
    position: absolute;
    border-radius: 999px;
    filter: blur(12px);
    opacity: 0.6;
    animation: tpHeroFloat 16s ease-in-out infinite;
  }

  .tp-hero__orb--primary {
    width: 40%;
    height: 60%;
    top: -10%;
    right: -12%;
    background: radial-gradient(circle at center, rgba(56, 189, 248, 0.65), rgba(37, 99, 235, 0));
  }

  .tp-hero__orb--secondary {
    width: 55%;
    height: 55%;
    bottom: -18%;
    left: -14%;
    background: radial-gradient(circle at center, rgba(56, 189, 248, 0.45), rgba(14, 116, 144, 0));
    animation-delay: -6s;
  }

  .tp-hero__grid {
    position: absolute;
    inset: 0;
    background-image: linear-gradient(
        rgba(148, 163, 184, 0.12) 1px,
        transparent 1px
      ),
      linear-gradient(
        90deg,
        rgba(148, 163, 184, 0.12) 1px,
        transparent 1px
      );
    background-size: 48px 48px;
    opacity: 0.35;
    animation: tpHeroGrid 22s linear infinite;
  }

  .tp-overview-grid {
    align-items: stretch;
  }

  .tp-github-panel {
    display: grid;
    gap: 1.25rem;
  }

  .tp-momentum {
    position: relative;
    overflow: hidden;
  }

  .tp-momentum::after {
    content: '';
    position: absolute;
    inset: -60% -20% auto -20%;
    height: 220px;
    background: radial-gradient(circle at top, rgba(56, 189, 248, 0.25), rgba(15, 23, 42, 0));
    opacity: 0.7;
    pointer-events: none;
  }

  .tp-momentum__list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 1rem;
  }

  .tp-momentum__item {
    position: relative;
    display: grid;
    gap: 0.45rem;
    padding: 1rem 1.25rem;
    border-radius: 16px;
    background: rgba(15, 23, 42, 0.55);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.12);
  }

  .tp-momentum__item::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.18), transparent 60%);
    opacity: 0;
    transition: opacity 0.4s ease;
    pointer-events: none;
  }

  .tp-momentum__item:hover::before {
    opacity: 1;
  }

  .tp-momentum__item-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 0.5rem;
  }

  .tp-momentum__label {
    font-size: 0.95rem;
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  .tp-momentum__trend {
    font-size: 0.85rem;
    font-weight: 600;
    color: rgba(148, 163, 184, 0.9);
  }

  .tp-momentum__trend--positive {
    color: rgba(74, 222, 128, 0.9);
  }

  .tp-momentum__trend--negative {
    color: rgba(248, 113, 113, 0.9);
  }

  .tp-momentum__trend--neutral {
    color: rgba(148, 163, 184, 0.9);
  }

  .tp-momentum__value {
    font-size: 1.35rem;
    font-weight: 600;
  }

  .tp-momentum__hint {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.8);
  }

  .tp-github-panel--stretch {
    grid-row: span 2;
  }

  .tp-github-badges {
    display: grid;
    gap: 1.15rem;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    margin: 0;
  }

  .tp-github-badge {
    position: relative;
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 1rem;
    padding: 1rem 1.25rem;
    border-radius: 18px;
    background: rgba(15, 23, 42, 0.55);
    border: 1px solid rgba(56, 189, 248, 0.25);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.12);
    overflow: hidden;
  }

  .tp-github-badge::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(120deg, rgba(56, 189, 248, 0.2), transparent 60%);
    mix-blend-mode: screen;
    opacity: 0;
    transition: opacity 0.4s ease;
  }

  .tp-github-badge:hover::after {
    opacity: 1;
  }

  .tp-github-badge__icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 2.75rem;
    height: 2.75rem;
    border-radius: 18px;
    background: rgba(56, 189, 248, 0.16);
    color: rgba(56, 189, 248, 0.95);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.35);
  }

  .tp-github-badge__icon svg {
    width: 1.5rem;
    height: 1.5rem;
  }

  .tp-github-badge__content {
    display: grid;
    gap: 0.25rem;
  }

  .tp-github-badge__label {
    margin: 0;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: rgba(148, 163, 184, 0.8);
  }

  .tp-github-badge__value {
    margin: 0;
    font-size: 1.6rem;
    font-weight: 700;
  }

  .tp-github-badge__hint {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.75);
  }

  .tp-github-release {
    display: grid;
    gap: 1.25rem;
  }

  .tp-github-release__tag {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
  }

  .tp-github-release__tag .tp-pill {
    background: rgba(56, 189, 248, 0.16);
    color: #f0f9ff;
  }

  .tp-github-release__tag strong {
    font-size: 1.05rem;
  }

  .tp-github-release__metrics {
    display: grid;
    gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  }

  .tp-github-release__metrics dt {
    margin: 0;
    font-size: 0.9rem;
    color: rgba(148, 163, 184, 0.75);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }

  .tp-github-release__metrics dd {
    margin: 0.35rem 0 0;
    font-size: 1.35rem;
    font-weight: 600;
  }

  .tp-github-languages {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 1rem;
  }

  .tp-github-language {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.75rem;
    align-items: center;
  }

  .tp-github-language__label {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    font-weight: 600;
  }

  .tp-github-language__swatch {
    width: 0.85rem;
    height: 0.85rem;
    border-radius: 999px;
    background: var(--tp-language-color, #38bdf8);
    box-shadow: 0 0 0 3px rgba(15, 23, 42, 0.6);
  }

  .tp-progress--slim {
    height: 0.45rem;
  }

  .tp-github-language__value {
    font-weight: 600;
    font-size: 0.95rem;
  }

  .tp-github-workflows {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    align-items: center;
  }

  .tp-github-workflow {
    display: inline-flex;
    border-radius: 12px;
    overflow: hidden;
    background: rgba(15, 23, 42, 0.6);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
  }

  .tp-github-workflow:hover {
    transform: translateY(-2px);
    box-shadow: 0 16px 30px -20px rgba(56, 189, 248, 0.6);
  }

  .tp-github-workflow img {
    display: block;
    height: 28px;
  }

  .tp-view--community {
    display: grid;
    gap: 2rem;
  }

  .tp-community__grid {
    align-items: stretch;
  }

  .tp-community__hero {
    position: relative;
    display: grid;
    gap: 1.5rem;
    padding: clamp(1.75rem, 3vw, 2.5rem);
    border-radius: 24px;
    background: linear-gradient(140deg, rgba(56, 189, 248, 0.22), rgba(59, 130, 246, 0.18));
    border: 1px solid rgba(56, 189, 248, 0.4);
    overflow: hidden;
  }

  .tp-community__hero-content {
    position: relative;
    z-index: 2;
    display: grid;
    gap: 1rem;
    max-width: 32rem;
  }

  .tp-community__hero-eyebrow {
    margin: 0;
    font-size: 0.85rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(226, 232, 240, 0.75);
  }

  .tp-community__hero-title {
    margin: 0;
    font-size: clamp(2rem, 4.2vw, 2.85rem);
    font-weight: 700;
    letter-spacing: -0.02em;
  }

  .tp-community__hero-subtitle {
    margin: 0;
    font-size: 1rem;
    color: rgba(226, 232, 240, 0.82);
    max-width: 36ch;
  }

  .tp-community__hero-actions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
  }

  .tp-community__hero-cta {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.6rem 1.3rem;
    border-radius: 999px;
    background: linear-gradient(120deg, rgba(56, 189, 248, 0.95), rgba(37, 99, 235, 0.85));
    color: #0f172a;
    font-weight: 600;
    text-decoration: none;
    box-shadow: 0 16px 30px -20px rgba(56, 189, 248, 0.8);
    transition: transform 0.3s ease, box-shadow 0.3s ease;
  }

  .tp-community__hero-cta:hover {
    transform: translateY(-2px);
    box-shadow: 0 20px 44px -22px rgba(56, 189, 248, 0.9);
  }

  .tp-community__hero-secondary {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.55rem 1.1rem;
    border-radius: 999px;
    border: 1px solid rgba(148, 163, 184, 0.5);
    color: rgba(226, 232, 240, 0.9);
    text-decoration: none;
    background: rgba(15, 23, 42, 0.45);
    transition: background 0.3s ease, border-color 0.3s ease, transform 0.3s ease;
  }

  .tp-community__hero-secondary:hover {
    background: rgba(56, 189, 248, 0.15);
    border-color: rgba(56, 189, 248, 0.45);
    transform: translateY(-2px);
  }

  .tp-community__hero-channels {
    display: inline-flex;
    flex-wrap: wrap;
    gap: 0.6rem;
  }

  .tp-community__hero-channel {
    display: inline-flex;
    align-items: center;
    padding: 0.35rem 0.75rem;
    border-radius: 999px;
    background: rgba(15, 23, 42, 0.55);
    color: rgba(226, 232, 240, 0.85);
    text-decoration: none;
    font-size: 0.85rem;
    border: 1px solid rgba(148, 163, 184, 0.3);
  }

  .tp-community__hero-visual {
    position: absolute;
    inset: 0;
    pointer-events: none;
  }

  .tp-community__hero-orb {
    position: absolute;
    border-radius: 999px;
    filter: blur(12px);
    opacity: 0.65;
    animation: tpHeroFloat 20s ease-in-out infinite;
  }

  .tp-community__hero-orb--primary {
    width: 45%;
    height: 60%;
    top: -12%;
    right: -14%;
    background: radial-gradient(circle at center, rgba(56, 189, 248, 0.55), rgba(37, 99, 235, 0));
  }

  .tp-community__hero-orb--secondary {
    width: 55%;
    height: 55%;
    bottom: -18%;
    left: -16%;
    background: radial-gradient(circle at center, rgba(59, 130, 246, 0.4), rgba(14, 116, 144, 0));
    animation-delay: -6s;
  }

  .tp-community__metrics {
    gap: 1.25rem;
  }

  .tp-community__metrics-grid {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  }

  .tp-community__filters {
    display: grid;
    gap: 0.5rem;
    margin-bottom: 1.25rem;
  }

  .tp-community__filters-toolbar {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .tp-community__filter {
    appearance: none;
    border: 1px solid rgba(148, 163, 184, 0.3);
    background: rgba(15, 23, 42, 0.3);
    color: inherit;
    border-radius: 999px;
    padding: 0.45rem 0.95rem;
    font-size: 0.8rem;
    letter-spacing: 0.02em;
    transition: background 0.3s ease, border-color 0.3s ease, transform 0.3s ease;
    cursor: pointer;
  }

  .tp-community__filter:hover,
  .tp-community__filter:focus-visible {
    border-color: rgba(56, 189, 248, 0.5);
    transform: translateY(-1px);
    outline: none;
  }

  .tp-community__filter--active {
    background: linear-gradient(90deg, rgba(56, 189, 248, 0.25), rgba(37, 99, 235, 0.4));
    border-color: rgba(37, 99, 235, 0.6);
    box-shadow: 0 4px 12px -8px rgba(37, 99, 235, 0.7);
  }

  .tp-community__filters-helper {
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.7);
  }

  .tp-community__metric {
    display: grid;
    gap: 0.4rem;
    padding: 1rem 1.25rem;
    border-radius: 16px;
    background: rgba(15, 23, 42, 0.55);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.18);
  }

  .tp-community__metric-label {
    font-size: 0.75rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.8);
  }

  .tp-community__metric-value {
    font-size: 1.6rem;
    font-weight: 700;
    letter-spacing: -0.015em;
  }

  .tp-community__metric-caption {
    margin: 0;
    font-size: 0.85rem;
    color: var(--tp-text-subtle);
  }

  .tp-community__programs-list,
  .tp-community__resource-list,
  .tp-community__event-list,
  .tp-community__champion-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 1rem;
  }

  .tp-community__program {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.15);
  }

  .tp-community__program:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .tp-community__program-title {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }

  .tp-community__program-description {
    margin: 0.35rem 0 0 0;
    color: var(--tp-text-muted);
    max-width: 38ch;
  }

  .tp-community__program-link {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-weight: 600;
    color: rgba(125, 211, 252, 0.95);
    text-decoration: none;
  }

  .tp-community__event {
    display: grid;
    gap: 0.5rem;
    padding: 0.9rem 1.1rem;
    border-radius: 16px;
    background: rgba(15, 23, 42, 0.5);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.12);
  }

  .tp-community__event-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.85);
  }

  .tp-community__event-title {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }

  .tp-community__event-location {
    margin: 0;
    color: var(--tp-text-muted);
  }

  .tp-community__event-link {
    display: inline-flex;
    align-items: center;
    font-weight: 600;
    color: rgba(125, 211, 252, 0.95);
    text-decoration: none;
  }

  .tp-community__resource {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: flex-start;
    gap: 1rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
  }

  .tp-community__resource:last-child {
    border-bottom: none;
    padding-bottom: 0;
  }

  .tp-community__resource-title {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }

  .tp-community__resource-description {
    margin: 0.3rem 0 0 0;
    color: var(--tp-text-muted);
    max-width: 40ch;
  }

  .tp-community__resource-link {
    display: inline-flex;
    align-items: center;
    font-weight: 600;
    color: rgba(125, 211, 252, 0.95);
    text-decoration: none;
  }

  .tp-community__champion {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.25rem;
    border-radius: 16px;
    background: rgba(15, 23, 42, 0.5);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.14);
  }

  .tp-community__champion-badge {
    width: 40px;
    height: 40px;
    border-radius: 999px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: rgba(56, 189, 248, 0.18);
    color: rgba(56, 189, 248, 0.95);
    font-size: 1.2rem;
  }

  .tp-community__champion-name {
    margin: 0;
    font-size: 1.05rem;
    font-weight: 600;
  }

  .tp-community__champion-specialty,
  .tp-community__champion-contributions {
    margin: 0;
    font-size: 0.85rem;
    color: var(--tp-text-subtle);
  }

  .tp-community__champion-link {
    display: inline-flex;
    align-items: center;
    font-weight: 600;
    color: rgba(125, 211, 252, 0.95);
    text-decoration: none;
  }

  .tp-community__engagement {
    position: relative;
    overflow: hidden;
  }

  .tp-community__timeline {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 1.25rem;
  }

  .tp-community__timeline-entry {
    display: grid;
    gap: 0.9rem;
    padding: 1.2rem;
    border-radius: 16px;
    background: rgba(15, 23, 42, 0.4);
    border: 1px solid rgba(148, 163, 184, 0.18);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.06);
  }

  .tp-community__timeline-period {
    font-size: 0.9rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.85);
  }

  .tp-community__timeline-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 0.75rem;
  }

  .tp-community__timeline-metric {
    display: grid;
    gap: 0.25rem;
    padding: 0.75rem;
    border-radius: 12px;
    background: rgba(37, 99, 235, 0.12);
    border: 1px solid rgba(37, 99, 235, 0.2);
  }

  .tp-community__timeline-value {
    font-size: 1.2rem;
    font-weight: 600;
  }

  .tp-community__timeline-label {
    font-size: 0.8rem;
    color: rgba(226, 232, 240, 0.7);
  }

  .tp-community__timeline-highlights {
    list-style: disc;
    margin: 0;
    padding-left: 1.25rem;
    display: grid;
    gap: 0.4rem;
    color: rgba(226, 232, 240, 0.85);
  }

  .tp-community__hubs {
    position: relative;
  }

  .tp-community__hub-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 1rem;
  }

  .tp-community__hub {
    display: grid;
    gap: 0.65rem;
    padding: 1.1rem;
    border-radius: 14px;
    background: rgba(15, 23, 42, 0.38);
    border: 1px solid rgba(148, 163, 184, 0.16);
    transition: transform 0.3s ease, border-color 0.3s ease;
  }

  .tp-community__hub:hover {
    transform: translateY(-2px);
    border-color: rgba(56, 189, 248, 0.35);
  }

  .tp-community__hub-header {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.5rem;
  }

  .tp-community__hub-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .tp-community__hub-location {
    font-size: 0.75rem;
    color: rgba(148, 163, 184, 0.75);
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .tp-community__hub-leads {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(226, 232, 240, 0.8);
  }

  .tp-community__hub-focus {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.8);
  }

  .tp-community__hub-link {
    justify-self: start;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    color: rgba(96, 165, 250, 0.95);
    text-decoration: none;
    font-size: 0.85rem;
  }

  .tp-community__hub-link:hover {
    text-decoration: underline;
  }

  .tp-community__opportunities {
    position: relative;
  }

  .tp-community__opportunity-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 1rem;
  }

  .tp-community__opportunity {
    display: grid;
    gap: 0.65rem;
    padding: 1.15rem;
    border-radius: 14px;
    border: 1px solid rgba(56, 189, 248, 0.15);
    background: rgba(15, 23, 42, 0.45);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.07);
  }

  .tp-community__opportunity-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
  }

  .tp-community__opportunity-scope {
    margin: 0;
    font-size: 0.8rem;
    color: rgba(148, 163, 184, 0.75);
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }

  .tp-community__opportunity-description {
    margin: 0;
    color: rgba(226, 232, 240, 0.85);
    font-size: 0.9rem;
  }

  .tp-community__opportunity-link {
    justify-self: start;
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    color: rgba(129, 140, 248, 0.95);
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 500;
  }

  .tp-community__opportunity-link:hover {
    text-decoration: underline;
  }

  .tp-community-spotlight {
    display: grid;
    gap: 1.25rem;
  }

  .tp-community-spotlight__metrics {
    display: grid;
    gap: 0.75rem;
  }

  .tp-community-spotlight__metric {
    display: grid;
    gap: 0.35rem;
    padding: 0.9rem 1.1rem;
    border-radius: 14px;
    background: rgba(15, 23, 42, 0.5);
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.12);
  }

  .tp-community-spotlight__metric dt {
    margin: 0;
    font-size: 0.75rem;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.8);
  }

  .tp-community-spotlight__metric dd {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
  }

  .tp-community-spotlight__metric-hint {
    margin: 0;
    font-size: 0.85rem;
    color: var(--tp-text-subtle);
  }

  .tp-community-spotlight__section {
    display: grid;
    gap: 0.5rem;
  }

  .tp-community-spotlight__section h4 {
    margin: 0;
    font-size: 0.95rem;
    font-weight: 600;
    color: rgba(226, 232, 240, 0.9);
  }

  .tp-community-spotlight__list {
    display: grid;
    gap: 0.4rem;
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .tp-community-spotlight__program,
  .tp-community-spotlight__resource {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    color: rgba(125, 211, 252, 0.95);
    font-weight: 600;
    text-decoration: none;
  }

  .tp-view__header {
    display: grid;
    gap: 0.5rem;
    margin-bottom: 1.5rem;
  }

  .tp-view__meta {
    display: none;
  }

  .tp-view__title {
    margin: 0;
    font-size: 1.5rem;
    font-weight: 600;
  }

  .tp-view__subtitle {
    margin: 0;
    font-size: 0.95rem;
    color: var(--tp-text-muted);
  }

  .tp-grid {
    display: grid;
    gap: 1.5rem;
  }

  .tp-grid--two {
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  }

  .tp-grid--three {
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  }

  .tp-card {
    position: relative;
    background: var(--tp-surface-800);
    border: 1px solid rgba(148, 163, 184, 0.2);
    border-radius: 18px;
    padding: 1.5rem;
    display: grid;
    gap: 1rem;
    transition: transform 0.45s ease, border-color 0.45s ease, box-shadow 0.45s ease;
    overflow: hidden;
  }

  .tp-card::before {
    content: '';
    position: absolute;
    inset: -80% -80%;
    background: radial-gradient(circle at center, rgba(56, 189, 248, 0.2), transparent 65%);
    opacity: 0;
    transition: transform 0.6s ease, opacity 0.6s ease;
    pointer-events: none;
  }

  .tp-card:hover {
    transform: translateY(-6px);
    border-color: rgba(56, 189, 248, 0.35);
    box-shadow: 0 28px 60px -34px rgba(56, 189, 248, 0.5);
  }

  .tp-card:hover::before {
    opacity: 0.8;
    transform: scale(1.15);
  }

  .tp-card__header {
    display: grid;
    gap: 0.35rem;
  }

  .tp-card__title {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 600;
  }

  .tp-card__meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.95rem;
    color: rgba(226, 232, 240, 0.75);
  }

  .tp-stat {
    font-weight: 600;
  }

  .tp-stat--muted {
    color: rgba(148, 163, 184, 0.85);
  }

  .tp-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    background: rgba(148, 163, 184, 0.2);
    color: rgba(226, 232, 240, 0.9);
    transition: transform 0.3s ease, background 0.3s ease;
  }

  .tp-pill--positive {
    background: rgba(74, 222, 128, 0.2);
    color: var(--tp-positive);
  }

  .tp-pill--negative {
    background: rgba(248, 113, 113, 0.2);
    color: var(--tp-negative);
  }

  .tp-meta-list {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .tp-meta-list__item {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.2rem 0.65rem;
    border-radius: 999px;
    font-size: 0.75rem;
    background: rgba(148, 163, 184, 0.18);
    color: rgba(226, 232, 240, 0.88);
  }

  .tp-meta-list__key {
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: rgba(226, 232, 240, 0.75);
  }

  .tp-status {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.25rem 0.6rem;
    border-radius: 999px;
    font-size: 0.8rem;
    background: rgba(148, 163, 184, 0.2);
  }

  .tp-status--filled {
    background: rgba(74, 222, 128, 0.2);
    color: #4ade80;
  }

  .tp-status--working {
    background: rgba(251, 191, 36, 0.2);
    color: #fbbf24;
  }

  .tp-status--cancelled {
    background: rgba(248, 113, 113, 0.2);
    color: #f87171;
  }

  .tp-progress {
    position: relative;
    background: rgba(15, 23, 42, 0.6);
    border-radius: 999px;
    overflow: hidden;
    height: 0.75rem;
    box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.2);
  }

  .tp-progress__bar {
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, #38bdf8, #2563eb);
    transition: transform 0.3s ease;
  }

  .tp-progress--glow {
    box-shadow: inset 0 0 0 1px rgba(56, 189, 248, 0.2), 0 8px 18px -12px rgba(56, 189, 248, 0.7);
  }

  .tp-progress__label {
    display: inline-block;
    margin-left: 0.5rem;
    font-size: 0.85rem;
  }

  .tp-app[dir='rtl'] {
    direction: rtl;
  }

  .tp-app[dir='rtl'] .tp-nav__mobile-bar {
    flex-direction: row-reverse;
  }

  .tp-app[dir='rtl'] .tp-nav__link {
    flex-direction: row-reverse;
  }

  .tp-app[dir='rtl'] .tp-nav__badge {
    margin-inline-start: 0;
    margin-inline-end: auto;
  }

  .tp-app[dir='rtl'] .tp-community__timeline-highlights {
    padding-inline-start: 1.25rem;
    padding-inline-end: 0;
  }

  @media (max-width: 1079px) {
    .tp-app {
      grid-template-columns: minmax(0, 1fr);
    }

    .tp-nav {
      border-right: none;
      border-bottom: 1px solid var(--tp-border-soft);
      position: sticky;
      top: 0;
      background: rgba(15, 23, 42, 0.88);
      z-index: 20;
    }

    .tp-nav__mobile-bar {
      display: flex;
    }

    .tp-nav__panel {
      position: fixed;
      top: 0;
      left: 0;
      bottom: 0;
      width: min(320px, 85vw);
      max-width: 100%;
      background: rgba(15, 23, 42, 0.95);
      padding: 2.5rem 1.75rem 2.5rem;
      gap: 1.75rem;
      box-shadow: 18px 0 50px -30px rgba(15, 23, 42, 0.9);
      overflow-y: auto;
      transform: translateX(-100%);
      transition: transform 0.35s ease;
    }

    .tp-nav[data-enhanced='true'][data-state='expanded'] .tp-nav__panel {
      transform: translateX(0);
    }

    .tp-nav[data-enhanced='true'][data-state='expanded'] .tp-nav__overlay {
      display: block;
      position: fixed;
      inset: 0;
      background: rgba(15, 23, 42, 0.65);
      backdrop-filter: blur(3px);
    }

    .tp-nav__close {
      display: inline-flex;
    }

    .tp-shell {
      padding: 1.75rem 1.5rem 2.5rem;
    }

    .tp-nav__locale {
      padding-bottom: 0.75rem;
    }
  }

  @media (max-width: 768px) {
    .tp-shell {
      padding: 1.5rem 1.25rem 2.5rem;
    }

    .tp-grid--two {
      grid-template-columns: minmax(0, 1fr);
    }

    .tp-hero__content {
      max-width: none;
    }

    .tp-community__hero {
      padding: 1.5rem;
    }

    .tp-community__hero-content {
      max-width: none;
    }

    .tp-community__metrics-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .tp-community__timeline-grid {
      grid-template-columns: minmax(0, 1fr);
    }

    .tp-community__filters-toolbar {
      justify-content: flex-start;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .tp-app::before,
    .tp-nav__link--active::before,
    .tp-nav__badge,
    .tp-card,
    .tp-view,
    .tp-card::before,
    .tp-hero::after,
    .tp-hero__orb,
    .tp-hero__grid {
      animation: none !important;
      transition-duration: 0.01ms !important;
    }

    .tp-nav__link:hover,
    .tp-card:hover,
    .tp-view:hover {
      transform: none !important;
    }
  }
`;

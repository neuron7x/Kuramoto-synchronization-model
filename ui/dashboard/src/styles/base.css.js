export const BASE_STYLES = `
  :root {
    color-scheme: dark;
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    --tp-surface-900: rgba(15, 23, 42, 0.85);
    --tp-surface-800: rgba(15, 23, 42, 0.65);
    --tp-surface-700: rgba(15, 23, 42, 0.55);
    --tp-border-strong: rgba(148, 163, 184, 0.35);
    --tp-border-soft: rgba(148, 163, 184, 0.15);
    --tp-text-muted: rgba(226, 232, 240, 0.7);
    --tp-text-subtle: rgba(148, 163, 184, 0.75);
    --tp-accent: #38bdf8;
    --tp-accent-strong: #2563eb;
    --tp-positive: #4ade80;
    --tp-negative: #f87171;
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

  .tp-app {
    position: relative;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
    min-height: 100vh;
    background: radial-gradient(circle at top left, #0d1b2a, #010409);
    color: #f8fafc;
    overflow: hidden;
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
    padding: 2rem 2rem 0 2rem;
    display: flex;
    flex-direction: column;
    gap: 1rem;
    background: rgba(15, 23, 42, 0.6);
    border-right: 1px solid var(--tp-border-soft);
    backdrop-filter: blur(24px);
    z-index: 1;
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
    background: rgba(15, 23, 42, 0.45);
    position: relative;
    animation: tpBadgePulse 4s ease-in-out infinite;
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

  .tp-progress__label {
    display: inline-block;
    margin-left: 0.5rem;
    font-size: 0.85rem;
  }

  @media (prefers-reduced-motion: reduce) {
    .tp-app::before,
    .tp-nav__link--active::before,
    .tp-nav__badge,
    .tp-card,
    .tp-view,
    .tp-card::before {
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

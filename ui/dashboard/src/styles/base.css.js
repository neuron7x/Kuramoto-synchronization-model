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

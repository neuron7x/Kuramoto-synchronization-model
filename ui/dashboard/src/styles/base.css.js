export const BASE_STYLES = `
  :root {
    color-scheme: dark;
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
    --tp-surface-900: rgba(10, 15, 30, 0.95);
    --tp-surface-800: rgba(15, 23, 42, 0.85);
    --tp-surface-700: rgba(20, 30, 55, 0.75);
    --tp-surface-600: rgba(30, 41, 59, 0.7);
    --tp-surface-glass: rgba(15, 23, 42, 0.6);
    --tp-border-strong: rgba(99, 179, 237, 0.4);
    --tp-border-soft: rgba(99, 179, 237, 0.15);
    --tp-border-glow: rgba(6, 182, 212, 0.6);
    --tp-text-muted: rgba(240, 249, 255, 0.95);
    --tp-text-subtle: rgba(226, 232, 240, 0.92);
    --tp-text-dim: rgba(148, 163, 184, 0.8);
    --tp-accent: #06b6d4;
    --tp-accent-strong: #0891b2;
    --tp-accent-vibrant: #22d3ee;
    --tp-accent-soft: rgba(6, 182, 212, 0.15);
    --tp-positive: #10b981;
    --tp-positive-glow: #34d399;
    --tp-positive-soft: rgba(16, 185, 129, 0.15);
    --tp-negative: #ef4444;
    --tp-negative-glow: #f87171;
    --tp-negative-soft: rgba(239, 68, 68, 0.15);
    --tp-warning: #f59e0b;
    --tp-warning-glow: #fbbf24;
    --tp-warning-soft: rgba(245, 158, 11, 0.15);
    --tp-focus-ring: #06b6d4;
    --tp-focus-ring-subtle: rgba(6, 182, 212, 0.35);
    --tp-gradient-primary: linear-gradient(135deg, #06b6d4 0%, #3b82f6 50%, #8b5cf6 100%);
    --tp-gradient-accent: linear-gradient(120deg, #22d3ee 0%, #0891b2 100%);
    --tp-gradient-warm: linear-gradient(135deg, #f59e0b 0%, #ef4444 100%);
    --tp-gradient-success: linear-gradient(135deg, #10b981 0%, #34d399 100%);
    --tp-gradient-purple: linear-gradient(135deg, #8b5cf6 0%, #a855f7 50%, #c084fc 100%);
    --tp-gradient-cosmic: linear-gradient(135deg, #1e1b4b 0%, #312e81 50%, #4338ca 100%);
    --tp-gradient-glass: linear-gradient(135deg, rgba(255, 255, 255, 0.1) 0%, rgba(255, 255, 255, 0.02) 100%);
    --tp-shadow-glow: 0 0 40px -10px rgba(6, 182, 212, 0.5);
    --tp-shadow-ambient: 0 25px 50px -12px rgba(0, 0, 0, 0.4);
    --tp-shadow-card: 0 20px 40px -20px rgba(6, 182, 212, 0.3), 0 0 0 1px rgba(6, 182, 212, 0.1);
    --tp-noise-opacity: 0.03;
    --tp-noise-pattern: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
    --tp-transition-smooth: cubic-bezier(0.4, 0, 0.2, 1);
    --tp-transition-bounce: cubic-bezier(0.34, 1.56, 0.64, 1);
    --tp-transition-spring: cubic-bezier(0.175, 0.885, 0.32, 1.275);
  }

  :focus-visible {
    outline: 2px solid var(--tp-focus-ring);
    outline-offset: 3px;
  }

  /* Enhanced Typography Utilities */
  .tp-text-muted {
    color: var(--tp-text-muted);
  }

  .tp-text-subtle {
    color: var(--tp-text-subtle);
  }

  .tp-text-dim {
    color: var(--tp-text-dim);
  }

  .tp-text-gradient {
    background: var(--tp-gradient-primary);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .tp-text-glow {
    text-shadow: 0 0 20px rgba(6, 182, 212, 0.5);
  }

  /* Glass Morphism Utilities */
  .tp-glass {
    background: var(--tp-surface-glass);
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(255, 255, 255, 0.08);
  }

  .tp-glass-strong {
    background: rgba(15, 23, 42, 0.85);
    backdrop-filter: blur(30px) saturate(200%);
    border: 1px solid rgba(255, 255, 255, 0.1);
  }

  /* Enhanced Glow Effects */
  .tp-glow {
    box-shadow: var(--tp-shadow-glow);
  }

  .tp-glow-accent {
    box-shadow: 0 0 30px -5px var(--tp-accent), 0 0 60px -15px rgba(6, 182, 212, 0.3);
  }

  .tp-glow-positive {
    box-shadow: 0 0 30px -5px var(--tp-positive), 0 0 60px -15px rgba(16, 185, 129, 0.3);
  }

  .tp-glow-negative {
    box-shadow: 0 0 30px -5px var(--tp-negative), 0 0 60px -15px rgba(239, 68, 68, 0.3);
  }

  /* Noise Texture Overlay */
  .tp-noise::after {
    content: '';
    position: absolute;
    inset: 0;
    background-image: var(--tp-noise-pattern);
    opacity: var(--tp-noise-opacity);
    pointer-events: none;
    mix-blend-mode: overlay;
    border-radius: inherit;
  }

  /* Animated Border Glow */
  .tp-border-glow {
    position: relative;
  }

  .tp-border-glow::before {
    content: '';
    position: absolute;
    inset: -1px;
    background: linear-gradient(90deg, 
      rgba(6, 182, 212, 0), 
      rgba(6, 182, 212, 0.5), 
      rgba(59, 130, 246, 0.5), 
      rgba(139, 92, 246, 0.5), 
      rgba(6, 182, 212, 0)
    );
    border-radius: inherit;
    opacity: 0;
    transition: opacity 0.4s ease;
    z-index: -1;
  }

  .tp-border-glow:hover::before {
    opacity: 1;
    animation: tpBorderRotate 3s linear infinite;
  }

  @keyframes tpBorderRotate {
    0% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
    100% { background-position: 0% 50%; }
  }

  /* Premium Button Variants */
  .tp-btn {
    position: relative;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    font-size: 0.95rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    border-radius: 12px;
    border: none;
    cursor: pointer;
    overflow: hidden;
    transition: all 0.3s var(--tp-transition-smooth);
  }

  .tp-btn-primary {
    background: var(--tp-gradient-accent);
    color: #020617;
    box-shadow: 
      0 4px 20px -4px rgba(6, 182, 212, 0.5),
      inset 0 1px 0 rgba(255, 255, 255, 0.2);
  }

  .tp-btn-primary::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
    transform: translateX(-100%);
    transition: transform 0.5s ease;
  }

  .tp-btn-primary:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 
      0 8px 30px -4px rgba(6, 182, 212, 0.6),
      inset 0 1px 0 rgba(255, 255, 255, 0.3);
  }

  .tp-btn-primary:hover::before {
    transform: translateX(100%);
  }

  .tp-btn-secondary {
    background: var(--tp-surface-glass);
    border: 1px solid var(--tp-border-soft);
    color: var(--tp-text-muted);
    backdrop-filter: blur(20px);
  }

  .tp-btn-secondary:hover {
    background: rgba(6, 182, 212, 0.1);
    border-color: var(--tp-accent);
    transform: translateY(-2px);
    box-shadow: 0 8px 24px -8px rgba(6, 182, 212, 0.4);
  }

  .tp-btn-ghost {
    background: transparent;
    color: var(--tp-text-subtle);
  }

  .tp-btn-ghost:hover {
    background: var(--tp-accent-soft);
    color: var(--tp-accent-vibrant);
  }

  /* Enhanced Input Styles */
  .tp-input {
    width: 100%;
    padding: 0.75rem 1rem;
    background: var(--tp-surface-glass);
    border: 1px solid var(--tp-border-soft);
    border-radius: 12px;
    color: var(--tp-text-muted);
    font-size: 0.95rem;
    transition: all 0.3s var(--tp-transition-smooth);
    backdrop-filter: blur(10px);
  }

  .tp-input:focus {
    outline: none;
    border-color: var(--tp-accent);
    box-shadow: 
      0 0 0 3px var(--tp-focus-ring-subtle),
      0 4px 20px -4px rgba(6, 182, 212, 0.3);
  }

  .tp-input::placeholder {
    color: var(--tp-text-dim);
  }

  /* Card Hover Effects */
  .tp-card-interactive {
    transition: all 0.4s var(--tp-transition-smooth);
  }

  .tp-card-interactive:hover {
    transform: translateY(-6px) scale(1.01);
    box-shadow: 
      0 30px 60px -20px rgba(6, 182, 212, 0.4),
      0 0 0 1px rgba(6, 182, 212, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }

  /* Animated Indicators */
  .tp-indicator {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.25rem 0.75rem;
    font-size: 0.8rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    border-radius: 999px;
    text-transform: uppercase;
  }

  .tp-indicator-live {
    background: var(--tp-positive-soft);
    color: var(--tp-positive-glow);
  }

  .tp-indicator-live::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--tp-positive);
    animation: tpIndicatorPulse 2s ease-in-out infinite;
  }

  @keyframes tpIndicatorPulse {
    0%, 100% {
      opacity: 1;
      transform: scale(1);
    }
    50% {
      opacity: 0.5;
      transform: scale(1.3);
    }
  }

  .tp-indicator-warning {
    background: var(--tp-warning-soft);
    color: var(--tp-warning-glow);
  }

  .tp-indicator-error {
    background: var(--tp-negative-soft);
    color: var(--tp-negative-glow);
  }

  /* Skeleton Loading Animation */
  .tp-skeleton {
    position: relative;
    overflow: hidden;
    background: var(--tp-surface-700);
    border-radius: 8px;
  }

  .tp-skeleton::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(
      90deg,
      transparent,
      rgba(6, 182, 212, 0.1),
      transparent
    );
    animation: tpSkeletonShimmer 1.5s infinite;
  }

  @keyframes tpSkeletonShimmer {
    0% { transform: translateX(-100%); }
    100% { transform: translateX(100%); }
  }

  /* Floating Action Button */
  .tp-fab {
    position: fixed;
    bottom: 2rem;
    right: 2rem;
    width: 56px;
    height: 56px;
    border-radius: 16px;
    background: var(--tp-gradient-accent);
    border: none;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    box-shadow: 
      0 8px 30px -8px rgba(6, 182, 212, 0.6),
      0 0 0 1px rgba(6, 182, 212, 0.3);
    transition: all 0.3s var(--tp-transition-spring);
    z-index: 100;
  }

  .tp-fab:hover {
    transform: scale(1.1) rotate(90deg);
    box-shadow: 
      0 12px 40px -8px rgba(6, 182, 212, 0.8),
      0 0 0 2px rgba(6, 182, 212, 0.5);
  }

  /* Divider with gradient */
  .tp-divider {
    height: 1px;
    background: linear-gradient(
      90deg,
      transparent,
      var(--tp-border-soft),
      var(--tp-accent),
      var(--tp-border-soft),
      transparent
    );
    margin: 1.5rem 0;
  }

  @keyframes tpAurora {
    0% {
      transform: translate3d(-15%, -25%, 0) scale(1.05) rotate(0deg);
      opacity: 0.4;
    }
    50% {
      transform: translate3d(10%, -10%, 0) scale(1.15) rotate(12deg);
      opacity: 0.6;
    }
    100% {
      transform: translate3d(-5%, 0%, 0) scale(1.08) rotate(-4deg);
      opacity: 0.4;
    }
  }

  @keyframes tpBadgePulse {
    0%,
    100% {
      box-shadow: 0 0 0 0 rgba(6, 182, 212, 0.6), 0 0 20px rgba(6, 182, 212, 0.3);
    }
    70% {
      box-shadow: 0 0 0 10px rgba(6, 182, 212, 0), 0 0 30px rgba(6, 182, 212, 0);
    }
  }

  @keyframes tpShimmer {
    0% {
      transform: translateX(-100%) translateY(-100%) rotate(45deg);
    }
    100% {
      transform: translateX(100%) translateY(100%) rotate(45deg);
    }
  }

  @keyframes tpFloat {
    0%, 100% {
      transform: translateY(0px);
    }
    50% {
      transform: translateY(-10px);
    }
  }

  @keyframes tpGradientShift {
    0%, 100% {
      background-position: 0% 50%;
    }
    50% {
      background-position: 100% 50%;
    }
  }

  @keyframes tpScanLine {
    0% {
      transform: translateY(-100%);
    }
    100% {
      transform: translateY(100%);
    }
  }

  @keyframes tpPulseGlow {
    0%, 100% {
      filter: brightness(1) drop-shadow(0 0 10px rgba(6, 182, 212, 0.4));
    }
    50% {
      filter: brightness(1.2) drop-shadow(0 0 20px rgba(6, 182, 212, 0.8));
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
    background: 
      radial-gradient(circle at 20% 30%, rgba(6, 182, 212, 0.15) 0%, transparent 50%),
      radial-gradient(circle at 80% 70%, rgba(139, 92, 246, 0.12) 0%, transparent 50%),
      linear-gradient(135deg, #020617 0%, #0a0f1e 50%, #020617 100%);
    background-size: 100% 100%, 100% 100%, 100% 100%;
    color: #f8fafc;
    overflow: hidden;
  }

  .tp-skip-link {
    position: absolute;
    top: 1rem;
    left: 1.5rem;
    transform: translateY(-200%);
    padding: 0.75rem 1.35rem;
    border-radius: 999px;
    background: var(--tp-gradient-accent);
    color: #020617;
    font-weight: 700;
    letter-spacing: 0.02em;
    transition: transform 0.2s ease;
    z-index: 30;
    box-shadow: 0 4px 12px -4px rgba(6, 182, 212, 0.6);
  }

  .tp-skip-link:focus-visible {
    transform: translateY(0);
    box-shadow: 
      0 8px 24px -6px rgba(6, 182, 212, 0.8),
      0 0 0 4px rgba(6, 182, 212, 0.3);
  }

  .tp-app::before {
    content: '';
    position: fixed;
    inset: -40%;
    background: conic-gradient(
      from 180deg at 50% 50%, 
      rgba(6, 182, 212, 0.2), 
      rgba(59, 130, 246, 0.15),
      rgba(139, 92, 246, 0.18), 
      rgba(6, 182, 212, 0.2)
    );
    filter: blur(140px);
    pointer-events: none;
    animation: tpAurora 30s ease-in-out infinite alternate;
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
    background: rgba(10, 15, 30, 0.75);
    border-right: 1px solid var(--tp-border-soft);
    backdrop-filter: blur(30px) saturate(180%);
    box-shadow: inset -1px 0 0 0 rgba(6, 182, 212, 0.1);
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

  .tp-nav__menu {
    display: grid;
    gap: 1.5rem;
  }

  .tp-nav__menu-header {
    display: grid;
    gap: 0.35rem;
  }

  .tp-nav__menu-title {
    margin: 0;
    font-size: 0.82rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: rgba(226, 232, 240, 0.72);
  }

  .tp-nav__menu-description {
    margin: 0;
    font-size: 0.86rem;
    color: rgba(148, 163, 184, 0.82);
  }

  .tp-nav__menu-groups {
    display: grid;
    gap: 1.25rem;
  }

  .tp-nav__menu-group {
    display: grid;
    gap: 0.75rem;
    padding: 1.25rem 1.3rem;
    border-radius: 20px;
    background: rgba(20, 30, 55, 0.6);
    border: 1px solid rgba(99, 179, 237, 0.25);
    box-shadow: 
      inset 0 1px 0 rgba(255, 255, 255, 0.06),
      0 4px 20px -10px rgba(6, 182, 212, 0.3);
    backdrop-filter: blur(16px) saturate(180%);
  }

  .tp-nav__menu-group-header {
    display: grid;
    gap: 0.25rem;
  }

  .tp-nav__menu-group-title {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    letter-spacing: 0.01em;
  }

  .tp-nav__menu-group-description {
    margin: 0;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.78);
  }

  .tp-nav__menu-links {
    gap: 0.6rem;
  }

  .tp-nav__menu-item {
    list-style: none;
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
    width: 100%;
    padding: 0.85rem 1.1rem;
    border-radius: 14px;
    position: relative;
    background: rgba(20, 30, 55, 0.4);
    border: 1px solid rgba(99, 179, 237, 0.1);
    color: inherit;
    text-decoration: none;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
  }

  .tp-nav__link::after {
    content: '';
    position: absolute;
    inset: 0;
    background: var(--tp-gradient-accent);
    opacity: 0;
    transition: opacity 0.4s ease;
    z-index: -1;
  }

  .tp-nav__link:hover {
    background: rgba(6, 182, 212, 0.15);
    border-color: rgba(6, 182, 212, 0.4);
    transform: translateX(6px);
    box-shadow: 0 8px 24px -8px rgba(6, 182, 212, 0.5);
  }

  .tp-nav__link:hover::after {
    opacity: 0.15;
  }

  .tp-nav__link--active {
    background: rgba(6, 182, 212, 0.2);
    border-color: rgba(6, 182, 212, 0.6);
    color: #f0f9ff;
    box-shadow: 0 10px 30px -10px rgba(6, 182, 212, 0.6), inset 0 1px 0 0 rgba(255, 255, 255, 0.1);
  }

  .tp-nav__link--active::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(120deg, rgba(6, 182, 212, 0.4), rgba(34, 211, 238, 0));
    opacity: 0.8;
    mix-blend-mode: screen;
    transform: translateX(-100%);
    animation: tpGlowSweep 2s ease-in-out infinite;
    pointer-events: none;
  }

  .tp-nav__link-label {
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  .tp-nav__badge {
    font-size: 0.75rem;
    font-weight: 700;
    padding: 0.3rem 0.7rem;
    border-radius: 999px;
    background: var(--tp-gradient-accent);
    color: #0a0f1e;
    position: relative;
    animation: tpBadgePulse 3s ease-in-out infinite;
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
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

  .tp-breadcrumbs {
    display: flex;
    align-items: center;
    margin: 0;
    color: rgba(148, 163, 184, 0.85);
  }

  .tp-breadcrumbs__list {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .tp-breadcrumbs__item {
    display: flex;
    align-items: center;
    font-size: 0.85rem;
  }

  .tp-breadcrumbs__item + .tp-breadcrumbs__item::before {
    content: '/';
    margin: 0 0.45rem;
    opacity: 0.55;
  }

  .tp-breadcrumbs__link {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    padding: 0.45rem 0.85rem;
    border-radius: 999px;
    border: 1px solid rgba(99, 179, 237, 0.2);
    background: rgba(20, 30, 55, 0.6);
    color: inherit;
    text-decoration: none;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    backdrop-filter: blur(10px);
  }

  .tp-breadcrumbs__link:hover {
    border-color: rgba(6, 182, 212, 0.6);
    background: rgba(6, 182, 212, 0.2);
    color: #f0f9ff;
    box-shadow: 0 4px 12px -6px rgba(6, 182, 212, 0.6);
    transform: translateY(-1px);
  }

  .tp-breadcrumbs__link:focus-visible {
    outline: 2px solid var(--tp-focus-ring);
    outline-offset: 2px;
  }

  .tp-breadcrumbs__current {
    display: inline-flex;
    align-items: center;
    padding: 0.45rem 0.85rem;
    border-radius: 999px;
    background: var(--tp-gradient-accent);
    color: #020617;
    font-weight: 700;
    letter-spacing: 0.01em;
    box-shadow: 
      0 4px 12px -6px rgba(6, 182, 212, 0.7),
      inset 0 1px 0 rgba(255, 255, 255, 0.3);
    border: 1px solid rgba(6, 182, 212, 0.4);
  }

  .tp-toolbar {
    position: relative;
    display: grid;
    gap: 1.25rem;
    padding: 1.75rem 2rem;
    border-radius: 24px;
    background: rgba(10, 15, 30, 0.7);
    border: 1px solid rgba(99, 179, 237, 0.25);
    box-shadow: 
      0 20px 60px -20px rgba(6, 182, 212, 0.3), 
      inset 0 1px 0 rgba(255, 255, 255, 0.08),
      0 0 0 1px rgba(6, 182, 212, 0.05);
    backdrop-filter: blur(20px) saturate(180%);
  }

  .tp-toolbar__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1.5rem;
    flex-wrap: wrap;
  }

  .tp-toolbar__context {
    display: grid;
    gap: 0.35rem;
  }

  .tp-toolbar__eyebrow {
    margin: 0;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: rgba(148, 163, 184, 0.75);
  }

  .tp-toolbar__title {
    margin: 0;
    font-size: clamp(1.25rem, 2.5vw, 1.6rem);
    font-weight: 700;
    letter-spacing: -0.01em;
  }

  .tp-toolbar__description {
    margin: 0;
    max-width: 320px;
    font-size: 0.9rem;
    color: rgba(226, 232, 240, 0.82);
  }

  .tp-toolbar__actions {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
  }

  .tp-toolbar__button {
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.4rem;
    min-width: 190px;
    padding: 1rem 1.3rem;
    border-radius: 16px;
    border: 1px solid rgba(99, 179, 237, 0.3);
    background: rgba(20, 30, 55, 0.7);
    color: inherit;
    font-weight: 600;
    letter-spacing: 0.01em;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
  }

  .tp-toolbar__button::before {
    content: '';
    position: absolute;
    inset: 0;
    background: var(--tp-gradient-accent);
    opacity: 0;
    transition: opacity 0.3s ease;
    z-index: 0;
  }

  .tp-toolbar__button > * {
    position: relative;
    z-index: 1;
  }

  .tp-toolbar__button:hover {
    transform: translateY(-3px);
    border-color: rgba(6, 182, 212, 0.7);
    box-shadow: 
      0 16px 40px -12px rgba(6, 182, 212, 0.5),
      0 0 0 1px rgba(6, 182, 212, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }

  .tp-toolbar__button:hover::before {
    opacity: 0.15;
  }

  .tp-toolbar__button:disabled {
    cursor: wait;
    opacity: 0.75;
  }

  .tp-toolbar__button-label {
    font-size: 0.95rem;
  }

  .tp-toolbar__button-hint {
    font-size: 0.8rem;
    color: rgba(148, 163, 184, 0.85);
    font-weight: 500;
  }

  .tp-toolbar__button[data-state='busy'] {
    box-shadow: 0 0 0 4px rgba(56, 189, 248, 0.2);
  }

  .tp-toolbar__button[data-state='busy']::after {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background: linear-gradient(120deg, rgba(56, 189, 248, 0.18), rgba(37, 99, 235, 0.12));
    opacity: 0.75;
    animation: tpGlowSweep 1.6s ease-in-out infinite;
    pointer-events: none;
  }

  .tp-toolbar__button[data-feedback]::before {
    content: attr(data-feedback);
    position: absolute;
    left: 0;
    bottom: -0.35rem;
    transform: translateY(100%);
    padding: 0.35rem 0.65rem;
    border-radius: 999px;
    font-size: 0.75rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    background: rgba(56, 189, 248, 0.28);
    color: #f0f9ff;
    box-shadow: 0 12px 26px rgba(15, 23, 42, 0.45);
    pointer-events: none;
  }

  .tp-toolbar__button[data-feedback][data-state='busy']::before {
    background: rgba(148, 163, 184, 0.28);
    color: rgba(226, 232, 240, 0.92);
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
    background: rgba(10, 15, 30, 0.85);
    border: 1px solid rgba(99, 179, 237, 0.2);
    border-radius: 24px;
    padding: 2rem;
    box-shadow: 
      0 24px 60px -30px rgba(6, 182, 212, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.06);
    backdrop-filter: blur(20px) saturate(180%);
    transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
  }

  .tp-view::after {
    content: '';
    position: absolute;
    inset: -40% -60% auto -60%;
    height: 140%;
    background: radial-gradient(
      circle at top, 
      rgba(6, 182, 212, 0.25), 
      rgba(34, 211, 238, 0.1) 40%,
      rgba(6, 182, 212, 0)
    );
    opacity: 0.5;
    pointer-events: none;
    transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .tp-view:hover {
    transform: translateY(-6px);
    border-color: rgba(6, 182, 212, 0.5);
    box-shadow: 
      0 40px 80px -35px rgba(6, 182, 212, 0.6),
      0 0 0 1px rgba(6, 182, 212, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.1);
  }

  .tp-view:hover::after {
    transform: translateY(8%);
    opacity: 0.8;
  }

  .tp-view--overview {
    display: grid;
    gap: 2rem;
  }

  .tp-hero {
    position: relative;
    display: grid;
    gap: 1.75rem;
    padding: clamp(2rem, 3.5vw, 3rem);
    border-radius: 28px;
    overflow: hidden;
    background: 
      linear-gradient(135deg, rgba(6, 182, 212, 0.25), rgba(59, 130, 246, 0.2) 50%, rgba(139, 92, 246, 0.15)),
      rgba(10, 15, 30, 0.8);
    border: 1px solid rgba(6, 182, 212, 0.4);
    box-shadow: 
      0 32px 80px -40px rgba(6, 182, 212, 0.6),
      0 0 0 1px rgba(6, 182, 212, 0.15),
      inset 0 2px 0 rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(20px) saturate(180%);
  }

  .tp-hero::after {
    content: '';
    position: absolute;
    inset: 10% 8% -35% 8%;
    background: radial-gradient(
      circle at top, 
      rgba(6, 182, 212, 0.5), 
      rgba(34, 211, 238, 0.3) 40%,
      transparent 65%
    );
    filter: blur(50px);
    opacity: 0.7;
    pointer-events: none;
    animation: tpHeroPulse 10s ease-in-out infinite alternate;
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
    position: relative;
    display: grid;
    gap: 1rem;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    margin: 0;
    padding: 1.1rem 1.25rem;
    border-radius: 18px;
    background: rgba(15, 23, 42, 0.45);
    box-shadow: 
      inset 0 0 0 1px rgba(6, 182, 212, 0.25),
      0 4px 20px -8px rgba(6, 182, 212, 0.3);
    backdrop-filter: blur(16px);
    overflow: hidden;
  }

  .tp-hero__stats::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 2px;
    background: linear-gradient(90deg, transparent, rgba(6, 182, 212, 0.8), transparent);
    animation: tpScanLine 3s ease-in-out infinite;
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
    background: var(--tp-gradient-accent);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    filter: drop-shadow(0 0 15px rgba(6, 182, 212, 0.3));
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
    gap: 0.6rem;
    padding: 0.7rem 1.5rem;
    border-radius: 999px;
    background: var(--tp-gradient-accent);
    color: #020617;
    font-weight: 700;
    text-decoration: none;
    box-shadow: 
      0 16px 40px -20px rgba(6, 182, 212, 0.8),
      0 0 0 1px rgba(6, 182, 212, 0.5),
      inset 0 1px 0 rgba(255, 255, 255, 0.3);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }

  .tp-hero__action::before {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.4), transparent);
    transition: left 0.5s ease;
  }

  .tp-hero__action:hover {
    transform: translateY(-4px) scale(1.02);
    box-shadow: 
      0 20px 50px -22px rgba(6, 182, 212, 1),
      0 0 0 1px rgba(6, 182, 212, 0.7),
      inset 0 1px 0 rgba(255, 255, 255, 0.4);
  }

  .tp-hero__action:hover::before {
    left: 100%;
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
    background: rgba(15, 23, 42, 0.6);
    border: 1px solid rgba(99, 179, 237, 0.3);
    box-shadow: 
      inset 0 0 0 1px rgba(6, 182, 212, 0.15),
      0 4px 20px -10px rgba(6, 182, 212, 0.3);
    overflow: hidden;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .tp-github-badge::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(120deg, rgba(6, 182, 212, 0.2), transparent 60%);
    mix-blend-mode: screen;
    opacity: 0;
    transition: opacity 0.4s ease;
  }

  .tp-github-badge:hover {
    border-color: rgba(6, 182, 212, 0.5);
    transform: translateY(-2px);
    box-shadow: 
      inset 0 0 0 1px rgba(6, 182, 212, 0.2),
      0 8px 30px -12px rgba(6, 182, 212, 0.5);
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
    background: rgba(6, 182, 212, 0.18);
    color: rgba(6, 182, 212, 0.95);
    box-shadow: 
      inset 0 0 0 1px rgba(6, 182, 212, 0.4),
      0 0 20px rgba(6, 182, 212, 0.2);
    transition: all 0.3s ease;
  }

  .tp-github-badge:hover .tp-github-badge__icon {
    animation: tpPulseGlow 1.5s ease-in-out infinite;
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
    background: var(--tp-gradient-accent);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
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
    background: var(--tp-gradient-accent);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
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
    background: rgba(15, 23, 42, 0.8);
    border: 1px solid rgba(99, 179, 237, 0.25);
    border-radius: 20px;
    padding: 1.75rem;
    display: grid;
    gap: 1.25rem;
    transition: all 0.5s cubic-bezier(0.4, 0, 0.2, 1);
    overflow: hidden;
    backdrop-filter: blur(16px) saturate(180%);
    box-shadow: 
      0 10px 40px -20px rgba(6, 182, 212, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }

  .tp-card::before {
    content: '';
    position: absolute;
    inset: -80% -80%;
    background: radial-gradient(
      circle at center, 
      rgba(6, 182, 212, 0.25), 
      rgba(34, 211, 238, 0.15) 40%,
      transparent 65%
    );
    opacity: 0;
    transition: all 0.6s cubic-bezier(0.4, 0, 0.2, 1);
    pointer-events: none;
  }

  .tp-card:hover {
    transform: translateY(-8px);
    border-color: rgba(6, 182, 212, 0.5);
    box-shadow: 
      0 32px 70px -38px rgba(6, 182, 212, 0.6),
      0 0 0 1px rgba(6, 182, 212, 0.2),
      inset 0 1px 0 rgba(255, 255, 255, 0.08);
  }

  .tp-card:hover::before {
    opacity: 0.9;
    transform: scale(1.2) rotate(45deg);
  }

  .tp-card__header {
    display: grid;
    gap: 0.35rem;
  }

  .tp-quality {
    display: grid;
    gap: 1.25rem;
  }

  .tp-quality__metrics {
    display: grid;
    gap: 1rem;
  }

  .tp-quality__metric {
    display: grid;
    gap: 0.35rem;
  }

  .tp-quality__metric > dt {
    font-size: 0.85rem;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    color: rgba(226, 232, 240, 0.7);
  }

  .tp-quality__metric-value {
    font-size: 1.5rem;
    font-weight: 600;
    color: rgba(226, 232, 240, 0.95);
    display: inline-flex;
    align-items: baseline;
    gap: 0.4rem;
  }

  .tp-quality__metric-value--positive {
    color: var(--tp-positive);
  }

  .tp-quality__metric-value--negative {
    color: var(--tp-negative);
  }

  .tp-quality__metric-value--neutral {
    color: rgba(251, 191, 36, 0.85);
  }

  .tp-quality__metric-hint {
    margin: 0.35rem 0 0;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.85);
  }

  .tp-quality__audit {
    margin: 0;
    font-size: 0.9rem;
    color: rgba(226, 232, 240, 0.8);
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
    padding: 0.35rem 0.85rem;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 700;
    background: rgba(99, 179, 237, 0.2);
    color: rgba(240, 249, 255, 0.95);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border: 1px solid rgba(99, 179, 237, 0.3);
    box-shadow: 0 2px 8px -4px rgba(6, 182, 212, 0.4);
  }

  .tp-pill:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px -4px rgba(6, 182, 212, 0.6);
  }

  .tp-pill--positive {
    background: rgba(16, 185, 129, 0.2);
    color: var(--tp-positive-glow);
    border-color: rgba(16, 185, 129, 0.4);
    box-shadow: 0 2px 8px -4px rgba(16, 185, 129, 0.5);
  }

  .tp-pill--positive:hover {
    box-shadow: 0 4px 12px -4px rgba(16, 185, 129, 0.7);
  }

  .tp-pill--negative {
    background: rgba(239, 68, 68, 0.2);
    color: var(--tp-negative-glow);
    border-color: rgba(239, 68, 68, 0.4);
    box-shadow: 0 2px 8px -4px rgba(239, 68, 68, 0.5);
  }

  .tp-pill--negative:hover {
    box-shadow: 0 4px 12px -4px rgba(239, 68, 68, 0.7);
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
    background: rgba(10, 15, 30, 0.7);
    border-radius: 999px;
    overflow: hidden;
    height: 0.85rem;
    box-shadow: 
      inset 0 2px 4px rgba(0, 0, 0, 0.3),
      inset 0 0 0 1px rgba(99, 179, 237, 0.25);
    border: 1px solid rgba(99, 179, 237, 0.2);
  }

  .tp-progress__bar {
    position: absolute;
    inset: 0;
    background: var(--tp-gradient-primary);
    background-size: 200% 100%;
    animation: tpGradientShift 3s ease infinite;
    transition: transform 0.3s ease;
    box-shadow: 0 0 15px rgba(6, 182, 212, 0.6);
  }

  .tp-progress--glow {
    box-shadow: 
      inset 0 2px 4px rgba(0, 0, 0, 0.3),
      inset 0 0 0 1px rgba(6, 182, 212, 0.3), 
      0 0 20px rgba(6, 182, 212, 0.5),
      0 8px 24px -12px rgba(6, 182, 212, 0.8);
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
      transform: translateX(0);
      transition: transform 0.35s ease;
    }

    .tp-nav[data-enhanced='true'] .tp-nav__panel {
      transform: translateX(-100%);
    }

    .tp-nav[data-enhanced='true'][data-state='expanded'] .tp-nav__panel {
      transform: translateX(0);
    }

    .tp-nav:not([data-enhanced='true']) .tp-nav__panel {
      position: static;
      width: 100%;
      max-width: none;
      padding: 1.75rem 1.5rem 2rem;
      box-shadow: none;
      transform: none;
      overflow: visible;
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

    .tp-toolbar {
      padding: 1.25rem 1.25rem 1.4rem;
      gap: 1rem;
    }

    .tp-toolbar__actions {
      gap: 0.75rem;
    }

    .tp-toolbar__button {
      min-width: 100%;
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

  @media (max-width: 640px) {
    .tp-shell {
      padding: 1.25rem 1rem 2rem;
    }

    .tp-breadcrumbs__list {
      flex-wrap: wrap;
      gap: 0.45rem;
    }

    .tp-breadcrumbs__item + .tp-breadcrumbs__item::before {
      margin: 0 0.3rem;
    }

    .tp-view {
      padding: 1.25rem;
      border-radius: 18px;
    }

    .tp-view__title {
      font-size: 1.4rem;
    }

    .tp-view__subtitle {
      font-size: 0.9rem;
    }

    .tp-hero {
      padding: 1.5rem;
      border-radius: 22px;
    }

    .tp-hero__meta {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .tp-hero__stats {
      grid-template-columns: minmax(0, 1fr);
      padding: 1rem;
      gap: 0.85rem;
    }

    .tp-grid {
      gap: 1.25rem;
    }

    .tp-card {
      padding: 1.25rem;
    }

    .tp-card__meta {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.5rem;
    }

    .tp-nav__mobile-bar {
      padding: 0.85rem 1.25rem;
    }
  }

  @media (max-width: 480px) {
    .tp-shell {
      padding: 1rem 0.85rem 1.75rem;
    }

    .tp-toolbar__header {
      flex-direction: column;
      align-items: flex-start;
      gap: 0.75rem;
    }

    .tp-view {
      padding: 1rem;
      border-radius: 16px;
    }

    .tp-view__title {
      font-size: 1.3rem;
    }

    .tp-hero {
      padding: 1.25rem;
      border-radius: 20px;
    }

    .tp-hero__title {
      font-size: clamp(1.75rem, 8vw, 2.1rem);
    }

    .tp-card {
      padding: 1rem;
      border-radius: 16px;
    }

    .tp-hero__stats {
      gap: 0.75rem;
    }

    .tp-nav__mobile-bar {
      padding: 0.75rem 1rem;
      gap: 0.5rem;
    }

    .tp-nav__toggle {
      padding: 0.45rem 0.85rem;
    }

    .tp-nav__toggle-text {
      font-size: 0.85rem;
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

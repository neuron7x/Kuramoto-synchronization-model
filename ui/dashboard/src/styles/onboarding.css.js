export const ONBOARDING_STYLES = `
  .tp-onboarding[hidden] {
    display: none !important;
  }

  .tp-onboarding {
    position: fixed;
    inset: 1.5rem;
    max-width: 420px;
    margin-left: auto;
    z-index: 1400;
    pointer-events: none;
    display: flex;
    justify-content: flex-end;
    align-items: flex-end;
  }

  .tp-onboarding__panel {
    width: 100%;
    max-width: 420px;
    background: 
      linear-gradient(135deg, rgba(15, 23, 42, 0.95), rgba(10, 15, 30, 0.98));
    border: 1px solid rgba(99, 179, 237, 0.35);
    border-radius: 1.5rem;
    padding: 2rem;
    box-shadow: 
      0 32px 80px -30px rgba(6, 182, 212, 0.5),
      0 0 0 1px rgba(6, 182, 212, 0.15),
      inset 0 2px 0 rgba(255, 255, 255, 0.08),
      0 0 60px -30px rgba(139, 92, 246, 0.3);
    color: rgba(240, 249, 255, 0.95);
    pointer-events: auto;
    backdrop-filter: blur(30px) saturate(200%);
    animation: tpSlideInRight 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
    position: relative;
    overflow: hidden;
  }

  .tp-onboarding__panel::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #22d3ee, #3b82f6, #8b5cf6);
    border-radius: 1.5rem 1.5rem 0 0;
  }

  .tp-onboarding__panel::after {
    content: '';
    position: absolute;
    top: 0;
    left: -100%;
    width: 100%;
    height: 100%;
    background: linear-gradient(90deg, transparent, rgba(6, 182, 212, 0.1), transparent);
    animation: tpOnboardingShine 3s ease-in-out infinite;
  }

  @keyframes tpOnboardingShine {
    0% { left: -100%; }
    100% { left: 100%; }
  }

  @keyframes tpSlideInRight {
    from {
      transform: translateX(100%) scale(0.95);
      opacity: 0;
    }
    to {
      transform: translateX(0) scale(1);
      opacity: 1;
    }
  }

  .tp-onboarding__header {
    margin-bottom: 1.25rem;
    position: relative;
    z-index: 1;
  }

  .tp-onboarding__eyebrow {
    font-size: 0.75rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--tp-accent-vibrant, #22d3ee);
    margin: 0 0 0.5rem;
    font-weight: 600;
  }

  .tp-onboarding__title {
    margin: 0;
    font-size: 1.35rem;
    line-height: 1.4;
    font-weight: 700;
    background: linear-gradient(120deg, #f0f9ff, #e0f2fe);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .tp-onboarding__description {
    margin: 0 0 1.5rem;
    font-size: 0.95rem;
    line-height: 1.7;
    color: rgba(203, 213, 225, 0.92);
    position: relative;
    z-index: 1;
  }

  .tp-onboarding__footer {
    display: flex;
    flex-direction: column;
    gap: 1rem;
    position: relative;
    z-index: 1;
  }

  .tp-onboarding__progress {
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: rgba(148, 163, 184, 0.8);
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .tp-onboarding__progress-bar {
    flex: 1;
    height: 4px;
    background: rgba(99, 179, 237, 0.2);
    border-radius: 999px;
    overflow: hidden;
  }

  .tp-onboarding__progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #22d3ee, #3b82f6);
    border-radius: 999px;
    transition: width 0.4s ease;
  }

  .tp-onboarding__controls {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.75rem;
  }

  .tp-onboarding__nav {
    display: flex;
    gap: 0.5rem;
  }

  .tp-onboarding__control {
    border: none;
    border-radius: 12px;
    padding: 0.65rem 1.35rem;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }

  .tp-onboarding__control:focus-visible {
    outline: 2px solid var(--tp-focus-ring, #38bdf8);
    outline-offset: 2px;
  }

  .tp-onboarding__control--primary {
    background: linear-gradient(120deg, #22d3ee 0%, #0891b2 100%);
    color: #020617;
    font-weight: 700;
    box-shadow: 
      0 16px 32px -16px rgba(6, 182, 212, 0.6),
      0 0 0 1px rgba(6, 182, 212, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.3);
  }

  .tp-onboarding__control--primary::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
    transform: translateX(-100%);
    transition: transform 0.5s ease;
  }

  .tp-onboarding__control--primary:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 
      0 20px 40px -18px rgba(6, 182, 212, 0.8),
      0 0 0 1px rgba(6, 182, 212, 0.6),
      inset 0 1px 0 rgba(255, 255, 255, 0.4);
  }

  .tp-onboarding__control--primary:hover::before {
    transform: translateX(100%);
  }

  .tp-onboarding__control--muted {
    background: rgba(30, 41, 59, 0.6);
    color: rgba(203, 213, 225, 0.9);
    border: 1px solid rgba(99, 179, 237, 0.2);
  }

  .tp-onboarding__control--muted:hover {
    background: var(--tp-accent-soft, rgba(6, 182, 212, 0.15));
    border-color: rgba(6, 182, 212, 0.4);
    color: var(--tp-accent-vibrant, #22d3ee);
  }

  .tp-onboarding__control--disabled,
  .tp-onboarding__control[disabled] {
    opacity: 0.5;
    cursor: not-allowed;
    transform: none !important;
  }

  [data-onboarding-highlight='true'] {
    position: relative;
    z-index: 1300;
    box-shadow: 
      0 0 0 4px rgba(6, 182, 212, 0.9), 
      0 0 0 8px rgba(6, 182, 212, 0.3),
      0 0 40px rgba(6, 182, 212, 0.6),
      0 0 80px rgba(6, 182, 212, 0.3);
    border-radius: 14px;
    transition: box-shadow 300ms cubic-bezier(0.4, 0, 0.2, 1);
    animation: tpHighlightPulse 2s ease-in-out infinite;
  }

  @keyframes tpHighlightPulse {
    0%, 100% {
      box-shadow: 
        0 0 0 4px rgba(6, 182, 212, 0.9), 
        0 0 0 8px rgba(6, 182, 212, 0.3),
        0 0 40px rgba(6, 182, 212, 0.6);
    }
    50% {
      box-shadow: 
        0 0 0 4px rgba(6, 182, 212, 1), 
        0 0 0 14px rgba(6, 182, 212, 0.15),
        0 0 60px rgba(6, 182, 212, 0.8);
    }
  }

  @media (max-width: 768px) {
    .tp-onboarding {
      inset: 1rem;
      align-items: stretch;
    }

    .tp-onboarding__panel {
      max-width: none;
      height: auto;
      padding: 1.5rem;
    }

    .tp-onboarding__controls {
      flex-direction: column;
      align-items: stretch;
    }

    .tp-onboarding__nav {
      width: 100%;
    }

    .tp-onboarding__control {
      width: 100%;
      text-align: center;
    }
  }
`;

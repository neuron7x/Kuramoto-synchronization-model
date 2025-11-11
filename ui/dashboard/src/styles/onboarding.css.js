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
    background: rgba(10, 15, 30, 0.9);
    border: 1px solid rgba(99, 179, 237, 0.3);
    border-radius: 1.25rem;
    padding: 1.75rem;
    box-shadow: 
      0 32px 80px -30px rgba(6, 182, 212, 0.5),
      0 0 0 1px rgba(6, 182, 212, 0.15),
      inset 0 2px 0 rgba(255, 255, 255, 0.08);
    color: rgba(240, 249, 255, 0.95);
    pointer-events: auto;
    backdrop-filter: blur(24px) saturate(180%);
    animation: tpSlideInRight 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  }

  @keyframes tpSlideInRight {
    from {
      transform: translateX(100%);
      opacity: 0;
    }
    to {
      transform: translateX(0);
      opacity: 1;
    }
  }

  .tp-onboarding__header {
    margin-bottom: 1rem;
  }

  .tp-onboarding__eyebrow {
    font-size: 0.75rem;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--tp-text-subtle, rgba(203, 213, 225, 0.9));
    margin: 0 0 0.5rem;
  }

  .tp-onboarding__title {
    margin: 0;
    font-size: 1.25rem;
    line-height: 1.4;
    font-weight: 600;
  }

  .tp-onboarding__description {
    margin: 0 0 1.25rem;
    font-size: 0.95rem;
    line-height: 1.6;
    color: var(--tp-text-subtle, rgba(203, 213, 225, 0.9));
  }

  .tp-onboarding__footer {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .tp-onboarding__progress {
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--tp-text-subtle, rgba(203, 213, 225, 0.75));
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
    border-radius: 999px;
    padding: 0.55rem 1.2rem;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: transform 120ms ease, box-shadow 120ms ease;
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

  .tp-onboarding__control--primary:hover {
    transform: translateY(-2px) scale(1.02);
    box-shadow: 
      0 20px 40px -18px rgba(6, 182, 212, 0.8),
      0 0 0 1px rgba(6, 182, 212, 0.6),
      inset 0 1px 0 rgba(255, 255, 255, 0.4);
  }

  .tp-onboarding__control--muted {
    background: transparent;
    color: var(--tp-text-subtle, rgba(203, 213, 225, 0.9));
  }

  .tp-onboarding__control--muted:hover {
    color: var(--tp-text-muted, #e2e8f0);
  }

  .tp-onboarding__control--disabled,
  .tp-onboarding__control[disabled] {
    opacity: 0.6;
    cursor: not-allowed;
  }

  [data-onboarding-highlight='true'] {
    position: relative;
    z-index: 1300;
    box-shadow: 
      0 0 0 3px rgba(6, 182, 212, 0.8), 
      0 0 0 8px rgba(6, 182, 212, 0.3),
      0 0 30px rgba(6, 182, 212, 0.5);
    border-radius: 14px;
    transition: box-shadow 200ms cubic-bezier(0.4, 0, 0.2, 1);
    animation: tpHighlightPulse 2s ease-in-out infinite;
  }

  @keyframes tpHighlightPulse {
    0%, 100% {
      box-shadow: 
        0 0 0 3px rgba(6, 182, 212, 0.8), 
        0 0 0 8px rgba(6, 182, 212, 0.3),
        0 0 30px rgba(6, 182, 212, 0.5);
    }
    50% {
      box-shadow: 
        0 0 0 3px rgba(6, 182, 212, 1), 
        0 0 0 12px rgba(6, 182, 212, 0.2),
        0 0 40px rgba(6, 182, 212, 0.7);
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

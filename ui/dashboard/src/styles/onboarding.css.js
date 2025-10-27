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
    background: var(--tp-surface-900, rgba(15, 23, 42, 0.92));
    border: 1px solid var(--tp-border-soft, rgba(148, 163, 184, 0.28));
    border-radius: 1rem;
    padding: 1.5rem;
    box-shadow: 0 24px 60px rgba(15, 23, 42, 0.35);
    color: var(--tp-text-muted, #e2e8f0);
    pointer-events: auto;
    backdrop-filter: blur(12px);
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
    background: var(--tp-accent-strong, #2563eb);
    color: #fff;
    box-shadow: 0 12px 24px rgba(37, 99, 235, 0.35);
  }

  .tp-onboarding__control--primary:hover {
    transform: translateY(-1px);
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
    box-shadow: 0 0 0 3px var(--tp-focus-ring, #38bdf8), 0 0 0 8px var(--tp-focus-ring-subtle, rgba(56, 189, 248, 0.35));
    border-radius: 12px;
    transition: box-shadow 160ms ease;
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

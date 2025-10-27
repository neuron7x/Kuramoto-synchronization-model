export const TABLE_STYLES = `
  .tp-live-table {
    display: grid;
    gap: 1rem;
  }

  .tp-live-table__table {
    width: 100%;
    border-collapse: collapse;
  }

  .tp-live-table__head {
    background: rgba(15, 23, 42, 0.9);
  }

  .tp-live-table__row:nth-child(odd) {
    background: rgba(148, 163, 184, 0.08);
  }

  .tp-live-table__row:hover {
    background: rgba(56, 189, 248, 0.18);
    transform: translateY(-2px);
  }

  .tp-live-table__cell {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--tp-border-strong);
    font-size: 0.95rem;
    color: rgba(226, 232, 240, 0.96);
    transition: color 0.3s ease;
  }

  .tp-live-table__cell--right {
    text-align: right;
  }

  .tp-live-table__cell--center {
    text-align: center;
  }

  .tp-live-table__header {
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.08em;
    font-weight: 600;
    color: var(--tp-text-muted);
    border-bottom: 1px solid var(--tp-border-strong);
  }

  .tp-live-table__row--empty .tp-live-table__cell {
    text-align: center;
    color: rgba(148, 163, 184, 0.75);
  }

  .tp-live-table__footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.85rem;
    color: var(--tp-text-muted);
    padding: 0.5rem 0.75rem;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.72);
    border: 1px solid var(--tp-border-soft);
    backdrop-filter: blur(16px);
    gap: 0.75rem;
  }

  .tp-live-table__sort {
    margin-left: 0.25rem;
  }

  .tp-live-table__row {
    transition: transform 0.35s ease, background 0.35s ease;
  }

  .tp-app[data-theme='light'] .tp-live-table__head {
    background: rgba(248, 250, 252, 0.95);
  }

  .tp-app[data-theme='light'] .tp-live-table__row:nth-child(odd) {
    background: rgba(148, 163, 184, 0.08);
  }

  .tp-app[data-theme='light'] .tp-live-table__row:hover {
    background: rgba(59, 130, 246, 0.18);
  }

  .tp-app[data-theme='light'] .tp-live-table__cell {
    border-bottom: 1px solid rgba(148, 163, 184, 0.22);
    color: rgba(30, 41, 59, 0.9);
  }

  .tp-app[data-theme='light'] .tp-live-table__header {
    color: rgba(71, 85, 105, 0.82);
    border-bottom-color: rgba(148, 163, 184, 0.28);
  }

  .tp-app[data-theme='light'] .tp-live-table__row--empty .tp-live-table__cell {
    color: rgba(100, 116, 139, 0.75);
  }

  .tp-app[data-theme='light'] .tp-live-table__footer {
    background: rgba(255, 255, 255, 0.92);
    border: 1px solid rgba(148, 163, 184, 0.22);
    color: rgba(71, 85, 105, 0.85);
  }
`;

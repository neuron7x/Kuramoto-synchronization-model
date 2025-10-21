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
    background: rgba(15, 23, 42, 0.75);
  }

  .tp-live-table__row:nth-child(odd) {
    background: rgba(148, 163, 184, 0.04);
  }

  .tp-live-table__row:hover {
    background: rgba(56, 189, 248, 0.12);
    transform: translateY(-2px);
  }

  .tp-live-table__cell {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.2);
    font-size: 0.95rem;
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
    color: rgba(226, 232, 240, 0.65);
    border-bottom: 1px solid rgba(148, 163, 184, 0.35);
  }

  .tp-live-table__row--empty .tp-live-table__cell {
    text-align: center;
    color: rgba(148, 163, 184, 0.75);
  }

  .tp-live-table__footer {
    display: flex;
    justify-content: space-between;
    font-size: 0.85rem;
    color: rgba(148, 163, 184, 0.7);
    padding: 0.25rem 0.5rem;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.55);
    backdrop-filter: blur(16px);
  }

  .tp-live-table__sort {
    margin-left: 0.25rem;
  }

  .tp-live-table__row {
    transition: transform 0.35s ease, background 0.35s ease;
  }
`;

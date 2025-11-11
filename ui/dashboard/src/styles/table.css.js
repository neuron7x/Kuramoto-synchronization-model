export const TABLE_STYLES = `
  .tp-live-table {
    display: grid;
    gap: 1.25rem;
  }

  .tp-live-table__viewport {
    overflow-x: auto;
    border-radius: 18px;
    border: 1px solid rgba(99, 179, 237, 0.3);
    background: rgba(10, 15, 30, 0.7);
    box-shadow: 
      0 12px 40px -15px rgba(6, 182, 212, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.06),
      inset 0 0 0 1px rgba(6, 182, 212, 0.1);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-overflow-scrolling: touch;
  }

  .tp-live-table__viewport:focus-visible {
    outline: 2px solid var(--tp-focus-ring);
    outline-offset: 2px;
  }

  .tp-live-table__table {
    width: 100%;
    border-collapse: collapse;
    min-width: 640px;
  }

  .tp-live-table__head {
    background: rgba(6, 182, 212, 0.1);
    backdrop-filter: blur(10px);
  }

  .tp-live-table__row {
    position: relative;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .tp-live-table__row:nth-child(odd) {
    background: rgba(6, 182, 212, 0.03);
  }

  .tp-live-table__row::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--tp-gradient-accent);
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .tp-live-table__row:hover {
    background: rgba(6, 182, 212, 0.15);
    box-shadow: 0 4px 20px -5px rgba(6, 182, 212, 0.4);
  }

  .tp-live-table__row:hover::before {
    opacity: 1;
  }

  .tp-live-table__cell {
    padding: 0.9rem 1.25rem;
    border-bottom: 1px solid rgba(99, 179, 237, 0.15);
    font-size: 0.95rem;
    color: rgba(240, 249, 255, 0.95);
    transition: all 0.3s ease;
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
    letter-spacing: 0.1em;
    font-weight: 700;
    color: rgba(6, 182, 212, 0.95);
    border-bottom: 2px solid rgba(6, 182, 212, 0.3);
    text-shadow: 0 0 10px rgba(6, 182, 212, 0.3);
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
    color: rgba(240, 249, 255, 0.9);
    padding: 0.75rem 1rem;
    border-radius: 14px;
    background: rgba(10, 15, 30, 0.8);
    border: 1px solid rgba(99, 179, 237, 0.25);
    backdrop-filter: blur(20px) saturate(180%);
    gap: 0.75rem;
    box-shadow: 0 4px 12px -5px rgba(6, 182, 212, 0.3);
  }

  .tp-live-table__sort {
    margin-left: 0.25rem;
  }

  .tp-live-table__row {
    transition: transform 0.35s ease, background 0.35s ease;
  }

  @media (max-width: 768px) {
    .tp-live-table__footer {
      flex-wrap: wrap;
      justify-content: flex-start;
      gap: 0.5rem 1rem;
    }

    .tp-live-table__footer-item,
    .tp-live-table__summary {
      width: 100%;
    }
  }
`;

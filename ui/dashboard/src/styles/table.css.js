export const TABLE_STYLES = `
  .tp-live-table {
    display: grid;
    gap: 1.25rem;
  }

  .tp-live-table__viewport {
    overflow-x: auto;
    border-radius: 18px;
    border: 1px solid rgba(99, 179, 237, 0.3);
    background: 
      linear-gradient(135deg, rgba(6, 182, 212, 0.03), rgba(59, 130, 246, 0.02)),
      rgba(10, 15, 30, 0.7);
    box-shadow: 
      0 12px 40px -15px rgba(6, 182, 212, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.06),
      inset 0 0 0 1px rgba(6, 182, 212, 0.1);
    backdrop-filter: blur(20px) saturate(180%);
    -webkit-overflow-scrolling: touch;
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .tp-live-table__viewport:hover {
    box-shadow: 
      0 20px 50px -20px rgba(6, 182, 212, 0.5),
      inset 0 1px 0 rgba(255, 255, 255, 0.08),
      inset 0 0 0 1px rgba(6, 182, 212, 0.15);
    border-color: rgba(6, 182, 212, 0.4);
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
    background: 
      linear-gradient(90deg, rgba(6, 182, 212, 0.12), rgba(59, 130, 246, 0.08), rgba(6, 182, 212, 0.12));
    backdrop-filter: blur(10px);
    position: sticky;
    top: 0;
    z-index: 1;
  }

  .tp-live-table__row {
    position: relative;
    transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
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
    background: var(--tp-gradient-accent, linear-gradient(180deg, #22d3ee, #0891b2));
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .tp-live-table__row::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, rgba(6, 182, 212, 0.08), transparent 50%);
    opacity: 0;
    transition: opacity 0.3s ease;
    pointer-events: none;
  }

  .tp-live-table__row:hover {
    background: rgba(6, 182, 212, 0.12);
    box-shadow: 0 4px 20px -5px rgba(6, 182, 212, 0.4);
  }

  .tp-live-table__row:hover::before {
    opacity: 1;
  }

  .tp-live-table__row:hover::after {
    opacity: 1;
  }

  .tp-live-table__cell {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid rgba(99, 179, 237, 0.12);
    font-size: 0.95rem;
    color: rgba(240, 249, 255, 0.95);
    transition: all 0.3s ease;
    position: relative;
  }

  .tp-live-table__cell--right {
    text-align: right;
  }

  .tp-live-table__cell--center {
    text-align: center;
  }

  .tp-live-table__cell--positive {
    color: #34d399;
  }

  .tp-live-table__cell--negative {
    color: #f87171;
  }

  .tp-live-table__cell--accent {
    color: #22d3ee;
    font-weight: 600;
  }

  .tp-live-table__header {
    text-transform: uppercase;
    font-size: 0.75rem;
    letter-spacing: 0.12em;
    font-weight: 700;
    color: rgba(6, 182, 212, 0.95);
    border-bottom: 2px solid rgba(6, 182, 212, 0.3);
    text-shadow: 0 0 10px rgba(6, 182, 212, 0.3);
    padding: 1.15rem 1.25rem;
    white-space: nowrap;
  }

  .tp-live-table__header--sortable {
    cursor: pointer;
    user-select: none;
    transition: all 0.3s ease;
  }

  .tp-live-table__header--sortable:hover {
    color: #22d3ee;
    background: rgba(6, 182, 212, 0.08);
  }

  .tp-live-table__row--empty .tp-live-table__cell {
    text-align: center;
    color: rgba(148, 163, 184, 0.75);
    padding: 2rem 1.25rem;
    font-style: italic;
  }

  .tp-live-table__footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.85rem;
    color: rgba(240, 249, 255, 0.9);
    padding: 0.85rem 1.15rem;
    border-radius: 14px;
    background: 
      linear-gradient(135deg, rgba(15, 23, 42, 0.8), rgba(10, 15, 30, 0.9));
    border: 1px solid rgba(99, 179, 237, 0.25);
    backdrop-filter: blur(20px) saturate(180%);
    gap: 0.75rem;
    box-shadow: 
      0 4px 16px -5px rgba(6, 182, 212, 0.3),
      inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }

  .tp-live-table__sort {
    margin-left: 0.35rem;
    display: inline-flex;
    align-items: center;
    opacity: 0.6;
    transition: opacity 0.3s ease;
  }

  .tp-live-table__header--sortable:hover .tp-live-table__sort,
  .tp-live-table__sort--active {
    opacity: 1;
    color: #22d3ee;
  }

  .tp-live-table__pagination {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .tp-live-table__page-btn {
    padding: 0.4rem 0.75rem;
    border-radius: 8px;
    border: 1px solid rgba(99, 179, 237, 0.3);
    background: rgba(15, 23, 42, 0.6);
    color: rgba(226, 232, 240, 0.9);
    font-size: 0.85rem;
    cursor: pointer;
    transition: all 0.3s ease;
  }

  .tp-live-table__page-btn:hover {
    background: rgba(6, 182, 212, 0.15);
    border-color: rgba(6, 182, 212, 0.5);
    color: #22d3ee;
  }

  .tp-live-table__page-btn--active {
    background: linear-gradient(120deg, rgba(6, 182, 212, 0.3), rgba(8, 145, 178, 0.3));
    border-color: rgba(6, 182, 212, 0.6);
    color: #22d3ee;
    font-weight: 600;
  }

  /* Row animation for data updates */
  @keyframes tpRowUpdate {
    0% { background: rgba(6, 182, 212, 0.2); }
    100% { background: transparent; }
  }

  .tp-live-table__row--updated {
    animation: tpRowUpdate 1s ease-out;
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

    .tp-live-table__cell {
      padding: 0.75rem 1rem;
      font-size: 0.9rem;
    }

    .tp-live-table__header {
      padding: 0.9rem 1rem;
    }
  }
`;

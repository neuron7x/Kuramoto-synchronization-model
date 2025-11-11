export const CHART_STYLES = `
  .tp-area-chart__container {
    display: grid;
    gap: 1rem;
  }

  .tp-area-chart {
    width: 100%;
    height: auto;
    border-radius: 18px;
    background: rgba(10, 15, 30, 0.7);
    box-shadow: 
      0 12px 40px -15px rgba(6, 182, 212, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.05),
      inset 0 0 0 1px rgba(6, 182, 212, 0.15);
    overflow: hidden;
    position: relative;
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(99, 179, 237, 0.25);
  }

  .tp-area-chart::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(
      135deg, 
      rgba(6, 182, 212, 0.2), 
      rgba(59, 130, 246, 0.15) 50%,
      rgba(34, 211, 238, 0)
    );
    mix-blend-mode: screen;
    opacity: 0;
    transition: opacity 0.6s ease;
    pointer-events: none;
  }

  .tp-area-chart:hover::after {
    opacity: 0.6;
  }

  .tp-chart-legend {
    list-style: none;
    display: grid;
    gap: 0.65rem;
    margin: 0;
    padding: 0;
  }

  .tp-chart-legend__item {
    display: flex;
    justify-content: space-between;
    font-size: 0.9rem;
    color: rgba(240, 249, 255, 0.9);
    padding: 0.7rem 1rem;
    border-radius: 14px;
    background: rgba(20, 30, 55, 0.6);
    backdrop-filter: blur(16px) saturate(180%);
    border: 1px solid rgba(99, 179, 237, 0.15);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
  }

  .tp-chart-legend__item::before {
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

  .tp-chart-legend__item:hover {
    transform: translateX(6px);
    background: rgba(6, 182, 212, 0.15);
    border-color: rgba(6, 182, 212, 0.4);
    box-shadow: 0 6px 20px -8px rgba(6, 182, 212, 0.5);
  }

  .tp-chart-legend__item:hover::before {
    opacity: 1;
  }

  .tp-chart-empty {
    padding: 0.75rem;
    font-size: 0.9rem;
    border: 1px dashed rgba(148, 163, 184, 0.35);
    border-radius: 12px;
    text-align: center;
    color: rgba(148, 163, 184, 0.75);
  }
`;

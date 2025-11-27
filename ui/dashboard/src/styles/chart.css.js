export const CHART_STYLES = `
  .tp-area-chart__container {
    display: grid;
    gap: 1rem;
    position: relative;
  }

  .tp-area-chart {
    width: 100%;
    height: auto;
    border-radius: 18px;
    background: 
      linear-gradient(135deg, rgba(6, 182, 212, 0.05), rgba(59, 130, 246, 0.03)),
      rgba(10, 15, 30, 0.7);
    box-shadow: 
      0 12px 40px -15px rgba(6, 182, 212, 0.4),
      inset 0 1px 0 rgba(255, 255, 255, 0.05),
      inset 0 0 0 1px rgba(6, 182, 212, 0.15);
    overflow: hidden;
    position: relative;
    backdrop-filter: blur(20px) saturate(180%);
    border: 1px solid rgba(99, 179, 237, 0.25);
    transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  }

  .tp-area-chart:hover {
    box-shadow: 
      0 20px 50px -15px rgba(6, 182, 212, 0.5),
      inset 0 1px 0 rgba(255, 255, 255, 0.08),
      inset 0 0 0 1px rgba(6, 182, 212, 0.25);
    border-color: rgba(6, 182, 212, 0.4);
  }

  .tp-area-chart::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 60%;
    background: radial-gradient(
      ellipse at top,
      rgba(6, 182, 212, 0.15),
      transparent 70%
    );
    pointer-events: none;
    opacity: 0.6;
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

  /* Chart grid lines */
  .tp-area-chart__grid {
    stroke: rgba(99, 179, 237, 0.1);
    stroke-dasharray: 4 4;
  }

  /* Chart axis labels */
  .tp-area-chart__axis-label {
    fill: rgba(148, 163, 184, 0.7);
    font-size: 0.75rem;
    font-family: 'Inter', system-ui, sans-serif;
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
    align-items: center;
    font-size: 0.9rem;
    color: rgba(240, 249, 255, 0.9);
    padding: 0.85rem 1.15rem;
    border-radius: 14px;
    background: 
      linear-gradient(135deg, rgba(20, 30, 55, 0.6), rgba(15, 23, 42, 0.4)),
      rgba(20, 30, 55, 0.6);
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
    background: var(--tp-gradient-accent, linear-gradient(180deg, #22d3ee, #0891b2));
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .tp-chart-legend__item::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(90deg, var(--tp-accent-soft, rgba(6, 182, 212, 0.1)), transparent);
    opacity: 0;
    transition: opacity 0.3s ease;
  }

  .tp-chart-legend__item:hover {
    transform: translateX(6px);
    background: 
      linear-gradient(135deg, rgba(6, 182, 212, 0.15), rgba(59, 130, 246, 0.1)),
      rgba(6, 182, 212, 0.1);
    border-color: rgba(6, 182, 212, 0.4);
    box-shadow: 
      0 8px 24px -8px rgba(6, 182, 212, 0.5),
      inset 0 1px 0 rgba(255, 255, 255, 0.05);
  }

  .tp-chart-legend__item:hover::before {
    opacity: 1;
  }

  .tp-chart-legend__item:hover::after {
    opacity: 1;
  }

  .tp-chart-legend__item span {
    position: relative;
    z-index: 1;
    color: rgba(148, 163, 184, 0.9);
    font-size: 0.85rem;
    letter-spacing: 0.02em;
  }

  .tp-chart-legend__item strong {
    position: relative;
    z-index: 1;
    font-weight: 600;
    font-size: 1rem;
    background: linear-gradient(120deg, #22d3ee, #0891b2);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .tp-chart-empty {
    padding: 1.5rem;
    font-size: 0.9rem;
    border: 1px dashed rgba(148, 163, 184, 0.35);
    border-radius: 12px;
    text-align: center;
    color: rgba(148, 163, 184, 0.75);
    background: rgba(15, 23, 42, 0.4);
    backdrop-filter: blur(10px);
  }

  /* Chart tooltip styles */
  .tp-chart-tooltip {
    position: absolute;
    padding: 0.75rem 1rem;
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid rgba(6, 182, 212, 0.4);
    border-radius: 10px;
    font-size: 0.85rem;
    color: rgba(240, 249, 255, 0.95);
    box-shadow: 
      0 8px 24px -8px rgba(6, 182, 212, 0.5),
      0 0 0 1px rgba(6, 182, 212, 0.2);
    backdrop-filter: blur(20px);
    pointer-events: none;
    opacity: 0;
    transform: translateY(5px);
    transition: all 0.2s ease;
  }

  .tp-chart-tooltip--visible {
    opacity: 1;
    transform: translateY(0);
  }

  .tp-chart-tooltip__value {
    font-weight: 700;
    font-size: 1.1rem;
    background: linear-gradient(120deg, #22d3ee, #0891b2);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }

  .tp-chart-tooltip__label {
    color: rgba(148, 163, 184, 0.8);
    font-size: 0.75rem;
    margin-top: 0.25rem;
  }

  /* Responsive chart adjustments */
  @media (max-width: 768px) {
    .tp-chart-legend__item {
      padding: 0.7rem 1rem;
    }

    .tp-chart-legend__item span {
      font-size: 0.8rem;
    }

    .tp-chart-legend__item strong {
      font-size: 0.9rem;
    }
  }
`;

export const CHART_STYLES = `
  .tp-area-chart__container {
    display: grid;
    gap: 0.75rem;
  }

  .tp-area-chart {
    width: 100%;
    height: auto;
    border-radius: 16px;
    background: rgba(15, 23, 42, 0.55);
    box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.15);
    overflow: hidden;
    position: relative;
  }

  .tp-area-chart::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(120deg, rgba(37, 99, 235, 0.15), rgba(56, 189, 248, 0));
    mix-blend-mode: screen;
    opacity: 0;
    transition: opacity 0.6s ease;
    pointer-events: none;
  }

  .tp-area-chart:hover::after {
    opacity: 0.45;
  }

  .tp-chart-legend {
    list-style: none;
    display: grid;
    gap: 0.5rem;
    margin: 0;
    padding: 0;
  }

  .tp-chart-legend__item {
    display: flex;
    justify-content: space-between;
    font-size: 0.9rem;
    color: rgba(226, 232, 240, 0.85);
    padding: 0.5rem 0.75rem;
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.45);
    backdrop-filter: blur(12px);
    transition: transform 0.3s ease, background 0.3s ease;
  }

  .tp-chart-legend__item:hover {
    transform: translateX(4px);
    background: rgba(56, 189, 248, 0.18);
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

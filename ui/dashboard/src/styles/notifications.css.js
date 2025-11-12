/**
 * Notification styles for toast and banner components
 */

export const NOTIFICATION_STYLES = `
  /* Toast container */
  .tp-toast-container {
    position: fixed;
    top: 1rem;
    right: 1rem;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    pointer-events: none;
    max-width: 400px;
  }

  /* Toast base */
  .tp-toast {
    position: relative;
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem;
    background: rgba(15, 23, 42, 0.95);
    border-radius: 8px;
    border: 1px solid rgba(99, 179, 237, 0.3);
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
    backdrop-filter: blur(10px);
    pointer-events: auto;
    animation: tp-toast-slide-in 0.3s ease-out;
    transition: opacity 0.3s ease, transform 0.3s ease;
  }

  .tp-toast--hiding {
    opacity: 0;
    transform: translateX(100%);
  }

  @keyframes tp-toast-slide-in {
    from {
      opacity: 0;
      transform: translateX(100%);
    }
    to {
      opacity: 1;
      transform: translateX(0);
    }
  }

  /* Toast content */
  .tp-toast__content {
    flex: 1;
    font-size: 0.875rem;
    line-height: 1.5;
    color: rgba(240, 249, 255, 0.95);
  }

  /* Toast close button */
  .tp-toast__close {
    flex-shrink: 0;
    width: 1.5rem;
    height: 1.5rem;
    padding: 0;
    background: transparent;
    border: none;
    color: rgba(240, 249, 255, 0.7);
    font-size: 1.25rem;
    line-height: 1;
    cursor: pointer;
    transition: color 0.2s ease;
  }

  .tp-toast__close:hover {
    color: rgba(240, 249, 255, 0.95);
  }

  .tp-toast__close:focus {
    outline: 2px solid #06b6d4;
    outline-offset: 2px;
  }

  /* Toast variants */
  .tp-toast--info {
    border-color: rgba(6, 182, 212, 0.5);
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.1), rgba(15, 23, 42, 0.95));
  }

  .tp-toast--success {
    border-color: rgba(16, 185, 129, 0.5);
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.1), rgba(15, 23, 42, 0.95));
  }

  .tp-toast--warning {
    border-color: rgba(245, 158, 11, 0.5);
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.1), rgba(15, 23, 42, 0.95));
  }

  .tp-toast--error {
    border-color: rgba(239, 68, 68, 0.5);
    background: linear-gradient(135deg, rgba(239, 68, 68, 0.1), rgba(15, 23, 42, 0.95));
  }

  /* Banner base */
  .tp-banner {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.5rem;
    margin-bottom: 1rem;
    background: rgba(15, 23, 42, 0.95);
    border-radius: 8px;
    border: 1px solid rgba(99, 179, 237, 0.3);
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  }

  /* Banner content */
  .tp-banner__content {
    flex: 1;
    font-size: 0.875rem;
    line-height: 1.5;
    color: rgba(240, 249, 255, 0.95);
  }

  /* Banner actions */
  .tp-banner__actions {
    display: flex;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .tp-banner__button {
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    font-weight: 500;
    border-radius: 4px;
    border: 1px solid transparent;
    cursor: pointer;
    transition: all 0.2s ease;
  }

  .tp-banner__button--primary {
    background: #06b6d4;
    color: #ffffff;
    border-color: #06b6d4;
  }

  .tp-banner__button--primary:hover {
    background: #0891b2;
    border-color: #0891b2;
  }

  .tp-banner__button--secondary {
    background: transparent;
    color: rgba(240, 249, 255, 0.95);
    border-color: rgba(99, 179, 237, 0.3);
  }

  .tp-banner__button--secondary:hover {
    background: rgba(99, 179, 237, 0.1);
    border-color: rgba(99, 179, 237, 0.5);
  }

  .tp-banner__button:focus {
    outline: 2px solid #06b6d4;
    outline-offset: 2px;
  }

  /* Banner variants */
  .tp-banner--info {
    border-color: rgba(6, 182, 212, 0.5);
    background: linear-gradient(135deg, rgba(6, 182, 212, 0.1), rgba(15, 23, 42, 0.95));
  }

  .tp-banner--warning {
    border-color: rgba(245, 158, 11, 0.5);
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.1), rgba(15, 23, 42, 0.95));
  }

  .tp-banner--error {
    border-color: rgba(239, 68, 68, 0.5);
    background: linear-gradient(135deg, rgba(239, 68, 68, 0.1), rgba(15, 23, 42, 0.95));
  }

  /* Loading state styles */
  [data-loading="true"] {
    position: relative;
    opacity: 0.6;
    pointer-events: none;
  }

  [data-loading="true"]::after {
    content: '';
    position: absolute;
    top: 50%;
    left: 50%;
    width: 2rem;
    height: 2rem;
    margin: -1rem 0 0 -1rem;
    border: 3px solid rgba(6, 182, 212, 0.2);
    border-top-color: #06b6d4;
    border-radius: 50%;
    animation: tp-spin 0.8s linear infinite;
  }

  @keyframes tp-spin {
    to {
      transform: rotate(360deg);
    }
  }

  /* Responsive adjustments */
  @media (max-width: 640px) {
    .tp-toast-container {
      left: 1rem;
      right: 1rem;
      max-width: none;
    }

    .tp-banner {
      flex-direction: column;
      align-items: flex-start;
    }

    .tp-banner__actions {
      width: 100%;
      justify-content: flex-end;
    }
  }
`;

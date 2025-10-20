export const SAAS_SHELL_STYLES = `
  body.tp-saas {
    margin: 0;
    background: radial-gradient(circle at top right, #0f172a, #020617 75%);
    color: #f8fafc;
  }

  .tp-saas__layout {
    min-height: 100vh;
    display: grid;
    grid-template-columns: minmax(0, 1fr);
  }

  @media (min-width: 1280px) {
    .tp-saas__layout {
      grid-template-columns: 320px minmax(0, 1fr);
    }
  }

  .tp-saas__sidebar {
    padding: 2.5rem 2rem;
    border-right: 1px solid rgba(148, 163, 184, 0.15);
    backdrop-filter: blur(20px);
    background: rgba(15, 23, 42, 0.72);
    display: grid;
    gap: 2rem;
  }

  .tp-saas__brand {
    display: flex;
    align-items: center;
    gap: 1rem;
  }

  .tp-saas__logo {
    width: 44px;
    height: 44px;
    display: grid;
    place-items: center;
    border-radius: 14px;
    background: linear-gradient(135deg, rgba(56, 189, 248, 0.65), rgba(59, 130, 246, 0.85));
    font-weight: 700;
    font-size: 1.1rem;
  }

  .tp-saas__tenant {
    display: grid;
    gap: 0.35rem;
  }

  .tp-saas__tenant-name {
    font-size: 1.2rem;
    font-weight: 600;
    margin: 0;
  }

  .tp-saas__tenant-plan {
    margin: 0;
    color: rgba(226, 232, 240, 0.75);
    font-size: 0.95rem;
  }

  .tp-saas__menu {
    list-style: none;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 0.85rem;
  }

  .tp-saas__menu-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: rgba(226, 232, 240, 0.8);
    font-size: 0.95rem;
  }

  .tp-saas__badge {
    border-radius: 999px;
    padding: 0.2rem 0.6rem;
    font-size: 0.75rem;
    background: rgba(56, 189, 248, 0.15);
    color: rgba(125, 211, 252, 0.95);
    font-weight: 600;
  }

  .tp-saas__footer {
    font-size: 0.8rem;
    color: rgba(148, 163, 184, 0.75);
  }

  .tp-saas__workspace {
    display: grid;
    grid-template-rows: auto 1fr;
    min-height: 100vh;
  }

  .tp-saas__topbar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1.5rem 2rem;
    border-bottom: 1px solid rgba(148, 163, 184, 0.12);
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(18px);
  }

  .tp-saas__topbar-actions {
    display: flex;
    gap: 1rem;
    align-items: center;
  }

  .tp-saas__status {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.3rem 0.8rem;
    border-radius: 999px;
    background: rgba(74, 222, 128, 0.2);
    color: #4ade80;
    font-weight: 600;
    font-size: 0.85rem;
  }

  .tp-saas__action {
    background: linear-gradient(135deg, rgba(59, 130, 246, 0.9), rgba(14, 165, 233, 0.9));
    border: none;
    color: #f8fafc;
    padding: 0.65rem 1.4rem;
    border-radius: 999px;
    font-weight: 600;
    cursor: pointer;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }

  .tp-saas__action:hover {
    transform: translateY(-1px);
    box-shadow: 0 12px 30px -20px rgba(14, 165, 233, 0.75);
  }

  .tp-saas__contact {
    display: grid;
    gap: 0.2rem;
    text-align: right;
  }

  .tp-saas__contact-label {
    font-size: 0.8rem;
    color: rgba(148, 163, 184, 0.8);
  }

  .tp-saas__contact-link {
    color: rgba(125, 211, 252, 0.95);
    text-decoration: none;
    font-weight: 600;
  }

  .tp-saas__dashboard {
    padding: 2rem;
  }

  @media (max-width: 1024px) {
    .tp-saas__topbar {
      flex-direction: column;
      align-items: flex-start;
      gap: 1rem;
    }

    .tp-saas__contact {
      text-align: left;
    }

    .tp-saas__dashboard {
      padding: 1.5rem;
    }
  }
`;

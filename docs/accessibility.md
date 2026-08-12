# Accessibility Playbook

Accessible interfaces are a baseline requirement for GeoSync dashboards and
Next.js applications. This playbook focuses on keyboard navigation, ARIA usage,
colour contrast, and automated audits so a11y stays embedded in the delivery
pipeline.

## Keyboard Navigation Standards

1. **Logical focus order** – Ensure DOM order mirrors visual order. Use semantic
   HTML elements (`<header>`, `<main>`, `<nav>`, `<section>`) to let browsers
   manage focus naturally.
2. **Skip links** – Add a persistent `Skip to main content` link as the first
   focusable element. Reveal it visually when focused using utility CSS.
3. **Focus visibility** – Replace default outlines with high-contrast focus
   rings. For custom components, set `tabindex="0"` and handle `keydown`
   events for `Enter`/`Space` actions.
4. **Modal traps** – When opening dialogs, move focus inside and trap tab order
   until the modal is closed. Restore focus to the triggering control afterwards.
5. **Interactive tables** – Provide keyboard shortcuts (e.g., `ArrowUp`,
   `ArrowDown`, `Home`, `End`) for grid navigation. Use `aria-colindex` and
   `aria-rowindex` when virtualising rows.

## ARIA Role Guidelines

- Prefer native elements (`<button>`, `<a>`, `<label>`) before adding ARIA.
- When ARIA is required, pair `role` with the appropriate state/attribute:
  - `role="button"` → include `aria-pressed` if toggleable.
  - `role="tablist"` → ensure child tabs expose `aria-selected` and
    `aria-controls`.
  - `role="alert"` → emit only for urgent, assertive notifications.
- For composable charts, expose data via hidden tables using `aria-describedby`
  so screen readers can consume textual summaries.
- Keep `aria-live` regions concise; favour `polite` updates to reduce cognitive
  load.

## Contrast and Visual Verification

- Maintain **minimum contrast ratios**: 4.5:1 for regular text, 3:1 for large
  text/icons, and 3:1 for interactive UI states (hover/focus).
- Define theme tokens (`--color-surface`, `--color-text-strong`, etc.) and audit
  combinations during design reviews.
- Use tooling such as `@axe-core/react`, Storybook accessibility add-ons, or the
  Chrome Accessibility panel to flag regressions before code review.

## Automated aXe Testing Pipeline

1. **Component tests** – Add `jest-axe` or `@axe-core/playwright` checks to
   ensure isolated components respect rulesets.
2. **Integration smoke tests** – For each Next.js route, run an aXe scan once in
   CI to catch layout-level violations. Example Playwright snippet:
   ```ts
   import AxeBuilder from '@axe-core/playwright';

   test('portfolio dashboard is accessible', async ({ page }) => {
     await page.goto('/portfolio');
     const accessibilityScanResults = await new AxeBuilder({ page })
       .withTags(['wcag2a', 'wcag2aa'])
       .analyze();
     expect(accessibilityScanResults.violations).toEqual([]);
   });
   ```
3. **Budget gates** – Treat new violations as blockers. Configure CI to fail the
   pipeline if any `serious` or `critical` issues remain.

## Manual Verification Checklist

- [ ] Every interactive control reachable via keyboard alone.
- [ ] Focus never disappears when modals or overlays close.
- [ ] Screen-reader announcement for async events (fills, rejected orders) uses
      concise descriptions.
- [ ] Charts and analytics provide accessible summaries (`aria-describedby` or
      visually hidden `<dl>` blocks).
- [ ] Nightly aXe scans produce zero `serious` violations.

Embed these practices into feature definitions and PR templates so accessibility
remains a continuous activity rather than a release-end scramble.

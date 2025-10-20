# Localization Review Checklist

Use this checklist alongside `scripts/localization/sync_translations.py` and `make i18n-validate` before every release train lock.

## 1. Preparation

- [ ] Pull the latest vendor handoff package and run `make i18n-validate`.
- [ ] Confirm `reports/localization/coverage.json` updated with current run timestamp.
- [ ] Verify locale metadata regenerated from `configs/localization/locales.yaml`.

## 2. Native Speaker QA Sessions

| Locale | Reviewer(s) | Agenda |
| --- | --- | --- |
| en-US | NY trading-ops linguists | Validate tone-critical dashboard strings, verify telemetry terminology. |
| uk-UA | Kyiv localization guild | Confirm regulatory phrasing, check charts/tables for truncated text. |
| de-DE | Frankfurt compliance linguists | Audit legal disclaimers, ensure decimal/thousand separators render correctly. |
| ja-JP | Tokyo regulatory advisors | Review honorific tone, confirm financial abbreviations match FSA guidance. |

- [ ] Record QA outcomes in Confluence page `Localization QA <YYYY-MM-DD>`.
- [ ] Capture screenshots of key flows in all locales (navigation, orders, positions, PnL).

## 3. Scripted Verification

- [ ] Run smoke tests referencing locale toggles: `npm test -- dashboard:i18n` (pending automation).
- [ ] Ensure `scripts/localization/sync_translations.py --check` reports zero missing or extra keys.
- [ ] Validate JSON schema compliance for each locale bundle.

## 4. Privacy & Legal Review

- [ ] Cross-check locale-specific privacy strings (GDPR/CCPA/BDSG/APPI) with Legal sign-off.
- [ ] Confirm consent tracking events include locale dimension for analytics.
- [ ] Validate data residency statements are accurate per release target.

## 5. Sign-off Workflow

- [ ] Localization Lead approves checklist in Jira ticket (`LOC-*`).
- [ ] Legal & Compliance confirm regulatory updates processed.
- [ ] Engineering lead signs off on telemetry dashboards reflecting latest metrics.
- [ ] Release manager gates deployment until all boxes checked.


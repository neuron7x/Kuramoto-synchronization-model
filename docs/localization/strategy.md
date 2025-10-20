# Localization and Formatting Strategy

TradePulse derives human-readable number and timestamp formatting from a shared configuration so the dashboard and backend services present consistent information across locales. This document outlines the contract, the supporting runtime, and the process for adding or updating locales.

## Configuration Source

Localization metadata lives in [`configs/localization/locales.yaml`](../../configs/localization/locales.yaml). The file is valid JSON (and therefore valid YAML) and contains three top-level sections:

- `defaults`: Provides fallback values, including the prioritized locale list, a default currency, the default trading session timezone, and base `Intl.DateTimeFormat` options.
- `locales`: A map of locale identifiers to their formatting rules. Each entry can override the default currency, timezone, number symbols, and provide per-locale `number`, `currency`, `percent`, and `datetime` options that are passed directly to `Intl.NumberFormat`/`Intl.DateTimeFormat`.
- `currency_overrides`: Asset codes that should format with a different currency than the locale default (for example, synthetic assets pegged to USD).

### Adding or Updating a Locale

1. **Edit the configuration**:
   - Add the BCP-47 tag to the `defaults.locale_priority` array in descending order of preference.
   - Create (or update) the entry in `locales` with:
     - `currency`: ISO-4217 code used when no override applies.
     - `timezone`: IANA timezone name for trading session timestamps.
     - `symbols`: Decimal and grouping separators used for telemetry and analytics.
     - `formats`: Objects matching the `Intl.NumberFormat`/`Intl.DateTimeFormat` options that control number, currency, percent, and timestamp formatting.
   - Optional: Extend `currency_overrides` if certain instruments require bespoke currencies.
2. **Validate the timezone**: the backend calls `validate_timezone` (via `core.localization.runtime`) which falls back to `UTC` and emits a warning when a timezone is invalid. Prefer canonical names from the IANA database.
3. **Run regression tests**:
   - JavaScript unit tests under `ui/dashboard/tests` verify decimal/grouping separators and localized timestamps for representative locales.
   - Python unit tests under `tests/unit/test_localization.py` cover negotiation and currency override behaviour.
4. **Update documentation and dashboards as required** to reference the new locale options for operators.

## Runtime Consumption

### Front-end

The dashboard resolves locale-aware formatters through [`ui/dashboard/src/i18n/number_format.js`](../../ui/dashboard/src/i18n/number_format.js). The module loads the catalog once, memoizes `Intl.NumberFormat`/`Intl.DateTimeFormat` instances per locale, and exposes helpers to:

- Resolve the negotiated locale, currency, and timezone for a session.
- Format numbers, currencies, percentages, and timestamps with optional locale overrides.
- Emit telemetry (`localization.fallback`) when a requested locale is unsupported so product telemetry can track fallback frequency.

Dashboard views receive the negotiated localization context (locale, currency, timezone) from `renderDashboard` and pass it through to the formatters to ensure tables and summaries use the correct separators and currency symbols.

### Backend

Backend services use the helpers in [`core/localization/runtime.py`](../../core/localization/runtime.py) to parse the catalog, negotiate the preferred locale, and validate timezones. [`scripts/_runtime_core.py`](../../scripts/_runtime_core.py) applies the negotiated locale and timezone during runtime initialization so deterministic scripts respect the configured defaults. Service settings can request localization rules via [`application/settings.py`](../../application/settings.py) through the `get_localization_settings` helper, which returns a serialisable `LocalizationSettings` model suitable for dependency injection.

## Currency Override Rules

- Asset-specific overrides are declared in the `currency_overrides` section of the catalog and are merged with any runtime-provided overrides (for example, per-portfolio mappings).
- Front-end formatters call `LocaleFormatRules.resolve_currency` equivalents to respect overrides when formatting instrument-level data.
- Backend consumers should use the `LocaleFormatRules` returned by `negotiate_locale` to derive the correct currency for reporting pipelines.

## Timezone Handling

- The prioritized locale defines the default trading session timezone. If a locale omits the timezone, the runtime falls back to the default defined in `defaults`.
- Backend initialization calls `validate_timezone` to ensure the configured timezone exists. On POSIX systems the timezone is applied via `TZ`/`tzset` so libraries that rely on process-level timezone pick up the correct offset.
- Front-end timestamp formatting always passes the negotiated timezone to `Intl.DateTimeFormat`, ensuring browser rendering and server-side logs align with the same session clock.

## Telemetry and Observability

Telemetry listeners registered via `subscribeTelemetry` receive `localization.fallback` events emitted whenever the runtime falls back to a supported locale. The event payload includes the requested locale list and the resolved locale so product analytics can track unsupported locales and prioritise future rollouts.

## Checklist for New Locales

- [ ] Update `configs/localization/locales.yaml` with the locale metadata and currency overrides.
- [ ] Add the locale to `defaults.locale_priority` in the desired order.
- [ ] Confirm the timezone is valid using `zoneinfo` or via unit tests.
- [ ] Run `npm test` under `ui/dashboard` and `pytest tests/unit/test_localization.py` to validate formatting behaviour.
- [ ] Update any user-facing documentation or release notes as required.

Following this process keeps formatting consistent between the dashboard and backend services while providing a clear path to onboard new markets.

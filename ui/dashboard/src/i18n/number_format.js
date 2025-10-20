import { recordLocalizationFallback } from '../core/telemetry.js';

const DEFAULT_CATALOG = Object.freeze({
  defaults: {
    locale_priority: ['en-US'],
    currency: 'USD',
    timezone: 'UTC',
    datetime: {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
      timeZoneName: 'short',
    },
  },
  locales: {
    'en-US': {
      currency: 'USD',
      timezone: 'UTC',
      symbols: { decimal: '.', group: ',' },
      formats: {
        number: { minimumFractionDigits: 0, maximumFractionDigits: 2, useGrouping: true },
        currency: { minimumFractionDigits: 2, maximumFractionDigits: 2 },
        percent: { minimumFractionDigits: 2, maximumFractionDigits: 2 },
        datetime: {
          year: 'numeric',
          month: '2-digit',
          day: '2-digit',
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hourCycle: 'h23',
          timeZoneName: 'short',
        },
      },
    },
  },
  currency_overrides: {},
});

let localeCatalog = null;
let defaultContext = null;
const formatterCache = new Map();

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function normaliseLocaleTag(tag) {
  return String(tag || '').replace(/_/g, '-').trim();
}

function normaliseList(value, fallback = []) {
  if (!value) {
    return fallback.slice();
  }
  if (Array.isArray(value)) {
    return value.map((entry) => normaliseLocaleTag(entry)).filter((entry) => entry);
  }
  return [normaliseLocaleTag(value)].filter((entry) => entry);
}

function mergeLocaleEntry(baseEntry = {}, overrideEntry = {}, defaults = {}) {
  const baseFormats = baseEntry.formats || {};
  const overrideFormats = overrideEntry.formats || {};
  return {
    currency: overrideEntry.currency || baseEntry.currency || defaults.currency || 'USD',
    timezone: overrideEntry.timezone || baseEntry.timezone || defaults.timezone || 'UTC',
    symbols: {
      ...(baseEntry.symbols || {}),
      ...(overrideEntry.symbols || {}),
    },
    formats: {
      number: {
        ...(baseFormats.number || {}),
        ...(overrideFormats.number || {}),
      },
      currency: {
        ...(baseFormats.currency || {}),
        ...(overrideFormats.currency || {}),
      },
      percent: {
        ...(baseFormats.percent || {}),
        ...(overrideFormats.percent || {}),
      },
      datetime: {
        ...((defaults && defaults.datetime) || {}),
        ...(baseFormats.datetime || {}),
        ...(overrideFormats.datetime || {}),
      },
    },
  };
}

function normaliseCatalog(rawCatalog = {}) {
  const base = clone(DEFAULT_CATALOG);
  const defaults = {
    ...base.defaults,
    ...(rawCatalog.defaults || {}),
  };
  defaults.locale_priority = normaliseList(
    rawCatalog.defaults?.locale_priority,
    base.defaults.locale_priority,
  );

  const locales = {};
  const sourceLocales = { ...base.locales, ...(rawCatalog.locales || {}) };
  Object.entries(sourceLocales).forEach(([key, value]) => {
    const normalisedKey = normaliseLocaleTag(key) || 'en-US';
    const baseEntry = base.locales[key] || base.locales[normalisedKey] || base.locales['en-US'];
    locales[normalisedKey] = mergeLocaleEntry(baseEntry, value || {}, defaults);
  });
  if (!locales['en-US']) {
    locales['en-US'] = mergeLocaleEntry(base.locales['en-US'], {}, defaults);
  }

  const currencyOverrides = {
    ...(base.currency_overrides || {}),
    ...(rawCatalog.currency_overrides || {}),
  };

  return { defaults, locales, currency_overrides: currencyOverrides };
}

function loadCatalog() {
  if (localeCatalog) {
    return localeCatalog;
  }
  if (typeof globalThis !== 'undefined' && globalThis.TRADEPULSE_LOCALE_METADATA) {
    localeCatalog = normaliseCatalog(globalThis.TRADEPULSE_LOCALE_METADATA);
    return localeCatalog;
  }
  localeCatalog = normaliseCatalog(DEFAULT_CATALOG);
  return localeCatalog;
}

function isLocalizationDescriptor(value) {
  if (!value || typeof value !== 'object') {
    return false;
  }
  if (Array.isArray(value)) {
    return false;
  }
  return (
    'locale' in value ||
    'preferredLocales' in value ||
    'currencyOverride' in value ||
    'timezone' in value ||
    'assetCurrencyMap' in value
  );
}

function mergeCurrencyOverrides(baseOverrides = {}, extra = {}) {
  const merged = { ...baseOverrides };
  Object.entries(extra || {}).forEach(([key, value]) => {
    if (value) {
      merged[String(key)] = String(value);
    }
  });
  return merged;
}

function selectLocale(preferredLocales = []) {
  const catalog = loadCatalog();
  const defaults = catalog.defaults || {};
  const priority = normaliseList(defaults.locale_priority, ['en-US']);
  const requested = normaliseList(preferredLocales || []);
  const locales = catalog.locales || {};
  const candidates = [...requested, ...priority];
  for (const candidate of candidates) {
    if (!candidate) {
      continue;
    }
    if (locales[candidate]) {
      return { locale: candidate, entry: locales[candidate], matched: requested.includes(candidate) };
    }
    const legacy = candidate.replace(/-/g, '_');
    const normalisedLegacy = normaliseLocaleTag(legacy);
    if (locales[normalisedLegacy]) {
      return {
        locale: normaliseLocaleTag(candidate),
        entry: locales[normalisedLegacy],
        matched: requested.includes(candidate) || requested.includes(normalisedLegacy),
      };
    }
  }
  const fallbackLocale = Object.keys(locales)[0] || 'en-US';
  const entry = locales[fallbackLocale] || locales['en-US'];
  return { locale: normaliseLocaleTag(fallbackLocale), entry, matched: requested.includes(fallbackLocale) };
}

function resolveLocalization(preferredLocales, options = {}) {
  const catalog = loadCatalog();
  const { locale, entry, matched } = selectLocale(preferredLocales);
  if (!matched && preferredLocales && preferredLocales.length) {
    recordLocalizationFallback({
      requestedLocales: preferredLocales.map((value) => normaliseLocaleTag(value)),
      resolvedLocale: locale,
    });
  }

  const defaults = catalog.defaults || {};
  const formats = entry.formats || {};
  const currency = options.currencyOverride || entry.currency || defaults.currency || 'USD';
  const timezone = entry.timezone || defaults.timezone || 'UTC';
  const context = {
    locale,
    currency,
    timezone,
    formats: {
      number: { ...(formats.number || {}) },
      currency: { ...(formats.currency || {}) },
      percent: { ...(formats.percent || {}) },
      datetime: { ...(formats.datetime || {}) },
    },
    symbols: { ...(entry.symbols || {}) },
    currencyOverrides: mergeCurrencyOverrides(
      catalog.currency_overrides || {},
      options.assetCurrencyMap || {},
    ),
  };
  return context;
}

function getDefaultLocalizationContext() {
  if (!defaultContext) {
    defaultContext = resolveLocalization([]);
  }
  return defaultContext;
}

export function registerLocaleCatalog(rawCatalog) {
  localeCatalog = normaliseCatalog(rawCatalog || {});
  defaultContext = null;
  formatterCache.clear();
  if (typeof globalThis !== 'undefined') {
    globalThis.TRADEPULSE_LOCALE_METADATA = localeCatalog;
  }
  return localeCatalog;
}

export function getLocaleCatalog() {
  return loadCatalog();
}

function getLocalizationContext(descriptor) {
  if (!descriptor) {
    return getDefaultLocalizationContext();
  }
  if (typeof descriptor === 'string') {
    return resolveLocalization([descriptor]);
  }
  if (Array.isArray(descriptor)) {
    return resolveLocalization(descriptor);
  }
  if (descriptor && typeof descriptor === 'object') {
    if (descriptor.formats && descriptor.locale) {
      return descriptor;
    }
    const hasBackendFormats =
      'number' in descriptor ||
      'currency_format' in descriptor ||
      'percent' in descriptor ||
      'datetime' in descriptor;
    if (hasBackendFormats) {
      const base = resolveLocalization(descriptor.locale ? [descriptor.locale] : undefined);
      const numberOptions = descriptor.number || {};
      const currencyOptions = descriptor.currency_format || {};
      const percentOptions = descriptor.percent || {};
      const datetimeOptions = descriptor.datetime || {};
      const backendCurrencyOverrides =
        descriptor.currency_overrides || descriptor.currencyOverrides || {};
      const assetCurrencyMap = descriptor.assetCurrencyMap || {};
      return {
        ...base,
        locale: descriptor.locale || base.locale,
        currency: descriptor.currency || base.currency,
        timezone: descriptor.timezone || base.timezone,
        formats: {
          number: { ...(base.formats?.number || {}), ...numberOptions },
          currency: { ...(base.formats?.currency || {}), ...currencyOptions },
          percent: { ...(base.formats?.percent || {}), ...percentOptions },
          datetime: { ...(base.formats?.datetime || {}), ...datetimeOptions },
        },
        symbols: { ...(base.symbols || {}), ...(descriptor.symbols || {}) },
        currencyOverrides: mergeCurrencyOverrides(
          mergeCurrencyOverrides(base.currencyOverrides || {}, backendCurrencyOverrides),
          assetCurrencyMap,
        ),
      };
    }
    if (descriptor.preferredLocales || descriptor.currencyOverride || descriptor.assetCurrencyMap) {
      return resolveLocalization(descriptor.preferredLocales, {
        currencyOverride: descriptor.currencyOverride,
        assetCurrencyMap: descriptor.assetCurrencyMap,
      });
    }
    if (descriptor.locale || descriptor.currency || descriptor.timezone) {
      const base = resolveLocalization(descriptor.locale ? [descriptor.locale] : undefined, {
        currencyOverride: descriptor.currencyOverride,
        assetCurrencyMap: descriptor.assetCurrencyMap,
      });
      return {
        ...base,
        currency: descriptor.currency || base.currency,
        timezone: descriptor.timezone || base.timezone,
      };
    }
  }
  return getDefaultLocalizationContext();
}

export function resolveLocalizationContext(preferredLocales, options = {}) {
  return resolveLocalization(preferredLocales, options);
}

export function getLocalizationDescriptor(input) {
  return getLocalizationContext(input);
}

function normaliseCacheValue(value) {
  if (!value || typeof value !== 'object') {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => normaliseCacheValue(item));
  }
  return Object.keys(value)
    .sort()
    .reduce((acc, key) => {
      acc[key] = normaliseCacheValue(value[key]);
      return acc;
    }, {});
}

function makeCacheKey(type, locale, currency, options) {
  return JSON.stringify(
    normaliseCacheValue({ type, locale, currency: currency || null, options: options || {} }),
  );
}

function getCachedFormatter(cacheKey, factory) {
  if (!formatterCache.has(cacheKey)) {
    formatterCache.set(cacheKey, factory());
  }
  return formatterCache.get(cacheKey);
}

export function getNumberFormatter(localization, overrides = {}) {
  const context = getLocalizationContext(localization);
  const options = { ...(context.formats.number || {}), ...(overrides || {}) };
  const key = makeCacheKey('number', context.locale, null, options);
  return getCachedFormatter(key, () => new Intl.NumberFormat(context.locale, options));
}

export function getPercentFormatter(localization, overrides = {}) {
  const context = getLocalizationContext(localization);
  const options = {
    ...(context.formats.percent || {}),
    ...(overrides || {}),
    style: 'percent',
  };
  const key = makeCacheKey('percent', context.locale, null, options);
  return getCachedFormatter(key, () => new Intl.NumberFormat(context.locale, options));
}

export function getCurrencyFormatter(localization, currencyCode, overrides = {}) {
  const context = getLocalizationContext(localization);
  const currency = currencyCode || context.currency;
  const options = {
    ...(context.formats.currency || {}),
    ...(overrides || {}),
    style: 'currency',
    currency,
  };
  const key = makeCacheKey('currency', context.locale, currency, options);
  return getCachedFormatter(key, () => new Intl.NumberFormat(context.locale, options));
}

export function getDateTimeFormatter(localization, overrides = {}) {
  const context = getLocalizationContext(localization);
  const base = context.formats.datetime || {};
  const options = {
    ...base,
    timeZone: context.timezone,
    ...(overrides || {}),
  };
  if (!options.timeZone) {
    options.timeZone = context.timezone;
  }
  const key = makeCacheKey('datetime', context.locale, options.timeZone, options);
  return getCachedFormatter(key, () => new Intl.DateTimeFormat(context.locale, options));
}

export function getDefaultLocalization() {
  return getDefaultLocalizationContext();
}

export { getLocalizationContext };

export function resetLocalizationForTests() {
  localeCatalog = null;
  defaultContext = null;
  formatterCache.clear();
}

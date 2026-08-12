import { defaultLocale, getFallbackChain, supportedLocales } from './config.js';

function normalise(locale) {
  return typeof locale === 'string' ? locale.trim() : '';
}

// Keys forbidden as query parameters because writing them into a plain object
// would trigger prototype pollution. Rejected explicitly even though the
// accumulator below is a Map (prototype-immune by construction).
const FORBIDDEN_QUERY_KEYS = new Set(['__proto__', 'constructor', 'prototype']);
// Only keys matching this whitelist are ever written into the returned object.
// Defence-in-depth against js/remote-property-injection: user-provided
// property names can never reach object indexing.
const SAFE_KEY_PATTERN = /^[a-z][a-z0-9_-]{0,31}$/;

function parseQuery(search) {
  if (typeof search !== 'string' || search.length === 0) {
    return Object.create(null);
  }
  const out = Object.create(null);
  for (const pair of search.replace(/^\?/, '').split('&').filter(Boolean)) {
    const [rawKey, rawValue] = pair.split('=');
    const key = decodeURIComponent(rawKey || '').toLowerCase();
    if (!key || FORBIDDEN_QUERY_KEYS.has(key) || !SAFE_KEY_PATTERN.test(key)) {
      continue;
    }
    const value = decodeURIComponent(rawValue || '');
    // eslint-disable-next-line security/detect-object-injection -- key is SAFE_KEY_PATTERN-validated
    out[key] = value;
  }
  return out;
}

function safeDecode(value) {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function parseCookies(cookieString) {
  if (typeof cookieString !== 'string' || cookieString.length === 0) {
    return Object.create(null);
  }
  const out = Object.create(null);
  for (const segment of cookieString.split(';').map((s) => s.trim()).filter(Boolean)) {
    const separatorIndex = segment.indexOf('=');
    const keyRaw =
      separatorIndex >= 0 ? safeDecode(segment.slice(0, separatorIndex).trim()) : safeDecode(segment);
    const key = keyRaw.toLowerCase();
    if (!key || FORBIDDEN_QUERY_KEYS.has(key) || !SAFE_KEY_PATTERN.test(key)) {
      continue;
    }
    const value = separatorIndex >= 0 ? safeDecode(segment.slice(separatorIndex + 1).trim()) : '';
    // eslint-disable-next-line security/detect-object-injection -- key is SAFE_KEY_PATTERN-validated
    out[key] = value;
  }
  return out;
}

export function detectLocale({
  search = typeof window !== 'undefined' ? window.location.search : '',
  hash = typeof window !== 'undefined' ? window.location.hash : '',
  navigatorLanguage = typeof navigator !== 'undefined' ? navigator.language : '',
  storageLocale = typeof window !== 'undefined' ? window.localStorage?.getItem('tp:locale') : null,
  cookies = typeof document !== 'undefined' ? document.cookie : '',
  explicitLocale,
} = {}) {
  const query = { ...parseQuery(search), ...parseQuery(hash.includes('?') ? hash.substring(hash.indexOf('?')) : '') };
  const cookieLocale = parseCookies(cookies).tp_locale;
  const requested = normalise(explicitLocale || query.locale || query.lang || cookieLocale || storageLocale || navigatorLanguage);
  const chain = getFallbackChain(requested).concat(getFallbackChain(defaultLocale));
  const unique = chain.filter(Boolean).filter((value, index, arr) => arr.indexOf(value) === index);
  const locale = unique.find((candidate) => supportedLocales.includes(candidate)) || defaultLocale;
  return { locale, requested: requested || null };
}

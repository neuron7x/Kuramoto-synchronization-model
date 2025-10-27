import { defaultLocale, getFallbackChain, supportedLocales } from './config.js';

function normalise(locale) {
  return typeof locale === 'string' ? locale.trim() : '';
}

function parseQuery(search) {
  if (typeof search !== 'string' || search.length === 0) {
    return {};
  }
  return search
    .replace(/^\?/, '')
    .split('&')
    .filter(Boolean)
    .reduce((acc, pair) => {
      const [rawKey, rawValue] = pair.split('=');
      const key = decodeURIComponent(rawKey || '').toLowerCase();
      const value = decodeURIComponent(rawValue || '');
      if (key) {
        acc[key] = value;
      }
      return acc;
    }, {});
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
    return {};
  }
  return cookieString
    .split(';')
    .map((segment) => segment.trim())
    .filter(Boolean)
    .reduce((acc, segment) => {
      const separatorIndex = segment.indexOf('=');
      const key =
        separatorIndex >= 0 ? safeDecode(segment.slice(0, separatorIndex).trim()) : safeDecode(segment);
      const value =
        separatorIndex >= 0 ? safeDecode(segment.slice(separatorIndex + 1).trim()) : '';
      if (key) {
        acc[key] = value;
      }
      return acc;
    }, {});
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

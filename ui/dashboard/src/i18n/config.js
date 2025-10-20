import metadata from './locales.metadata.json' assert { type: 'json' };

export const localeMetadata = metadata.locales;
export const defaultLocale = metadata.defaultLocale;
export const fallbackLocale = metadata.fallbackLocale || metadata.defaultLocale;
export const supportedLocales = Object.keys(localeMetadata);

export function getLocaleConfig(locale) {
  return localeMetadata[locale] || null;
}

export function getFallbackChain(locale) {
  const candidates = [locale, locale?.split('-')[0], fallbackLocale, defaultLocale].filter(Boolean);
  return candidates.filter((value, index) => candidates.indexOf(value) === index);
}

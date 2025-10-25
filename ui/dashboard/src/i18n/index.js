import { localeMetadata, defaultLocale, fallbackLocale, getFallbackChain, supportedLocales } from './config.js';
import { detectLocale } from './detector.js';
import { recordLocaleAdopted, recordLocaleFallback, recordMissingTranslation } from '../core/telemetry.js';

import enUS from './locales/en-US.json' assert { type: 'json' };
import ukUA from './locales/uk-UA.json' assert { type: 'json' };
import deDE from './locales/de-DE.json' assert { type: 'json' };
import jaJP from './locales/ja-JP.json' assert { type: 'json' };
import esES from './locales/es-ES.json' assert { type: 'json' };
import frFR from './locales/fr-FR.json' assert { type: 'json' };
import ptBR from './locales/pt-BR.json' assert { type: 'json' };
import zhCN from './locales/zh-CN.json' assert { type: 'json' };
import itIT from './locales/it-IT.json' assert { type: 'json' };
import hiIN from './locales/hi-IN.json' assert { type: 'json' };
import plPL from './locales/pl-PL.json' assert { type: 'json' };
import arSA from './locales/ar-SA.json' assert { type: 'json' };

const catalog = {
  'en-US': enUS,
  'uk-UA': ukUA,
  'de-DE': deDE,
  'ja-JP': jaJP,
  'es-ES': esES,
  'fr-FR': frFR,
  'pt-BR': ptBR,
  'zh-CN': zhCN,
  'it-IT': itIT,
  'hi-IN': hiIN,
  'pl-PL': plPL,
  'ar-SA': arSA,
};

function flattenKey(key) {
  return String(key || '').trim();
}

function getFromObject(object, key) {
  const path = flattenKey(key).split('.');
  let current = object;
  for (const segment of path) {
    if (current == null) {
      return undefined;
    }
    current = current[segment];
  }
  return current;
}

function interpolate(template, params = {}) {
  return template.replace(/\{(\w+)\}/g, (_, placeholder) => {
    if (Object.prototype.hasOwnProperty.call(params, placeholder)) {
      const value = params[placeholder];
      return value == null ? '' : String(value);
    }
    return '';
  });
}

export class I18n {
  constructor({ locale = defaultLocale } = {}) {
    this.metadata = localeMetadata;
    this.locale = locale;
    this.translations = catalog;
    this.pluralRules = new Map();
    recordLocaleAdopted(this.locale, { source: 'init' });
    if (typeof window !== 'undefined' && window.localStorage) {
      try {
        window.localStorage.setItem('tp:locale', this.locale);
      } catch (error) {
        if (typeof console !== 'undefined' && console.debug) {
          console.debug('Unable to persist initial locale', error);
        }
      }
    }
  }

  setLocale(nextLocale, options = {}) {
    const detected = detectLocale({ explicitLocale: nextLocale });
    if (!supportedLocales.includes(detected.locale)) {
      recordLocaleFallback({
        requested: detected.requested || nextLocale,
        resolved: fallbackLocale,
        reason: 'unsupported-locale',
      });
    }
    if (detected.locale !== this.locale) {
      this.locale = detected.locale;
      recordLocaleAdopted(this.locale, { source: options.source || 'switch' });
      if (typeof window !== 'undefined' && window.localStorage) {
        try {
          window.localStorage.setItem('tp:locale', this.locale);
        } catch (error) {
          if (typeof console !== 'undefined' && console.debug) {
            console.debug('Unable to persist locale preference', error);
          }
        }
      }
    }
    return this.locale;
  }

  getLocale() {
    return this.locale;
  }

  getLocaleConfig(locale = this.locale) {
    return localeMetadata[locale] || null;
  }

  resolve(key, { locale = this.locale } = {}) {
    const path = flattenKey(key);
    const chain = getFallbackChain(locale).filter(Boolean);
    for (let index = 0; index < chain.length; index += 1) {
      const candidate = chain[index];
      const translation = this.translations[candidate];
      if (!translation) {
        continue;
      }
      const value = getFromObject(translation, path);
      if (value !== undefined) {
        if (index > 0) {
          recordLocaleFallback({
            requested: chain[0],
            resolved: candidate,
            reason: 'missing-key',
            key: path,
          });
        }
        return value;
      }
    }
    recordMissingTranslation({ locale: chain[0] || locale, key: path });
    return undefined;
  }

  t(key, params = {}) {
    const raw = this.resolve(key, params);
    if (raw == null) {
      return key;
    }
    if (typeof raw === 'object') {
      if (params.count != null) {
        return this.plural(key, params.count, params);
      }
      return JSON.parse(JSON.stringify(raw));
    }
    return interpolate(String(raw), params);
  }

  plural(key, count, params = {}) {
    const raw = this.resolve(key, params);
    if (raw == null || typeof raw !== 'object') {
      return interpolate(String(raw ?? key), { ...params, count });
    }
    const locale = this.locale;
    if (!this.pluralRules.has(locale)) {
      this.pluralRules.set(locale, new Intl.PluralRules(locale));
    }
    const rules = this.pluralRules.get(locale);
    const category = rules.select(Number(count));
    const template = raw[category] ?? raw.other;
    if (!template) {
      recordMissingTranslation({ locale, key: `${key}.${category}` });
      return interpolate(String(raw.other ?? key), { ...params, count });
    }
    return interpolate(String(template), { ...params, count });
  }

  get(key, params) {
    return this.resolve(key, params);
  }
}

export const i18n = new I18n(detectLocale());

export const t = (...args) => i18n.t(...args);
export const getLocale = () => i18n.getLocale();
export const setLocale = (locale, options) => i18n.setLocale(locale, options);
export const getLocaleConfig = (locale) => i18n.getLocaleConfig(locale);
export const getMessage = (key, params) => i18n.get(key, params);

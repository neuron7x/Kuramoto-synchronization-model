/**
 * I18n Debug Overlay
 * Provides tools for translation debugging, missing key detection, and RTL preview
 */

import { escapeHtml } from '../core/formatters.js';
import { supportedLocales, localeMetadata } from './config.js';
import { getLocale, getMessage } from './index.js';

/**
 * Get all missing translation keys
 * @returns {Array} - Array of missing keys
 */
export function getMissingKeys() {
  if (typeof window === 'undefined' || !window.tp || !window.tp.missingKeys) {
    return [];
  }
  return Array.from(window.tp.missingKeys || []);
}

/**
 * Clear missing keys tracking
 */
export function clearMissingKeys() {
  if (typeof window !== 'undefined' && window.tp) {
    window.tp.missingKeys = new Set();
  }
}

/**
 * Export translations as JSON
 * @param {string} locale - Locale code
 * @returns {string} - JSON string
 */
export function exportTranslations(locale) {
  const messages = getMessage(null, locale) || {};
  return JSON.stringify(messages, null, 2);
}

/**
 * Get locale statistics
 * @param {string} locale - Locale code
 * @returns {Object} - Statistics object
 */
export function getLocaleStats(locale) {
  const messages = getMessage(null, locale) || {};
  
  function countKeys(obj, prefix = '') {
    let count = 0;
    for (const key in obj) {
      if (typeof obj[key] === 'object' && obj[key] !== null) {
        count += countKeys(obj[key], `${prefix}${key}.`);
      } else {
        count++;
      }
    }
    return count;
  }

  const totalKeys = countKeys(messages);
  const missingKeys = getMissingKeys().filter((key) => key.startsWith(`${locale}.`)).length;
  const coverage = totalKeys > 0 ? ((totalKeys - missingKeys) / totalKeys) * 100 : 0;

  return {
    locale,
    totalKeys,
    missingKeys,
    coverage: Math.round(coverage * 100) / 100,
  };
}

/**
 * Render debug overlay
 * @returns {string} - HTML markup
 */
export function renderDebugOverlay() {
  const currentLocale = getLocale();
  const missingKeys = getMissingKeys();

  const localeOptions = supportedLocales
    .map((code) => {
      const meta = localeMetadata[code] || {};
      const stats = getLocaleStats(code);
      const isCurrent = code === currentLocale;
      return {
        code,
        label: meta.displayName || code,
        direction: meta.direction || 'ltr',
        stats,
        isCurrent,
      };
    })
    .sort((a, b) => a.label.localeCompare(b.label));

  const localeList = localeOptions
    .map((locale) => {
      const activeClass = locale.isCurrent ? ' tp-debug-overlay__locale--active' : '';
      return `
        <li class="tp-debug-overlay__locale${activeClass}">
          <button
            type="button"
            class="tp-debug-overlay__locale-button"
            data-action="preview-locale"
            data-locale="${escapeHtml(locale.code)}"
            data-direction="${escapeHtml(locale.direction)}"
          >
            <span class="tp-debug-overlay__locale-name">${escapeHtml(locale.label)}</span>
            <span class="tp-debug-overlay__locale-code">${escapeHtml(locale.code)}</span>
            <span class="tp-debug-overlay__locale-direction">${escapeHtml(locale.direction.toUpperCase())}</span>
          </button>
          <div class="tp-debug-overlay__locale-stats">
            <span>${locale.stats.totalKeys} keys</span>
            ${locale.stats.missingKeys > 0 ? `<span class="tp-debug-overlay__warning">${locale.stats.missingKeys} missing</span>` : ''}
            <span>${locale.stats.coverage}% coverage</span>
          </div>
        </li>
      `;
    })
    .join('');

  const missingKeysList = missingKeys
    .map((key) => {
      return `
        <li class="tp-debug-overlay__missing-key">
          <code>${escapeHtml(key)}</code>
        </li>
      `;
    })
    .join('');

  return `
    <aside
      class="tp-debug-overlay"
      data-role="i18n-debug-overlay"
      hidden
      role="complementary"
      aria-label="Translation debug tools"
    >
      <div class="tp-debug-overlay__panel">
        <div class="tp-debug-overlay__header">
          <h2 class="tp-debug-overlay__title">Translation Debug</h2>
          <button
            type="button"
            class="tp-debug-overlay__close"
            data-action="close-debug-overlay"
            aria-label="Close debug overlay"
          >
            <span aria-hidden="true">&times;</span>
          </button>
        </div>

        <div class="tp-debug-overlay__body">
          <section class="tp-debug-overlay__section">
            <h3 class="tp-debug-overlay__section-title">Locale Preview</h3>
            <ul class="tp-debug-overlay__locales">
              ${localeList}
            </ul>
          </section>

          <section class="tp-debug-overlay__section">
            <h3 class="tp-debug-overlay__section-title">
              Missing Keys
              ${missingKeys.length > 0 ? `<span class="tp-debug-overlay__badge">${missingKeys.length}</span>` : ''}
            </h3>
            ${missingKeys.length > 0 ? `
              <ul class="tp-debug-overlay__missing-keys">
                ${missingKeysList}
              </ul>
              <div class="tp-debug-overlay__actions">
                <button
                  type="button"
                  class="tp-debug-overlay__button"
                  data-action="export-missing-keys"
                >
                  Export Missing Keys
                </button>
                <button
                  type="button"
                  class="tp-debug-overlay__button"
                  data-action="clear-missing-keys"
                >
                  Clear List
                </button>
              </div>
            ` : `
              <p class="tp-debug-overlay__empty">No missing keys detected.</p>
            `}
          </section>

          <section class="tp-debug-overlay__section">
            <h3 class="tp-debug-overlay__section-title">Export Translations</h3>
            <div class="tp-debug-overlay__actions">
              <button
                type="button"
                class="tp-debug-overlay__button"
                data-action="export-translations"
                data-locale="${escapeHtml(currentLocale)}"
              >
                Export Current Locale (${escapeHtml(currentLocale)})
              </button>
            </div>
          </section>

          <section class="tp-debug-overlay__section">
            <h3 class="tp-debug-overlay__section-title">Direction Preview</h3>
            <div class="tp-debug-overlay__toggle">
              <label class="tp-debug-overlay__label">
                <input
                  type="checkbox"
                  data-action="toggle-direction"
                  ${currentLocale === 'ar' || currentLocale === 'he' ? 'checked' : ''}
                />
                <span>Force RTL Layout</span>
              </label>
            </div>
          </section>
        </div>
      </div>
    </aside>
  `;
}

/**
 * Get debug overlay script
 * @returns {string} - Script tag
 */
export function getDebugOverlayScript() {
  return `
    <script>
      (function() {
        if (typeof document === 'undefined') return;

        const overlay = document.querySelector('[data-role="i18n-debug-overlay"]');
        if (!overlay) return;

        const app = document.querySelector('.tp-app');

        function toggleOverlay(show) {
          overlay.hidden = !show;
        }

        function previewLocale(locale, direction) {
          if (!locale) return;

          // Update document direction
          if (app && direction) {
            app.setAttribute('dir', direction);
            app.setAttribute('data-locale', locale);
          }

          // Reload page with new locale
          const url = new URL(window.location.href);
          url.searchParams.set('locale', locale);
          window.location.href = url.toString();
        }

        function toggleDirection(rtl) {
          if (!app) return;
          app.setAttribute('dir', rtl ? 'rtl' : 'ltr');
        }

        function exportMissingKeys() {
          const missingKeys = window.tp && window.tp.missingKeys ? Array.from(window.tp.missingKeys) : [];
          const data = {
            timestamp: new Date().toISOString(),
            keys: missingKeys,
          };
          const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = 'missing-translation-keys.json';
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
        }

        function exportCurrentTranslations(locale) {
          const messages = window.tp && window.tp.messages && window.tp.messages[locale] 
            ? window.tp.messages[locale] 
            : {};
          const blob = new Blob([JSON.stringify(messages, null, 2)], { type: 'application/json' });
          const url = URL.createObjectURL(blob);
          const link = document.createElement('a');
          link.href = url;
          link.download = \`translations-\${locale}.json\`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          URL.revokeObjectURL(url);
        }

        function clearMissingKeys() {
          if (window.tp && window.tp.missingKeys) {
            window.tp.missingKeys.clear();
          }
          // Refresh overlay
          const missingKeysSection = overlay.querySelector('.tp-debug-overlay__missing-keys');
          if (missingKeysSection && missingKeysSection.parentElement) {
            const empty = document.createElement('p');
            empty.className = 'tp-debug-overlay__empty';
            empty.textContent = 'No missing keys detected.';
            missingKeysSection.parentElement.replaceChild(empty, missingKeysSection);
          }
        }

        // Event handlers
        overlay.addEventListener('click', (event) => {
          const target = event.target;

          if (target.matches('[data-action="close-debug-overlay"]') || target.closest('[data-action="close-debug-overlay"]')) {
            toggleOverlay(false);
          }

          if (target.matches('[data-action="preview-locale"]') || target.closest('[data-action="preview-locale"]')) {
            const button = target.closest('[data-action="preview-locale"]');
            const locale = button.getAttribute('data-locale');
            const direction = button.getAttribute('data-direction');
            previewLocale(locale, direction);
          }

          if (target.matches('[data-action="export-missing-keys"]')) {
            exportMissingKeys();
          }

          if (target.matches('[data-action="clear-missing-keys"]')) {
            clearMissingKeys();
          }

          if (target.matches('[data-action="export-translations"]')) {
            const locale = target.getAttribute('data-locale');
            exportCurrentTranslations(locale);
          }
        });

        overlay.addEventListener('change', (event) => {
          const target = event.target;

          if (target.matches('[data-action="toggle-direction"]')) {
            toggleDirection(target.checked);
          }
        });

        // Keyboard shortcut to toggle overlay (Ctrl+Shift+I)
        document.addEventListener('keydown', (event) => {
          if (event.ctrlKey && event.shiftKey && event.key === 'I') {
            event.preventDefault();
            toggleOverlay(overlay.hidden);
          }

          // Escape to close
          if (event.key === 'Escape' && !overlay.hidden) {
            toggleOverlay(false);
          }
        });

        // Add button to toolbar if available
        const toolbar = document.querySelector('[data-role="toolbar"]');
        if (toolbar) {
          const button = document.createElement('button');
          button.type = 'button';
          button.className = 'tp-toolbar__button tp-toolbar__button--debug';
          button.textContent = 'Debug i18n';
          button.setAttribute('aria-label', 'Open translation debug overlay');
          button.addEventListener('click', () => toggleOverlay(true));
          
          const actions = toolbar.querySelector('.tp-toolbar__actions');
          if (actions) {
            actions.appendChild(button);
          }
        }
      })();
    </script>
  `;
}

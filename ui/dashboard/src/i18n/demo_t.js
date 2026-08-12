// ⊛ neuron7xLab · CANON·2026 · i18n runtime for demo.html
// Locale state + translation + Intl formatters + toggle wiring.
// Two locales only: "uk" | "en". Persistence key: neuron7xLab.locale.
// Autodetect: navigator.language.startsWith("uk") → "uk" else "en".
//
// Contract:
//   - t(key) → string for current locale, falls back to key if missing
//   - setLocale(locale) → persists + broadcasts CustomEvent("n7x:locale")
//   - onLocaleChange(cb) → subscribe
//   - format.pnl(n) → "+1,234.56" (en convention in BOTH locales — floor standard)
//   - format.number(n, digits) → locale-aware (uk: "1 234,56" / en: "1,234.56")
//   - format.timeUTC(date) → ISO "YYYY-MM-DD HH:MM:SS UTC" (invariant across locales)
//   - format.dateTime(date) → locale-aware "20 квіт. 2026, 17:17:32 UTC" / "Apr 20, 2026…"

import { strings } from "./demo_strings.js";

/** @typedef {"uk" | "en"} Locale */
/** @type {readonly Locale[]} */
export const LOCALES = Object.freeze(["uk", "en"]);
const STORAGE_KEY = "neuron7xLab.locale";

/** @type {Locale} */
let _locale = _initialLocale();
const _listeners = new Set();

function _initialLocale() {
  try {
    const stored = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (stored === "uk" || stored === "en") return stored;
  } catch {
    /* ignore — private-mode storage denial */
  }
  const navLang = (globalThis.navigator?.language || "en").toLowerCase();
  return navLang.startsWith("uk") ? "uk" : "en";
}

/** Current locale. */
export function getLocale() {
  return _locale;
}

/**
 * Set locale + persist + broadcast. Silently ignores invalid input.
 * @param {Locale} next
 */
export function setLocale(next) {
  if (next !== "uk" && next !== "en") return;
  if (next === _locale) return;
  _locale = next;
  try {
    globalThis.localStorage?.setItem(STORAGE_KEY, next);
  } catch {
    /* ignore */
  }
  _emit();
}

/** Toggle between uk ↔ en. */
export function toggleLocale() {
  setLocale(_locale === "uk" ? "en" : "uk");
}

/**
 * Subscribe to locale changes. Returns an unsubscribe function.
 * @param {(locale: Locale) => void} cb
 */
export function onLocaleChange(cb) {
  _listeners.add(cb);
  return () => _listeners.delete(cb);
}

function _emit() {
  for (const cb of _listeners) {
    try {
      cb(_locale);
    } catch (err) {
      if (console?.debug) console.debug("[i18n] listener failed", err);
    }
  }
  try {
    globalThis.dispatchEvent?.(
      new CustomEvent("n7x:locale", { detail: { locale: _locale } }),
    );
  } catch {
    /* ignore — node/test context */
  }
}

/**
 * Lookup translation by dotted key, e.g. t("dro.title").
 * Variable interpolation via {name}: t("invariants.flagged", {count: 3}).
 * Falls back to the raw key on miss (never throws).
 * @param {string} key
 * @param {Record<string, string|number>} [params]
 */
export function t(key, params) {
  const [ns, leaf, ...rest] = String(key || "").split(".");
  if (rest.length) {
    // Allow 3-level lookup for enum tables: t("droState.CRITICAL") already works
    // with 2-level; deeper paths are unsupported by design.
    return key;
  }
  const pair = strings?.[ns]?.[leaf];
  if (!pair) return key;
  const raw = pair[_locale] ?? pair.en ?? key;
  return params ? _interpolate(raw, params) : raw;
}

function _interpolate(template, params) {
  return String(template).replace(/\{(\w+)\}/g, (_, name) =>
    params[name] == null ? "" : String(params[name]),
  );
}

// -------------------------- Formatters (T5) --------------------------

const _numberFormatters = new Map();
function _numFmt(locale, opts) {
  const key = locale + "|" + JSON.stringify(opts);
  let f = _numberFormatters.get(key);
  if (!f) {
    // Map "uk" → "uk-UA", "en" → "en-US" for Intl.
    const intlLocale = locale === "uk" ? "uk-UA" : "en-US";
    f = new Intl.NumberFormat(intlLocale, opts);
    _numberFormatters.set(key, f);
  }
  return f;
}

/** Locale-aware number (Intl). */
function formatNumber(n, { digits = 2, signed = false } = {}) {
  if (n == null || !Number.isFinite(n)) return "—";
  const s = _numFmt(_locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    useGrouping: true,
  }).format(n);
  return signed && n > 0 ? `+${s}` : s;
}

/** Percent (always "+12.34%" form; follows locale decimal). */
function formatPercent(n, digits = 2) {
  if (n == null || !Number.isFinite(n)) return "—";
  const s = _numFmt(_locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    useGrouping: true,
  }).format(n);
  return n >= 0 ? `+${s}%` : `${s}%`;
}

/**
 * PnL: trading-floor convention (en "1,234.56") in BOTH locales. This is a
 * conscious carve-out — see docs/tasks/I18N_TASK.md §T5.
 */
function formatPnl(n, { digits = 2, signed = true } = {}) {
  if (n == null || !Number.isFinite(n)) return "—";
  const s = _numFmt("en", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    useGrouping: true,
  }).format(n);
  return signed && n > 0 ? `+${s}` : s;
}

/** ISO 8601 UTC — invariant across locales (UTC suffix stays literal). */
function formatTimeUTC(date) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (v, w = 2) => String(v).padStart(w, "0");
  return (
    `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())} ` +
    `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())} UTC`
  );
}

/** Locale-aware date+time. UTC suffix preserved. */
function formatDateTime(date) {
  const d = date instanceof Date ? date : new Date(date);
  if (Number.isNaN(d.getTime())) return "—";
  const intlLocale = _locale === "uk" ? "uk-UA" : "en-US";
  const opts = {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  };
  const body = new Intl.DateTimeFormat(intlLocale, opts).format(d);
  return `${body} UTC`;
}

export const format = Object.freeze({
  number: formatNumber,
  percent: formatPercent,
  pnl: formatPnl,
  timeUTC: formatTimeUTC,
  dateTime: formatDateTime,
});

// -------------------------- Toggle mounting (T3) --------------------------

/**
 * Mount the UA · EN pill toggle into a container element.
 * Re-renders itself on every locale change (subscribed).
 * Returns a disposer that removes listeners.
 *
 * @param {HTMLElement} host
 */
export function mountLocaleToggle(host) {
  if (!host) return () => undefined;
  host.classList.add("n7x-locale-toggle");
  host.setAttribute("role", "group");
  host.setAttribute("aria-label", t("localeToggle.ariaLabel"));
  host.innerHTML = "";

  /** @type {Record<Locale, HTMLButtonElement>} */
  const buttons = /** @type {any} */ ({});
  for (const loc of LOCALES) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.locale = loc;
    b.textContent = loc === "uk" ? "UA" : "EN";
    b.addEventListener("click", () => setLocale(loc));
    host.appendChild(b);
    buttons[loc] = b;
  }

  const render = () => {
    host.setAttribute("aria-label", t("localeToggle.ariaLabel"));
    for (const loc of LOCALES) {
      const active = loc === _locale;
      buttons[loc].setAttribute("aria-pressed", String(active));
      buttons[loc].classList.toggle("is-active", active);
    }
  };
  render();
  const dispose = onLocaleChange(render);
  return dispose;
}

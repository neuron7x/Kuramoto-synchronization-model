// ⊛ neuron7xLab · CANON·2026 · i18n v1.0
// Single source of truth for every user-facing string in demo.html.
// Two locales: uk | en. Canon glyphs / system identifiers / market
// conventions never translated — they appear identically in both locales.
// Anything visible to the operator MUST live here; any literal remaining in
// demo.html after wiring is a contract violation.
//
// Shape:
//   strings[namespace][key] = { uk: "…", en: "…" }
//
// Locale resolution: see ./demo_t.js.

/** @type {Readonly<Record<string, Record<string, {uk: string, en: string}>>>} */
export const strings = Object.freeze({
  // ---------------- brand / identity (canon) ----------------
  brand: {
    label: { uk: "neuron7xLab", en: "neuron7xLab" },
    sublabel: { uk: "GeoSync", en: "GeoSync" },
  },

  // ---------------- navigation ----------------
  navGroup: {
    execution: { uk: "Виконання", en: "Execution" },
    regime:    { uk: "Режим",     en: "Regime"    },
    research:  { uk: "Дослідження", en: "Research" },
  },
  nav: {
    overview:    { uk: "Огляд",        en: "Overview"     },
    livePnl:     { uk: "Поточний PnL", en: "Live PnL"     },
    positions:   { uk: "Позиції",      en: "Positions"    },
    signals:     { uk: "Сигнали",      en: "Signals"      },
    orders:      { uk: "Ордери",       en: "Orders"       },
    droAra:      { uk: "DRO-ARA",      en: "DRO-ARA"      },
    crisisAlpha: { uk: "Crisis-alpha", en: "Crisis-alpha" },
    monitoring:  { uk: "Моніторинг",   en: "Monitoring"   },
    invariants:  { uk: "Інваріанти",   en: "Invariants"   },
    notebooks:   { uk: "Зошити",       en: "Notebooks"    },
  },

  // ---------------- header / topbar ----------------
  topbar: {
    overviewWord:  { uk: "Огляд",       en: "Overview"   },
    live:          { uk: "поточний",    en: "live"       },
    tick:          { uk: "тік",         en: "tick"       },
    slip:          { uk: "прослизання", en: "slip"       },
    search:        { uk: "пошук",       en: "search"     },
    menuToggle:    { uk: "≡ меню",      en: "≡ menu"     },
  },

  // ---------------- γ indicator ----------------
  gamma: {
    stable: { uk: "стабільний", en: "stable" },
    drift:  { uk: "дрейф",      en: "drift"  },
    broken: { uk: "розрив",     en: "broken" },
  },

  // ---------------- primary metrics row ----------------
  metrics: {
    sharpeTitle:   { uk: "ШАРП · in-sample",   en: "SHARPE · in-sample" },
    icTitle:       { uk: "IC · ранг",          en: "IC · rank"          },
    alphaTitle:    { uk: "альфа · річна",      en: "alpha · ann."       },
    maxDdTitle:    { uk: "Макс. DD",           en: "Max DD"             },
    sharpeSub:     { uk: "ціль ≥ 1.50 · очікування двигуна", en: "target ≥ 1.50 · awaiting engine" },
    icSub:         { uk: "поріг ≥ 0.08 · очікування двигуна", en: "gate ≥ 0.08 · awaiting engine" },
    alphaSub:      { uk: "vs BTC · очікування двигуна",       en: "vs BTC · awaiting engine"        },
    ddSub:         { uk: "crisis-alpha 2022 · +47.6%", en: "crisis-alpha 2022 · +47.6%" },
  },

  // ---------------- live PnL card ----------------
  pnl: {
    title:        { uk: "Поточний PnL · крива капіталу", en: "Live PnL · equity curve" },
    range1d:      { uk: "1д",  en: "1d"  },
    range1w:      { uk: "1т",  en: "1w"  },
    range30d:     { uk: "30д", en: "30d" },
    rangeYtd:     { uk: "YTD", en: "YTD" },
    age:          { uk: "вік", en: "age" },
    sinceOpen:    { uk: "Δ з відкриття",     en: "Δ since open" },
    runRate:      { uk: "темп",              en: "run-rate"     },
    unrealisedPill: { uk: "нереалізований",  en: "unrealised"   },
    realised:     { uk: "реалізований",      en: "realised"     },
    unrealised:   { uk: "нереалізований",    en: "unrealised"   },
    fees:         { uk: "комісії",           en: "fees"         },
    turnover:     { uk: "оборот",            en: "turnover"     },
    crisisRefLabel: { uk: "crisis-alpha 2022 · +47.6%", en: "crisis-alpha 2022 · +47.6%" },
  },

  // ---------------- DRO-ARA regime gate ----------------
  dro: {
    title:        { uk: "DRO-ARA · режимні ворота", en: "DRO-ARA · regime gate" },
    deltaWindow:  { uk: "Δвікно 2048", en: "Δwindow 2048" },
    state:        { uk: "стан",        en: "state" },
    trend:        { uk: "тренд",       en: "trend" },
    rule1:        { uk: "γ = 2H + 1 · INV-DRO1",      en: "γ = 2H + 1 · INV-DRO1" },
    rule2:        { uk: "r_s ∈ [0, 1] · INV-DRO2",    en: "r_s ∈ [0, 1] · INV-DRO2" },
    ruleStationary:{ uk: "стаціонарний · ADF",         en: "stationary · ADF" },
    ok:           { uk: "ok",    en: "ok" },
    fail:         { uk: "FAIL",  en: "FAIL" },
    noStationary: { uk: "НІ",    en: "NO" },
    footerLeft:   { uk: "Ворота LONG вимагають", en: "LONG gate requires" },
    footerRule:   {
      uk: "CRITICAL ∧ r_s>0.33 ∧ тренд∈{CONVERGING, STABLE}",
      en: "CRITICAL ∧ r_s>0.33 ∧ trend∈{CONVERGING, STABLE}",
    },
    signalLabel:  { uk: "Сигнал:", en: "Signal:" },
    eligible:     { uk: "допустимий", en: "eligible" },
  },
  // DRO-ARA regime state enum labels (API sends raw enum string)
  droState: {
    CRITICAL:   { uk: "КРИТИЧНИЙ",    en: "CRITICAL"   },
    TRANSITION: { uk: "ПЕРЕХІД",      en: "TRANSITION" },
    DRIFT:      { uk: "ДРЕЙФ",        en: "DRIFT"      },
    INVALID:    { uk: "ІНВАЛІДНИЙ",   en: "INVALID"    },
    STABLE:     { uk: "СТАБІЛЬНИЙ",   en: "STABLE"     },
    CONVERGING: { uk: "КОНВЕРГЕНЦІЯ", en: "CONVERGING" },
    DIVERGING:  { uk: "ДИВЕРГЕНЦІЯ",  en: "DIVERGING"  },
    METASTABLE: { uk: "МЕТАСТАБІЛЬНИЙ", en: "METASTABLE" },
    DRIFTING:   { uk: "ДРЕЙФУЄ",      en: "DRIFTING"   },
    COLLAPSING: { uk: "КОЛАПС",       en: "COLLAPSING" },
    DEGENERATE: { uk: "ВИРОДЖЕНИЙ",   en: "DEGENERATE" },
  },
  // DRO-ARA signal enum labels
  droSignal: {
    LONG:   { uk: "LONG",   en: "LONG"   },
    SHORT:  { uk: "SHORT",  en: "SHORT"  },
    HOLD:   { uk: "HOLD",   en: "HOLD"   },
    REDUCE: { uk: "REDUCE", en: "REDUCE" },
  },

  // ---------------- combo_v1 signal stream ----------------
  signal: {
    title:    { uk: "combo_v1 · потік сигналів", en: "combo_v1 · signal stream" },
    icPill:   { uk: "IC 0.124", en: "IC 0.124" },
    age:      { uk: "вік", en: "age" },
    colTime:  { uk: "час · UTC", en: "time · UTC" },
    colSymbol:{ uk: "інструмент", en: "symbol" },
    colSide:  { uk: "напрям",     en: "side"   },
    colStrength: { uk: "сила", en: "strength" },
    colTtl:   { uk: "TTL", en: "TTL" },
    colStatus:{ uk: "стан", en: "status" },
    buy:      { uk: "BUY",  en: "BUY"  },
    sell:     { uk: "SELL", en: "SELL" },
    flat:     { uk: "FLAT", en: "FLAT" },
    active:   { uk: "активний",      en: "active"  },
    expired:  { uk: "прострочений",  en: "expired" },
  },

  // ---------------- positions ----------------
  positions: {
    title:    { uk: "позиції · відкриті", en: "positions · open" },
    rows:     { uk: "6 рядків", en: "6 rows" },
    colSymbol:{ uk: "інструмент", en: "symbol" },
    colQty:   { uk: "кіл-ть", en: "qty"   },
    colAvg:   { uk: "сер.",   en: "avg"   },
    colMark:  { uk: "ринк.",  en: "mark"  },
    colUpnl:  { uk: "uPnL",   en: "uPnL"  },
    colAge:   { uk: "вік",    en: "age"   },
    netExposure: { uk: "чиста експозиція", en: "net exposure" },
    gross:    { uk: "валова", en: "gross"  },
  },

  // ---------------- bottom quadlet ----------------
  execution: {
    title:   { uk: "виконання", en: "execution" },
    fills1h: { uk: "заявки · 1г", en: "fills · 1h" },
    reject:  { uk: "відхилено",   en: "reject"    },
    slipP50: { uk: "прослизання p50", en: "slip p50" },
    slipP95: { uk: "прослизання p95", en: "slip p95" },
  },
  kelly: {
    title:   { uk: "ризик · Kelly", en: "risk · Kelly" },
    fStar:   { uk: "f*",        en: "f*"       },
    applied: { uk: "застосовано", en: "applied" },
    cap:     { uk: "ліміт",     en: "cap"      },
    sign:    { uk: "знак",      en: "sign"     },
    long:    { uk: "лонг",      en: "long"     },
    short:   { uk: "шорт",      en: "short"    },
    flat:    { uk: "нейтраль",  en: "flat"     },
  },
  kuramoto: {
    title: { uk: "фаза · Kuramoto", en: "phase · Kuramoto" },
    rT:    { uk: "R(t)",   en: "R(t)" },
    kKc:   { uk: "K/K_c",  en: "K/K_c" },
    n:     { uk: "N",      en: "N"     },
    gate:  { uk: "ворота", en: "gate"  },
    open:  { uk: "відкриті",  en: "open"   },
    closed:{ uk: "закриті",   en: "closed" },
  },
  invariants: {
    title:    { uk: "інваріанти · спостереження", en: "invariants · watch" },
    allOk:    { uk: "всі ok", en: "all ok" },
    flagged:  { uk: "позначено {count}", en: "{count} flagged" },
    waiting:  { uk: "очікування двигуна", en: "awaiting engine" },
    tagOk:    { uk: "OK",   en: "OK"   },
    tagFlag:  { uk: "ФЛАГ", en: "FLAG" },
    tagOff:   { uk: "OFF",  en: "OFF"  },
    offlineMessage: { uk: "двигун офлайн — немає даних", en: "engine offline — no data" },
  },

  // ---------------- command palette ----------------
  palette: {
    placeholder: {
      uk: "перехід · команда · пошук · інваріант…",
      en: "jump to view · run command · search symbols…",
    },
    catNav:       { uk: "навіг.",  en: "nav"       },
    catAction:    { uk: "дія",     en: "action"    },
    catSymbol:    { uk: "інструм.",en: "symbol"    },
    catInvariant: { uk: "інваріант", en: "invariant" },
    actionRefresh:{ uk: "Оновити канал", en: "Refresh feed" },
    actionExport: { uk: "Експорт звіту", en: "Export report" },
    actionCopy:   { uk: "Скопіювати хеш стану", en: "Copy state hash" },
    empty:        { uk: "немає збігів", en: "no match" },
  },

  // ---------------- footer ----------------
  footer: {
    versionLine:  { uk: "neuron7xLab · CANON·2026 · Протокол публікації v1.0", en: "neuron7xLab · CANON·2026 · Publication Protocol v1.0" },
    build:        { uk: "збірка", en: "build" },
    kbdSearch:    { uk: "пошук",  en: "search"  },
    kbdHelp:      { uk: "допомога", en: "help"  },
    kbdRefresh:   { uk: "оновити", en: "refresh" },
    engineLive:   { uk: "двигун: живий",  en: "engine: live"    },
    engineOffline:{ uk: "двигун: офлайн", en: "engine: offline" },
    engineAwait:  { uk: "двигун: …",      en: "engine: …"       },
  },

  // ---------------- locale toggle ----------------
  localeToggle: {
    uk: { uk: "UA", en: "UA" },
    en: { uk: "EN", en: "EN" },
    ariaLabel: { uk: "Перемкнути мову", en: "Toggle language" },
  },
});

/** Flat list of canon tokens that MUST appear identically in uk and en. */
export const canonTokens = Object.freeze([
  // Brand glyph + identity
  "⊛", "neuron7xLab", "GeoSync", "NeoSynaptex", "neurophase", "BN-Syn",
  "CNS-AI", "NFI", "MFN+",
  // System identifiers
  "DRO-ARA", "combo_v1", "Kelly", "Kuramoto",
  // Invariant codes
  "INV-DRO1", "INV-DRO2", "INV-K1", "INV-K3", "INV-KELLY2", "CANON·2026",
  // Math symbols
  "γ", "H", "r_s", "R²", "Δ", "α", "β", "σ", "π", "∈", "∧", "∨", "∀", "∃",
  // Market conventions
  "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "LINKUSDT", "ARBUSDT",
  "BTC", "ETH", "SOL", "BNB",
  "BUY", "SELL", "FLAT", "LONG", "SHORT",
  "PnL", "uPnL", "YTD", "DD", "IC", "TTL", "ADF", "bp",
  // Units + physics-notation composites
  "ms", "UTC", "USD", "USDT", "USD/h", "K/K_c", "f*",
  // Formal ok
  "ok",
]);

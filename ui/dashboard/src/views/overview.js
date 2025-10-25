import { escapeHtml, formatNumber, formatPercent, formatTimestamp } from '../core/formatters.js';
import { t, getMessage } from '../i18n/index.js';
import { localeMetadata, supportedLocales } from '../i18n/config.js';

function coerceNumber(value, fallback = 0) {
  if (Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return fallback;
}

function clamp01(value) {
  const numeric = coerceNumber(value, 0);
  if (!Number.isFinite(numeric)) {
    return 0;
  }
  return Math.min(1, Math.max(0, numeric));
}

function safeExternalUrl(url) {
  const raw = typeof url === 'string' ? url.trim() : '';
  if (raw.startsWith('https://') || raw.startsWith('http://')) {
    return raw;
  }
  return '#';
}

function asArray(value) {
  if (Array.isArray(value)) {
    return value;
  }
  if (value && typeof value === 'object') {
    return Object.values(value);
  }
  return [];
}

function normaliseFeatureItems(primary, fallback) {
  const source = asArray(primary);
  const items = source
    .map((entry) => {
      if (entry && typeof entry === 'object') {
        const title = entry.title || entry.label || null;
        if (!title) {
          return null;
        }
        return {
          title,
          description: entry.description || entry.body || entry.text || '',
        };
      }
      if (entry == null) {
        return null;
      }
      const title = String(entry);
      return title ? { title, description: '' } : null;
    })
    .filter(Boolean);
  if (items.length > 0) {
    return items;
  }
  if (fallback && fallback !== primary) {
    return normaliseFeatureItems(fallback, null);
  }
  return [];
}

function normalisePlatformItems(primary, fallback) {
  const source = asArray(primary);
  const items = source
    .map((entry) => {
      if (!entry) {
        return null;
      }
      if (typeof entry === 'object') {
        const label = entry.label || entry.title || entry.name;
        if (!label) {
          return null;
        }
        return {
          label,
          badge: entry.badge || entry.cta || entry.action || label,
          href: safeExternalUrl(entry.href || entry.url),
          description: entry.description || entry.note || '',
        };
      }
      const label = String(entry);
      return label ? { label, badge: label, href: '#', description: '' } : null;
    })
    .filter(Boolean);
  if (items.length > 0) {
    return items;
  }
  if (fallback && fallback !== primary) {
    return normalisePlatformItems(fallback, null);
  }
  return [];
}

function normaliseMetricItems(primary, fallback) {
  const source = asArray(primary);
  const items = source
    .map((entry) => {
      if (!entry) {
        return null;
      }
      if (typeof entry === 'object') {
        const label = entry.label || entry.title || null;
        const value = entry.value || entry.metric || entry.summary || null;
        if (!label || !value) {
          return null;
        }
        return {
          label,
          value,
          hint: entry.hint || entry.detail || '',
        };
      }
      return null;
    })
    .filter(Boolean);
  if (items.length > 0) {
    return items;
  }
  if (fallback && fallback !== primary) {
    return normaliseMetricItems(fallback, null);
  }
  return [];
}

function normaliseStringList(primary, fallback) {
  const source = asArray(primary)
    .map((entry) => {
      if (entry == null) {
        return null;
      }
      if (typeof entry === 'object') {
        return entry.text || entry.label || entry.title || null;
      }
      return String(entry);
    })
    .filter((entry) => typeof entry === 'string' && entry.trim().length > 0);
  if (source.length > 0) {
    return source;
  }
  if (fallback && fallback !== primary) {
    return normaliseStringList(fallback, null);
  }
  return [];
}

const DEFAULT_MOBILE_FEATURES = [
  {
    title: 'Biometric-grade access',
    description: 'Face ID, Touch ID, and hardware key support with audited unlock trails.',
  },
  {
    title: 'Incident-grade alerts',
    description: 'Push notifications with <120 ms SLA and acknowledgement workflows.',
  },
  {
    title: 'Offline continuity',
    description: 'Cache dashboards for 24 hours to stay operational without connectivity.',
  },
];

const DEFAULT_MOBILE_PLATFORMS = [
  {
    label: 'iOS',
    badge: 'TestFlight beta',
    href: 'https://github.com/tradepulse/TradePulse/wiki/Mobile-iOS',
  },
  {
    label: 'Android',
    badge: 'Play Store internal',
    href: 'https://github.com/tradepulse/TradePulse/wiki/Mobile-Android',
  },
  {
    label: 'PWA',
    badge: 'Install web app',
    href: 'https://tradepulse.io/mobile',
  },
];

const DEFAULT_MOBILE_METRICS = [
  {
    label: 'Release cadence',
    value: 'Weekly builds',
    hint: 'Signed distributions every Friday 17:00 UTC',
  },
  {
    label: 'Alert SLA',
    value: '<120 ms',
    hint: 'Edge fan-out via seven global PoPs',
  },
  {
    label: 'Session hardening',
    value: 'Zero-trust',
    hint: 'Device attestation & MDM compliance enforced',
  },
];

const PRIORITY_ORDER = {
  'tier-0': 0,
  'tier-1': 1,
  'tier-2': 2,
};

const DEFAULT_LOCALISATION_PRIORITY_LABELS = {
  'tier-0': 'Tier 0 · Primary',
  'tier-1': 'Tier 1 · Strategic',
  'tier-2': 'Tier 2 · Emerging',
};

const DEFAULT_LOCALISATION_HIGHLIGHTS = [
  'Every locale reviewed by native financial linguists.',
  'Regulatory tone guidance packaged per region.',
];

const DEFAULT_COMMUNITY_ACTIONS = [
  {
    title: 'Maintainer office hours',
    description: 'Weekly pairing sessions covering code walkthroughs and roadmap context.',
  },
  {
    title: 'Mentored issues',
    description: 'Curated backlog tagged good-first-issue with async reviewer support.',
  },
  {
    title: 'Contributor guild',
    description: 'Monthly forums featuring architecture updates and feedback loops.',
  },
];

const DEFAULT_COMMUNITY_METRICS = [
  {
    label: 'Mentors on rotation',
    value: '6',
    hint: 'Dedicated maintainers covering UTC, EST, and JST time zones',
  },
  {
    label: 'Avg. review turnaround',
    value: '18h',
    hint: 'Median across last 30 community pull requests',
  },
];

const DEFAULT_COMMUNITY_HIGHLIGHTS = [
  'Open governance with quarterly roadmap votes.',
  'Security reviews offered for first-time contributors.',
];

const DEFAULT_COMMUNITY_CTA = {
  label: 'Open contribution playbook',
  href: 'https://github.com/tradepulse/TradePulse/blob/main/CONTRIBUTING.md',
};

function renderMetaList(items = []) {
  if (!items.length) {
    return '';
  }
  const markup = items
    .map((item) => {
      const hint = item.hint ? `<span class="tp-text-subtle">${escapeHtml(String(item.hint))}</span>` : '';
      return `
        <span class="tp-meta-list__item">
          <span class="tp-meta-list__key">${escapeHtml(String(item.label))}</span>
          <span>${escapeHtml(String(item.value))}</span>
          ${hint}
        </span>
      `;
    })
    .join('');
  return `<div class="tp-meta-list">${markup}</div>`;
}

function renderFeatureList(items = []) {
  if (!items.length) {
    return '';
  }
  return `
    <ul class="tp-feature-list">
      ${items
        .map(
          (item) => `
            <li class="tp-feature-item">
              <h4 class="tp-feature-item__title">${escapeHtml(String(item.title))}</h4>
              ${item.description ? `<p class="tp-feature-item__body">${escapeHtml(String(item.description))}</p>` : ''}
            </li>
          `,
        )
        .join('')}
    </ul>
  `;
}

function getTranslations() {
  const view = getMessage('views.overview') || {};
  return {
    title: view.title || 'Overview',
    heading: view.heading || 'Product Pulse',
    subtitle: view.subtitle || '',
    hero: view.hero || {},
    badges: view.badges || {},
    panels: view.panels || {},
    mobile: view.mobile || {},
    localization: view.localization || {},
    community: view.community || {},
  };
}

function renderHero(heroTranslations = {}, github = {}) {
  const eyebrow = heroTranslations.eyebrow || t('views.overview.hero.eyebrow');
  const title = heroTranslations.title || t('views.overview.hero.title');
  const subtitle = heroTranslations.subtitle || t('views.overview.hero.subtitle');
  const cta = heroTranslations.cta || t('views.overview.hero.cta');
  const repo = github.repository || github.repo || 'tradepulse/TradePulse';
  const org = github.organization || github.owner || 'TradePulse';
  const url = safeExternalUrl(github.url || github.html_url);

  const repoLabel = `${org}/${repo}`.replace(/^\/+|\/+$/g, '');

  const action = url === '#'
    ? ''
    : `
        <a class="tp-hero__action" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
          <svg class="tp-hero__action-icon" viewBox="0 0 16 16" aria-hidden="true" focusable="false">
            <path
              d="M8 .198a7.8 7.8 0 0 0-2.469 15.207c.39.072.53-.17.53-.376 0-.186-.007-.68-.01-1.334-2.159.469-2.614-1.04-2.614-1.04-.355-.904-.868-1.145-.868-1.145-.71-.486.054-.476.054-.476.785.055 1.199.806 1.199.806.698 1.196 1.833.851 2.279.651.071-.517.274-.851.498-1.047-1.724-.197-3.534-.862-3.534-3.838 0-.848.303-1.541.802-2.085-.08-.197-.348-.99.076-2.064 0 0 .652-.21 2.136.796a7.39 7.39 0 0 1 1.944-.262 7.39 7.39 0 0 1 1.944.262c1.484-1.006 2.135-.796 2.135-.796.425 1.073.157 1.866.078 2.064.5.544.801 1.237.801 2.085 0 2.983-1.813 3.638-3.543 3.831.281.24.532.71.532 1.43 0 1.033-.01 1.866-.01 2.12 0 .208.138.452.535.375A7.8 7.8 0 0 0 8 .198"
              fill="currentColor"
            />
          </svg>
          <span class="tp-hero__action-label">${escapeHtml(cta || 'Open GitHub Repo')}</span>
        </a>
      `;

  return `
    <section class="tp-hero" data-role="overview-hero">
      <div class="tp-hero__content">
        <p class="tp-hero__eyebrow">${escapeHtml(String(eyebrow || repoLabel))}</p>
        <h2 class="tp-hero__title">${escapeHtml(String(title || 'TradePulse Product Pulse'))}</h2>
        <p class="tp-hero__subtitle">${escapeHtml(String(subtitle || 'Visualise adoption, cadence, and quality signals sourced from GitHub.'))}</p>
        <div class="tp-hero__meta">
          <span class="tp-hero__repo">${escapeHtml(repoLabel)}</span>
          ${action}
        </div>
      </div>
      <div class="tp-hero__visual" aria-hidden="true">
        <div class="tp-hero__orb tp-hero__orb--primary"></div>
        <div class="tp-hero__orb tp-hero__orb--secondary"></div>
        <div class="tp-hero__grid"></div>
      </div>
    </section>
  `;
}

function formatDelta(value) {
  if (!Number.isFinite(value) || value === 0) {
    return '0%';
  }
  const percent = formatPercent(value, { maximumFractionDigits: 1 });
  return value > 0 ? `+${percent}` : percent;
}

function renderBadge({ icon, label, value, hint }) {
  return `
    <div class="tp-github-badge">
      <div class="tp-github-badge__icon">${icon}</div>
      <div class="tp-github-badge__content">
        <dt class="tp-github-badge__label">${escapeHtml(String(label))}</dt>
        <dd class="tp-github-badge__value">${escapeHtml(String(value))}</dd>
        ${hint ? `<p class="tp-github-badge__hint">${escapeHtml(String(hint))}</p>` : ''}
      </div>
    </div>
  `;
}

function renderBadges(github = {}, translations = {}) {
  const badgesT = translations || {};
  const stats = [
    {
      key: 'stars',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2.5l2.47 6.47 6.78.22-5.3 4.23 1.74 6.58L12 16.91l-5.69 3.09 1.74-6.58-5.3-4.23 6.78-.22z" fill="currentColor"/></svg>',
      value: formatNumber(coerceNumber(github.stars, 0)),
      hint: badgesT.stars?.hint
        ? badgesT.stars.hint.replace('{delta}', formatDelta(coerceNumber(github.stars_delta)))
        : null,
      label: badgesT.stars?.label || 'Stars',
    },
    {
      key: 'forks',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 4a3 3 0 1 1-2.995 3.176A3.001 3.001 0 0 1 7 4Zm10 0a3 3 0 1 1-2.995 3.176A3.001 3.001 0 0 1 17 4Zm0 9a3 3 0 1 1-2.995 3.176A3.001 3.001 0 0 1 17 13Zm-5-7v6.268a3.5 3.5 0 0 1 2 3.122V19a1 1 0 1 1-2 0v-3.61a1.5 1.5 0 0 0-3 0V19a1 1 0 1 1-2 0v-3.61a3.5 3.5 0 0 1 2-3.122V6a1 1 0 1 1 2 0Z" fill="currentColor"/></svg>',
      value: formatNumber(coerceNumber(github.forks, 0)),
      hint: badgesT.forks?.hint
        ? badgesT.forks.hint.replace('{count}', formatNumber(coerceNumber(github.active_forks)))
        : null,
      label: badgesT.forks?.label || 'Forks',
    },
    {
      key: 'watchers',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5c5.177 0 9.62 3.295 11 7-1.38 3.705-5.823 7-11 7S2.38 15.705 1 12c1.38-3.705 5.823-7 11-7Zm0 3.5a3.5 3.5 0 1 0 0 7 3.5 3.5 0 0 0 0-7Zm0 2a1.5 1.5 0 1 1 0 3 1.5 1.5 0 0 1 0-3Z" fill="currentColor"/></svg>',
      value: formatNumber(coerceNumber(github.watchers, 0)),
      hint: badgesT.watchers?.hint
        ? badgesT.watchers.hint.replace('{percent}', formatPercent(clamp01(github.watchers_growth || 0)))
        : null,
      label: badgesT.watchers?.label || 'Watchers',
    },
    {
      key: 'contributors',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.5 6.5a4 4 0 1 1 8 0 4 4 0 0 1-8 0Zm-3 11.25c0-2.21 2.91-4 6.5-4s6.5 1.79 6.5 4V20H4.5v-2.25Zm12.75-8.75a2.75 2.75 0 1 1 5.5 0 2.75 2.75 0 0 1-5.5 0Zm-1.25 8.75c0-.553.124-1.082.35-1.564 1.107-.69 2.556-1.186 4.15-1.347A4.5 4.5 0 0 1 22.5 20v1.5H15v-2.25Z" fill="currentColor"/></svg>',
      value: formatNumber(coerceNumber(github.contributors, 0)),
      hint: badgesT.contributors?.hint
        ? badgesT.contributors.hint.replace('{new}', formatNumber(coerceNumber(github.new_contributors_30d)))
        : null,
      label: badgesT.contributors?.label || 'Contributors',
    },
  ];

  return `
    <dl class="tp-github-badges">
      ${stats
        .filter((item) => Number.isFinite(coerceNumber(github[item.key], 0)) || item.key === 'contributors')
        .map((item) => renderBadge(item))
        .join('')}
    </dl>
  `;
}

function renderReleasePanel(github = {}, translations = {}) {
  const release = github.last_release || github.release || {};
  const panelsT = translations || {};
  const title = panelsT.release?.title || 'Release cadence';
  const subtitle = panelsT.release?.subtitle || 'Latest tagged milestone and merge velocity.';
  const tag = release.tag || release.name || 'v0.0.0';
  const published = release.published_at || release.date || null;
  const publishedDisplay = published ? formatTimestamp(new Date(published).getTime()) : '—';
  const commits = coerceNumber(github.commits_30d, 0);
  const merges = coerceNumber(github.prs?.merged_30d, github.merged_prs_30d);
  const openPRs = coerceNumber(github.prs?.open, github.open_prs);
  const changeRequest = panelsT.release?.metrics || {};

  return `
    <section class="tp-card tp-github-panel">
      <header class="tp-card__header">
        <h3 class="tp-card__title">${escapeHtml(String(title))}</h3>
        <p class="tp-text-subtle">${escapeHtml(String(subtitle))}</p>
      </header>
      <div class="tp-github-release">
        <div class="tp-github-release__tag">
          <span class="tp-pill">${escapeHtml(String(tag))}</span>
          <span class="tp-text-muted">${escapeHtml(panelsT.release?.published || 'Published')}</span>
          <strong>${escapeHtml(String(publishedDisplay))}</strong>
        </div>
        <dl class="tp-github-release__metrics">
          <div>
            <dt>${escapeHtml(String(changeRequest?.commits || 'Commits (30d)'))}</dt>
            <dd>${escapeHtml(formatNumber(commits))}</dd>
          </div>
          <div>
            <dt>${escapeHtml(String(changeRequest?.merged || 'Merged PRs (30d)'))}</dt>
            <dd>${escapeHtml(formatNumber(merges))}</dd>
          </div>
          <div>
            <dt>${escapeHtml(String(changeRequest?.open || 'Open PRs'))}</dt>
            <dd>${escapeHtml(formatNumber(openPRs))}</dd>
          </div>
        </dl>
      </div>
    </section>
  `;
}

function renderLanguageBar(language) {
  const name = language?.name || 'Unknown';
  const share = clamp01(language?.share ?? language?.percent ?? language?.percentage ?? 0);
  const percentLabel = formatPercent(share, { maximumFractionDigits: 1 });
  return `
    <li class="tp-github-language">
      <div class="tp-github-language__label">
        <span class="tp-github-language__swatch" style="--tp-language-color: ${escapeHtml(language?.color || '#38bdf8')};"></span>
        <span>${escapeHtml(String(name))}</span>
      </div>
      <div class="tp-progress tp-progress--slim" role="presentation">
        <div class="tp-progress__bar" style="transform: scaleX(${share});"></div>
      </div>
      <span class="tp-github-language__value">${escapeHtml(percentLabel)}</span>
    </li>
  `;
}

function renderLanguagesPanel(github = {}, translations = {}) {
  const languages = Array.isArray(github.languages) ? github.languages.filter(Boolean) : [];
  if (languages.length === 0) {
    return '';
  }
  const title = translations.languages?.title || 'Language mix';
  const subtitle = translations.languages?.subtitle || 'Distribution across the repository.';

  return `
    <section class="tp-card tp-github-panel">
      <header class="tp-card__header">
        <h3 class="tp-card__title">${escapeHtml(String(title))}</h3>
        <p class="tp-text-subtle">${escapeHtml(String(subtitle))}</p>
      </header>
      <ul class="tp-github-languages">
        ${languages.map((language) => renderLanguageBar(language)).join('')}
      </ul>
    </section>
  `;
}

function renderWorkflowBadges(github = {}, translations = {}) {
  const workflows = Array.isArray(github.workflows) ? github.workflows.filter(Boolean) : [];
  const valid = workflows
    .map((workflow) => {
      const badgeSrc = safeExternalUrl(workflow.badge || workflow.status_badge);
      if (badgeSrc === '#') {
        return null;
      }
      const href = safeExternalUrl(workflow.url || workflow.html_url);
      const label = workflow.name || workflow.label || 'Workflow';
      return {
        href,
        badgeSrc,
        label,
      };
    })
    .filter(Boolean);

  if (valid.length === 0) {
    return '';
  }
  const title = translations.workflows?.title || 'CI health';
  const subtitle = translations.workflows?.subtitle || 'Latest GitHub Actions badges.';

  const items = valid
    .map((workflow) => `
        <a class="tp-github-workflow" href="${escapeHtml(workflow.href)}" target="_blank" rel="noopener noreferrer">
          <img src="${escapeHtml(workflow.badgeSrc)}" alt="${escapeHtml(String(workflow.label))} status badge" loading="lazy" />
        </a>
      `)
    .join('');

  return `
    <section class="tp-card tp-github-panel">
      <header class="tp-card__header">
        <h3 class="tp-card__title">${escapeHtml(String(title))}</h3>
        <p class="tp-text-subtle">${escapeHtml(String(subtitle))}</p>
      </header>
      <div class="tp-github-workflows">
        ${items}
      </div>
    </section>
  `;
}

function renderMobileShowcase(mobile = {}, translations = {}) {
  const title = mobile.title || translations.title || 'Mobile companion';
  const subtitle = mobile.subtitle || translations.subtitle || 'Stay connected to operations on the move.';
  const tagline = mobile.tagline || translations.tagline || 'Carry the TradePulse cockpit with biometric-grade security.';

  const features = normaliseFeatureItems(mobile.features, translations.features || DEFAULT_MOBILE_FEATURES);
  const featureItems = features.length ? features : DEFAULT_MOBILE_FEATURES;
  const platforms = normalisePlatformItems(mobile.platforms, translations.platforms || DEFAULT_MOBILE_PLATFORMS);
  const platformItems = platforms.length ? platforms : DEFAULT_MOBILE_PLATFORMS;
  const metrics = normaliseMetricItems(mobile.metrics, translations.metrics || DEFAULT_MOBILE_METRICS);
  const metricItems = metrics.length ? metrics : DEFAULT_MOBILE_METRICS;

  const platformMarkup = platformItems.length
    ? `
        <div class="tp-mobile-platforms">
          ${platformItems
            .map((platform) => {
              const href = platform.href && platform.href !== '#' ? platform.href : '#';
              const isExternal = href !== '#';
              const attributes = isExternal
                ? `href="${escapeHtml(String(href))}" target="_blank" rel="noopener noreferrer"`
                : 'href="#" aria-disabled="true"';
              const description = platform.description
                ? `<span class="tp-text-subtle">${escapeHtml(String(platform.description))}</span>`
                : '';
              return `
                <a class="tp-mobile-platform" ${attributes}>
                  <span class="tp-mobile-platform__label">${escapeHtml(String(platform.label))}</span>
                  <span class="tp-text-muted">${escapeHtml(String(platform.badge || platform.label))}</span>
                  ${description}
                </a>
              `;
            })
            .join('')}
        </div>
      `
    : '';

  return `
    <section class="tp-card tp-mobile-card">
      <header class="tp-card__header">
        <h3 class="tp-card__title">${escapeHtml(String(title))}</h3>
        <p class="tp-text-subtle">${escapeHtml(String(subtitle))}</p>
      </header>
      ${tagline ? `<p class="tp-mobile-card__tagline">${escapeHtml(String(tagline))}</p>` : ''}
      ${platformMarkup}
      ${renderFeatureList(featureItems)}
      ${renderMetaList(metricItems)}
    </section>
  `;
}

function renderLocalizationPanel(localization = {}, translations = {}) {
  const title = localization.title || translations.title || 'Global language coverage';
  const subtitle = localization.subtitle || translations.subtitle || 'Six fully curated locales with compliance tone-of-voice.';
  const localeOverrides = localization.locales || translations.locales || {};
  const priorityLabels = { ...DEFAULT_LOCALISATION_PRIORITY_LABELS, ...(translations.priorityLabels || {}) };
  const supported = supportedLocales
    .map((code) => {
      const meta = localeMetadata[code] || {};
      const override = localeOverrides[code] || {};
      const translationDetails = (translations.locales && translations.locales[code]) || {};
      const label = override.label || translationDetails.label || meta.label || code;
      const nativeLabel = override.nativeLabel || translationDetails.nativeLabel || meta.nativeLabel || label;
      const reviewCadence = override.reviewCadence || translationDetails.reviewCadence || meta.reviewCadence || '';
      const priority = override.priority || translationDetails.priority || meta.priority || 'tier-2';
      return { code, label, nativeLabel, reviewCadence, priority };
    })
    .sort((a, b) => {
      const rankA = PRIORITY_ORDER[a.priority] ?? 99;
      const rankB = PRIORITY_ORDER[b.priority] ?? 99;
      if (rankA !== rankB) {
        return rankA - rankB;
      }
      return a.label.localeCompare(b.label);
    });

  const supportedLabelTemplate = translations.supportedLabel || '{count} supported locales';
  const supportedLabel = supportedLabelTemplate.replace('{count}', supported.length);
  const highlights = normaliseStringList(localization.highlights, translations.highlights || DEFAULT_LOCALISATION_HIGHLIGHTS);

  const ctaConfig = { ...(translations.cta || {}), ...(localization.cta || {}) };
  const ctaHref = safeExternalUrl(ctaConfig.href || ctaConfig.url);
  const showCta = ctaHref !== '#';
  const ctaLabel = ctaConfig.label || 'Request another locale';
  const footnote = localization.footnote || translations.footnote || '';

  const localesMarkup = supported
    .map((locale) => {
      const priorityLabel = priorityLabels[locale.priority] || locale.priority || 'tier';
      const native = locale.nativeLabel && locale.nativeLabel !== locale.label
        ? `<span class="tp-locale__native">${escapeHtml(String(locale.nativeLabel))}</span>`
        : '';
      const review = locale.reviewCadence
        ? `<span>${escapeHtml(String(locale.reviewCadence))}</span>`
        : '';
      return `
        <li class="tp-locale">
          <div class="tp-locale__header">
            <span class="tp-locale__name">${escapeHtml(String(locale.label))}</span>
            ${native}
          </div>
          <div class="tp-locale__meta">
            <span class="tp-pill">${escapeHtml(String(priorityLabel))}</span>
            ${review}
          </div>
        </li>
      `;
    })
    .join('');

  const highlightsMarkup = highlights.length
    ? `
        <ul class="tp-bullet-list">
          ${highlights.map((item) => `<li>${escapeHtml(String(item))}</li>`).join('')}
        </ul>
      `
    : '';

  const ctaMarkup = showCta
    ? `
        <a class="tp-community-panel__cta" href="${escapeHtml(ctaHref)}" target="_blank" rel="noopener noreferrer">
          <span>${escapeHtml(String(ctaLabel))}</span>
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3 8a.75.75 0 0 1 .75-.75h5.638L7.23 5.09a.75.75 0 1 1 1.04-1.08l3.5 3.25a.75.75 0 0 1 0 1.08l-3.5 3.25a.75.75 0 1 1-1.04-1.08l2.158-2.16H3.75A.75.75 0 0 1 3 8Z" fill="currentColor"/></svg>
        </a>
      `
    : '';

  return `
    <section class="tp-card">
      <header class="tp-card__header">
        <h3 class="tp-card__title">${escapeHtml(String(title))}</h3>
        <p class="tp-text-subtle">${escapeHtml(String(subtitle))}</p>
      </header>
      <p class="tp-text-muted">${escapeHtml(String(supportedLabel))}</p>
      <ul class="tp-locale-list">${localesMarkup}</ul>
      ${highlightsMarkup}
      ${footnote ? `<p class="tp-text-subtle">${escapeHtml(String(footnote))}</p>` : ''}
      ${ctaMarkup}
    </section>
  `;
}

function renderCommunityPanel(community = {}, translations = {}) {
  const title = community.title || translations.title || 'Open community engagement';
  const subtitle = community.subtitle || translations.subtitle || 'Structured pathways for maintainers and contributors.';
  const actions = normaliseFeatureItems(community.actions, translations.actions || DEFAULT_COMMUNITY_ACTIONS);
  const actionItems = actions.length ? actions : DEFAULT_COMMUNITY_ACTIONS;
  const metrics = normaliseMetricItems(community.metrics, translations.metrics || DEFAULT_COMMUNITY_METRICS);
  const metricItems = metrics.length ? metrics : DEFAULT_COMMUNITY_METRICS;
  const highlights = normaliseStringList(community.highlights, translations.highlights || DEFAULT_COMMUNITY_HIGHLIGHTS);
  const ctaDefaults = { ...DEFAULT_COMMUNITY_CTA, ...(translations.cta || {}) };
  const ctaConfig = { ...ctaDefaults, ...(community.cta || {}) };
  const ctaHref = safeExternalUrl(ctaConfig.href || ctaConfig.url);
  const ctaLabel = ctaConfig.label || ctaDefaults.label;
  const ctaDescription = ctaConfig.description || translations.cta?.description || community.cta?.description || '';

  const actionsMarkup = actionItems.length
    ? `
        <div class="tp-community-actions">
          ${actionItems
            .map(
              (action) => `
                <article class="tp-community-action">
                  <h4 class="tp-community-action__title">${escapeHtml(String(action.title))}</h4>
                  ${action.description ? `<p class="tp-community-action__body">${escapeHtml(String(action.description))}</p>` : ''}
                </article>
              `,
            )
            .join('')}
        </div>
      `
    : '';

  const highlightsMarkup = highlights.length
    ? `
        <ul class="tp-bullet-list">
          ${highlights.map((item) => `<li>${escapeHtml(String(item))}</li>`).join('')}
        </ul>
      `
    : '';

  const ctaMarkup = ctaHref === '#'
    ? ''
    : `
        <a class="tp-community-panel__cta" href="${escapeHtml(ctaHref)}" target="_blank" rel="noopener noreferrer">
          <span>${escapeHtml(String(ctaLabel))}</span>
          <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M3 8a.75.75 0 0 1 .75-.75h5.638L7.23 5.09a.75.75 0 1 1 1.04-1.08l3.5 3.25a.75.75 0 0 1 0 1.08l-3.5 3.25a.75.75 0 1 1-1.04-1.08l2.158-2.16H3.75A.75.75 0 0 1 3 8Z" fill="currentColor"/></svg>
        </a>
      `;

  return `
    <section class="tp-card tp-community-panel">
      <header class="tp-card__header">
        <h3 class="tp-card__title">${escapeHtml(String(title))}</h3>
        <p class="tp-text-subtle">${escapeHtml(String(subtitle))}</p>
      </header>
      ${renderMetaList(metricItems)}
      ${actionsMarkup}
      ${highlightsMarkup}
      ${ctaDescription ? `<p class="tp-text-subtle">${escapeHtml(String(ctaDescription))}</p>` : ''}
      ${ctaMarkup}
    </section>
  `;
}

export function renderOverviewView({ github = {}, mobile = {}, localization = {}, community = {} } = {}) {
  const translations = getTranslations();
  const heroHtml = renderHero(translations.hero, github);
  const badgesHtml = renderBadges(github, translations.badges);
  const releasePanel = renderReleasePanel(github, translations.panels);
  const languagesPanel = renderLanguagesPanel(github, translations.panels || {});
  const workflowPanel = renderWorkflowBadges(github, translations.panels || {});
  const mobilePanel = renderMobileShowcase(mobile || github.mobile || {}, translations.mobile || {});
  const localizationPanel = renderLocalizationPanel(localization || github.localization || {}, translations.localization || {});
  const communityPanel = renderCommunityPanel(community || github.community || {}, translations.community || {});

  const html = `
    <article class="tp-view tp-view--overview">
      <header class="tp-view__header">
        <h1 class="tp-view__title">${escapeHtml(String(translations.heading))}</h1>
        ${translations.subtitle ? `<p class="tp-view__subtitle">${escapeHtml(String(translations.subtitle))}</p>` : ''}
      </header>
      ${heroHtml}
      <section class="tp-grid tp-grid--two tp-overview-grid">
        <section class="tp-card tp-github-panel tp-github-panel--stretch">
          <header class="tp-card__header">
            <h3 class="tp-card__title">${escapeHtml(translations.badges?.title || 'Community traction')}</h3>
            <p class="tp-text-subtle">${escapeHtml(translations.badges?.subtitle || 'Live GitHub signals summarised for leadership review.')}</p>
          </header>
          ${badgesHtml}
        </section>
        ${releasePanel}
        ${languagesPanel}
        ${workflowPanel}
      </section>
      <section class="tp-grid tp-grid--two tp-overview-grid tp-overview-grid--experience">
        ${mobilePanel}
        ${localizationPanel}
        ${communityPanel}
      </section>
    </article>
  `;

  return {
    html,
    github,
  };
}


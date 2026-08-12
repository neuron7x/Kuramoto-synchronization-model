import { escapeHtml, formatNumber, formatPercent, formatTimestamp } from '../core/formatters.js';
import { t, getMessage } from '../i18n/index.js';

/**
 * @typedef {import('../types/api').GithubOverview} GithubOverview
 * @typedef {import('../types/api').GithubLanguageShare} GithubLanguageShare
 * @typedef {import('../types/api').GithubWorkflowBadge} GithubWorkflowBadge
 * @typedef {import('../types/api').CommunityProfile} CommunityProfile
 * @typedef {import('../types/api').DashboardOverviewPayload} DashboardOverviewPayload
 */

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

function coerceOptionalNumber(value) {
  if (Number.isFinite(value)) {
    return Number(value);
  }
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
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

const SAFE_COLOR_PATTERN =
  /^(?:#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})|rgba?\(\s*(?:\d{1,3}\s*,\s*){2}\d{1,3}(?:\s*,\s*(?:0|1|0?\.\d+))?\s*\)|hsla?\(\s*\d{1,3}(?:\.\d+)?\s*,\s*\d{1,3}%\s*,\s*\d{1,3}%\s*(?:,\s*(?:0|1|0?\.\d+))?\s*\)|[a-zA-Z]{1,20})$/;

function sanitizeCssColor(value, fallback = '#38bdf8') {
  if (typeof value !== 'string') {
    return fallback;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return fallback;
  }
  if (SAFE_COLOR_PATTERN.test(trimmed)) {
    return trimmed;
  }
  return fallback;
}

function toRatio(value) {
  const numeric = coerceOptionalNumber(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  if (numeric > 1) {
    return clamp01(numeric / 100);
  }
  if (numeric < 0) {
    return 0;
  }
  return clamp01(numeric);
}

function formatRatio(value, options) {
  if (!Number.isFinite(value)) {
    return '—';
  }
  return formatPercent(value, options);
}

function toneFromStatus(status) {
  if (typeof status !== 'string') {
    return null;
  }
  const lowered = status.toLowerCase();
  if (['operational', 'healthy', 'green', 'pass'].includes(lowered)) {
    return 'positive';
  }
  if (['degraded', 'warning', 'amber', 'needs attention'].includes(lowered)) {
    return 'neutral';
  }
  if (['critical', 'red', 'failed', 'outage'].includes(lowered)) {
    return 'negative';
  }
  return null;
}

function compareAgainstTarget(actual, target) {
  if (!Number.isFinite(actual) || !Number.isFinite(target)) {
    return null;
  }
  if (actual >= target) {
    return 'positive';
  }
  if (actual >= target * 0.95) {
    return 'neutral';
  }
  return 'negative';
}

function formatTemplate(template, params = {}) {
  if (typeof template !== 'string') {
    return '';
  }
  return template.replace(/\{(\w+)\}/g, (_, key) => {
    if (Object.prototype.hasOwnProperty.call(params, key)) {
      const value = params[key];
      return value == null ? '' : String(value);
    }
    return '';
  });
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
  };
}

function buildHeroStats(heroTranslations = {}, github = {}) {
  const statsT = heroTranslations.stats || {};
  const commits = coerceNumber(github.commits_30d, 0);
  const merges = coerceNumber(github.prs?.merged_30d, github.merged_prs_30d);
  const contributors = coerceNumber(github.contributors, 0);
  const newContributors = coerceNumber(github.new_contributors_30d, 0);
  const starsDelta = Number.isFinite(github.stars_delta) ? github.stars_delta : null;

  const stats = [
    {
      key: 'stars',
      label: statsT.stars?.label || 'Stargazers',
      value: formatNumber(coerceNumber(github.stars, 0)),
      unit: statsT.stars?.unit || '',
      trend:
        Number.isFinite(starsDelta) && starsDelta !== 0
          ? statsT.stars?.trend || formatDelta(starsDelta)
          : null,
      tone: Number.isFinite(starsDelta) ? (starsDelta < 0 ? 'negative' : 'positive') : null,
    },
    {
      key: 'velocity',
      label: statsT.velocity?.label || 'Velocity (30d)',
      value: formatNumber(commits),
      unit: statsT.velocity?.unit || 'commits',
      trend:
        merges > 0
          ? (statsT.velocity?.trend || `${formatNumber(merges)} merges`)
          : null,
      tone: 'neutral',
    },
    {
      key: 'contributors',
      label: statsT.contributors?.label || 'Contributor health',
      value: formatNumber(contributors),
      unit: statsT.contributors?.unit || 'contributors',
      trend:
        newContributors !== 0
          ? (statsT.contributors?.trend || `${newContributors > 0 ? '+' : ''}${formatNumber(newContributors)} new`)
          : null,
      tone: newContributors === 0 ? null : newContributors > 0 ? 'positive' : 'negative',
    },
  ];

  return stats.filter((stat) => stat.value !== null && stat.value !== undefined);
}

/**
 * @param {{ key: string; label: string; value: string | number; unit?: string | null; tone?: string | null; trend?: string | null; }} stat
 */
function renderHeroStat(stat) {
  if (!stat) {
    return '';
  }

  const unit = stat.unit ? `<span class="tp-hero__stat-unit">${escapeHtml(String(stat.unit))}</span>` : '';
  const tone = stat.tone ? ` tp-hero__stat-trend--${stat.tone}` : '';
  const trend = stat.trend
    ? `<p class="tp-hero__stat-trend${tone}">${escapeHtml(String(stat.trend))}</p>`
    : '';

  return `
    <div class="tp-hero__stat">
      <dt class="tp-hero__stat-label">${escapeHtml(String(stat.label))}</dt>
      <dd class="tp-hero__stat-value">
        <span class="tp-hero__stat-number">${escapeHtml(String(stat.value))}</span>
        ${unit}
      </dd>
      ${trend}
    </div>
  `;
}

/**
 * @param {Record<string, unknown>} heroTranslations
 * @param {GithubOverview} github
 */
function renderHero(heroTranslations = {}, github = {}) {
  const eyebrow = heroTranslations.eyebrow || t('views.overview.hero.eyebrow');
  const title = heroTranslations.title || t('views.overview.hero.title');
  const subtitle = heroTranslations.subtitle || t('views.overview.hero.subtitle');
  const cta = heroTranslations.cta || t('views.overview.hero.cta');
  const repo = github.repository || github.repo || 'geosync/GeoSync';
  const org = github.organization || github.owner || 'GeoSync';
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

  const stats = buildHeroStats(heroTranslations, github);
  const statsMarkup =
    stats.length > 0
      ? `
          <dl class="tp-hero__stats">
            ${stats.map((stat) => renderHeroStat(stat)).join('')}
          </dl>
        `
      : '';

  return `
    <section class="tp-hero" data-role="overview-hero">
      <div class="tp-hero__content">
        <p class="tp-hero__eyebrow">${escapeHtml(String(eyebrow || repoLabel))}</p>
        <h2 class="tp-hero__title">${escapeHtml(String(title || 'GeoSync Product Pulse'))}</h2>
        <p class="tp-hero__subtitle">${escapeHtml(String(subtitle || 'Visualise adoption, cadence, and quality signals sourced from GitHub.'))}</p>
        <div class="tp-hero__meta">
          <span class="tp-hero__repo">${escapeHtml(repoLabel)}</span>
          ${action}
        </div>
        ${statsMarkup}
      </div>
      <div class="tp-hero__visual" aria-hidden="true">
        <div class="tp-hero__orb tp-hero__orb--primary"></div>
        <div class="tp-hero__orb tp-hero__orb--secondary"></div>
        <div class="tp-hero__grid"></div>
      </div>
    </section>
  `;
}

function renderMomentumMetric(metric) {
  if (!metric) {
    return '';
  }

  const tone = metric.tone ? ` tp-momentum__trend--${metric.tone}` : '';
  const progress = Number.isFinite(metric.progress) ? clamp01(metric.progress) : 0;
  const progressStyle = `style="transform: scaleX(${progress});"`;

  return `
    <li class="tp-momentum__item">
      <div class="tp-momentum__item-header">
        <span class="tp-momentum__label">${escapeHtml(String(metric.label))}</span>
        ${metric.trend ? `<span class="tp-momentum__trend${tone}">${escapeHtml(String(metric.trend))}</span>` : ''}
      </div>
      <div class="tp-momentum__value">${escapeHtml(String(metric.value))}</div>
      ${metric.hint ? `<p class="tp-momentum__hint">${escapeHtml(String(metric.hint))}</p>` : ''}
      <div class="tp-progress tp-progress--glow" role="presentation">
        <div class="tp-progress__bar" ${progressStyle}></div>
      </div>
    </li>
  `;
}

/**
 * @param {GithubOverview} github
 * @param {Record<string, unknown>} translations
 */
function renderMomentumPanel(github = {}, translations = {}) {
  const panelsT = translations || {};
  const momentumT = panelsT.momentum || {};
  const title = momentumT.title || 'Momentum signals';
  const subtitle = momentumT.subtitle || 'Track repository health targets at a glance.';

  const commits = coerceNumber(github.commits_30d, 0);
  const mergedPrs = coerceNumber(github.prs?.merged_30d, github.merged_prs_30d);
  const stars = coerceNumber(github.stars, 0);
  const starsDelta = Number.isFinite(github.stars_delta) ? github.stars_delta : 0;
  const watchersGrowth = Number.isFinite(github.watchers_growth) ? github.watchers_growth : 0;
  const contributors = coerceNumber(github.contributors, 0);
  const newContributors = coerceNumber(github.new_contributors_30d, 0);

  const velocityTarget = coerceNumber(momentumT.velocity?.target, 200) || 200;
  const engagementTarget = coerceNumber(momentumT.engagement?.target, 0.2) || 0.2;
  const contributorTarget = coerceNumber(momentumT.contributors?.target, 120) || 120;

  const mergeRatio = commits > 0 ? mergedPrs / commits : 0;
  const contributorMomentum = contributors > 0 ? newContributors / contributors : 0;

  const metrics = [
    {
      key: 'velocity',
      label: momentumT.velocity?.label || 'Delivery velocity',
      value: `${formatNumber(commits)} commits`,
      hint:
        mergedPrs > 0
          ? (momentumT.velocity?.hint || `${formatNumber(mergedPrs)} merges shipped this month`)
          : null,
      trend:
        mergeRatio
          ? (momentumT.velocity?.trend || `${formatPercent(Math.min(mergeRatio, 2))} merge/commit ratio`)
          : null,
      tone: mergeRatio >= 0.5 ? 'positive' : 'neutral',
      progress: velocityTarget > 0 ? commits / velocityTarget : 0,
    },
    {
      key: 'engagement',
      label: momentumT.engagement?.label || 'Community engagement',
      value: `${formatNumber(stars)} stars`,
      hint:
        Number.isFinite(starsDelta) && starsDelta !== 0
          ? (momentumT.engagement?.hint || `${formatDelta(starsDelta)} month-over-month star growth`)
          : null,
      trend:
        watchersGrowth
          ? (momentumT.engagement?.trend || formatDelta(watchersGrowth))
          : null,
      tone: watchersGrowth > 0 ? 'positive' : watchersGrowth < 0 ? 'negative' : 'neutral',
      progress: engagementTarget > 0 ? Math.max(0, watchersGrowth) / engagementTarget : 0,
    },
    {
      key: 'contributors',
      label: momentumT.contributors?.label || 'Contributor energy',
      value: `${formatNumber(contributors)} people`,
      hint:
        newContributors
          ? (momentumT.contributors?.hint || `${newContributors > 0 ? '+' : ''}${formatNumber(newContributors)} new engineers this month`)
          : null,
      trend:
        contributorMomentum
          ? (momentumT.contributors?.trend || formatDelta(contributorMomentum))
          : null,
      tone: newContributors > 0 ? 'positive' : newContributors < 0 ? 'negative' : 'neutral',
      progress: contributorTarget > 0 ? contributors / contributorTarget : 0,
    },
  ].filter(Boolean);

  if (metrics.length === 0) {
    return '';
  }

  return `
    <section class="tp-card tp-github-panel tp-momentum">
      <header class="tp-card__header">
        <h3 class="tp-card__title">${escapeHtml(String(title))}</h3>
        <p class="tp-text-subtle">${escapeHtml(String(subtitle))}</p>
      </header>
      <ul class="tp-momentum__list">
        ${metrics.map((metric) => renderMomentumMetric(metric)).join('')}
      </ul>
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

/**
 * @param {GithubOverview} github
 * @param {Record<string, unknown>} translations
 */
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

/**
 * @param {GithubOverview} github
 * @param {Record<string, unknown>} translations
 */
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

/**
 * @param {GithubLanguageShare | null | undefined} language
 */
function renderLanguageBar(language) {
  const name = language?.name || 'Unknown';
  const share = clamp01(language?.share ?? language?.percent ?? language?.percentage ?? 0);
  const percentLabel = formatPercent(share, { maximumFractionDigits: 1 });
  const swatchColor = sanitizeCssColor(language?.color, '#38bdf8');
  return `
    <li class="tp-github-language">
      <div class="tp-github-language__label">
        <span class="tp-github-language__swatch" style="--tp-language-color: ${escapeHtml(swatchColor)};"></span>
        <span>${escapeHtml(String(name))}</span>
      </div>
      <div class="tp-progress tp-progress--slim" role="presentation">
        <div class="tp-progress__bar" style="transform: scaleX(${share});"></div>
      </div>
      <span class="tp-github-language__value">${escapeHtml(percentLabel)}</span>
    </li>
  `;
}

/**
 * @param {GithubOverview} github
 * @param {Record<string, unknown>} translations
 */
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

/**
 * @param {GithubOverview} github
 * @param {Record<string, unknown>} translations
 */
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
      const width = coerceNumber(
        workflow.badgeWidth ?? workflow.badge_width ?? workflow.width,
        null,
      );
      const height = coerceNumber(
        workflow.badgeHeight ?? workflow.badge_height ?? workflow.height,
        null,
      );
      return {
        href,
        badgeSrc,
        label,
        width,
        height,
      };
    })
    .filter(Boolean);

  if (valid.length === 0) {
    return '';
  }
  const title = translations.workflows?.title || 'CI health';
  const subtitle = translations.workflows?.subtitle || 'Latest GitHub Actions badges.';

  const items = valid
    .map((workflow) => {
      const widthAttr = Number.isFinite(workflow.width) && workflow.width > 0
        ? ` width="${Number(workflow.width)}"`
        : '';
      const heightAttr = Number.isFinite(workflow.height) && workflow.height > 0
        ? ` height="${Number(workflow.height)}"`
        : '';
      return `
        <a class="tp-github-workflow" href="${escapeHtml(workflow.href)}" target="_blank" rel="noopener noreferrer">
          <img src="${escapeHtml(workflow.badgeSrc)}" alt="${escapeHtml(String(workflow.label))} status badge" loading="lazy" decoding="async" fetchpriority="low" style="max-width: 100%; height: auto;"${widthAttr}${heightAttr} />
        </a>
      `;
    })
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

function renderQualityPanel(github = {}, translations = {}) {
  const rawQuality = github.quality;
  if (!rawQuality || typeof rawQuality !== 'object') {
    return '';
  }

  const panelT = translations.quality || {};
  const metricsSource =
    typeof rawQuality.metrics === 'object' && rawQuality.metrics !== null
      ? rawQuality.metrics
      : rawQuality;
  const sloSource =
    typeof rawQuality.slo === 'object' && rawQuality.slo !== null
      ? rawQuality.slo
      : {};

  const coverage = toRatio(
    metricsSource.coverage ?? metricsSource.coverage_ratio ?? metricsSource.coverageRate,
  );
  const coverageTarget = toRatio(
    sloSource.coverage ?? metricsSource.coverage_target ?? metricsSource.coverageTarget,
  );
  const uptime = toRatio(
    metricsSource.uptime ?? metricsSource.uptime_90d ?? metricsSource.uptimeRolling,
  );
  const uptimeTarget = toRatio(
    sloSource.uptime ?? metricsSource.uptime_target ?? metricsSource.uptimeTarget,
  );
  const incidents = coerceOptionalNumber(
    metricsSource.incidents_30d ?? metricsSource.incidents ?? rawQuality.incidents_30d,
  );
  const mttrHours = coerceOptionalNumber(
    metricsSource.mttr_hours ?? metricsSource.mttr ?? rawQuality.mttr_hours,
  );
  const healthScore = coerceOptionalNumber(
    metricsSource.health_score ?? metricsSource.health ?? rawQuality.health_score,
  );
  const status = rawQuality.status || metricsSource.status;
  const lastAudit =
    rawQuality.last_audit ||
    rawQuality.lastAudit ||
    metricsSource.last_audit ||
    (rawQuality.audit && rawQuality.audit.completed_at) ||
    null;

  const metrics = [
    {
      key: 'coverage',
      label: panelT.metrics?.coverage?.label || 'Automated coverage',
      value: formatRatio(coverage, { maximumFractionDigits: 1 }),
      hint:
        Number.isFinite(coverageTarget)
          ? formatTemplate(panelT.metrics?.coverage?.hint || 'Target {target}', {
              target: formatRatio(coverageTarget, { maximumFractionDigits: 1 }),
            })
          : '',
      tone: compareAgainstTarget(coverage, coverageTarget),
    },
    {
      key: 'uptime',
      label: panelT.metrics?.uptime?.label || 'Uptime (90d)',
      value: formatRatio(uptime, { maximumFractionDigits: 2 }),
      hint:
        Number.isFinite(uptimeTarget)
          ? formatTemplate(panelT.metrics?.uptime?.hint || 'Target {target}', {
              target: formatRatio(uptimeTarget, { maximumFractionDigits: 2 }),
            })
          : '',
      tone: compareAgainstTarget(uptime, uptimeTarget),
    },
    {
      key: 'incidents',
      label: panelT.metrics?.incidents?.label || 'Incidents (30d)',
      value: Number.isFinite(incidents)
        ? formatNumber(Math.max(0, incidents), { maximumFractionDigits: 0 })
        : '—',
      hint: panelT.metrics?.incidents?.hint || '',
      tone: Number.isFinite(incidents) && incidents > 0 ? 'negative' : 'positive',
    },
    {
      key: 'mttr',
      label: panelT.metrics?.mttr?.label || 'MTTR',
      value: Number.isFinite(mttrHours)
        ? `${formatNumber(Math.max(0, mttrHours), {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1,
          })}h`
        : '—',
      hint: panelT.metrics?.mttr?.hint || '',
      tone: Number.isFinite(mttrHours) && mttrHours > 4 ? 'negative' : 'neutral',
    },
    {
      key: 'health',
      label: panelT.metrics?.health?.label || 'Health score',
      value: Number.isFinite(healthScore)
        ? healthScore <= 1
          ? formatRatio(Math.max(0, healthScore), { maximumFractionDigits: 1 })
          : formatNumber(healthScore, { maximumFractionDigits: 1 })
        : '—',
      hint: panelT.metrics?.health?.hint || '',
      tone: Number.isFinite(healthScore) && healthScore < 0.7 ? 'negative' : null,
    },
  ].filter((metric) => metric.value !== '—' || metric.hint);

  if (metrics.length === 0 && !status && !lastAudit) {
    return '';
  }

  const statusTone = toneFromStatus(status);
  const statusBadge = status
    ? `<span class="tp-pill${statusTone ? ` tp-pill--${statusTone}` : ''}">${escapeHtml(String(status))}</span>`
    : '';

  const metricsMarkup = metrics.length
    ? `
        <dl class="tp-quality__metrics">
          ${metrics
            .map(
              (metric) => `
                <div class="tp-quality__metric">
                  <dt>${escapeHtml(String(metric.label))}</dt>
                  <dd>
                    <span class="tp-quality__metric-value${
                      metric.tone ? ` tp-quality__metric-value--${metric.tone}` : ''
                    }">${escapeHtml(String(metric.value))}</span>
                    ${
                      metric.hint
                        ? `<p class="tp-quality__metric-hint">${escapeHtml(String(metric.hint))}</p>`
                        : ''
                    }
                  </dd>
                </div>
              `,
            )
            .join('')}
        </dl>
      `
    : '';

  const auditMarkup = lastAudit
    ? `<p class="tp-quality__audit">${escapeHtml(
        formatTemplate(panelT.audit?.label || 'Last audit {date}', {
          date: formatTimestamp(new Date(lastAudit).getTime()),
        }),
      )}</p>`
    : '';

  return `
    <section class="tp-card tp-github-panel tp-quality">
      <header class="tp-card__header">
        <h3 class="tp-card__title">${escapeHtml(String(panelT.title || 'Reliability guardrails'))}</h3>
        <p class="tp-text-subtle">${escapeHtml(
          String(panelT.subtitle || 'SLO adherence across reliability-critical signals.'),
        )}</p>
        ${statusBadge}
      </header>
      ${metricsMarkup}
      ${auditMarkup}
    </section>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderCommunitySpotlight(community = {}, translations = {}) {
  if (!community || typeof community !== 'object') {
    return '';
  }

  const panelT = translations.community || {};
  const metricsT = panelT.metrics || {};
  const metrics = community.metrics || {};

  const goodFirstIssues = coerceNumber(
    metrics.goodFirstIssues ?? community.good_first_issues ?? community.goodFirstIssues,
    null,
  );
  const mentorshipSeats = coerceNumber(
    metrics.mentorshipSeats ?? community.mentorship_seats ?? community.mentorshipSeats,
    null,
  );
  const responseHours = coerceNumber(
    metrics.responseHours ?? community.response_hours ?? community.responseHours,
    null,
  );
  const sponsors = coerceNumber(metrics.sponsors ?? community.sponsors?.total, null);

  const metricItems = [
    {
      key: 'goodFirstIssues',
      label: metricsT.goodFirstIssues?.label || 'Good-first issues',
      value:
        goodFirstIssues != null ? formatNumber(goodFirstIssues, { maximumFractionDigits: 0 }) : '—',
      hint:
        goodFirstIssues != null
          ? formatTemplate(metricsT.goodFirstIssues?.hint || '', {
              count: formatNumber(goodFirstIssues, { maximumFractionDigits: 0 }),
            })
          : '',
    },
    {
      key: 'mentorship',
      label: metricsT.mentorship?.label || 'Mentorship seats',
      value:
        mentorshipSeats != null ? formatNumber(mentorshipSeats, { maximumFractionDigits: 0 }) : '—',
      hint:
        mentorshipSeats != null
          ? formatTemplate(metricsT.mentorship?.hint || '', {
              count: formatNumber(mentorshipSeats, { maximumFractionDigits: 0 }),
            })
          : '',
    },
    {
      key: 'response',
      label: metricsT.response?.label || 'Median response',
      value:
        responseHours != null
          ? `${formatNumber(responseHours, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}h`
          : '—',
      hint:
        responseHours != null
          ? formatTemplate(metricsT.response?.hint || '', {
              hours: formatNumber(responseHours, {
                minimumFractionDigits: 1,
                maximumFractionDigits: 1,
              }),
            })
          : '',
    },
    {
      key: 'sponsors',
      label: metricsT.sponsors?.label || 'Sponsors',
      value:
        sponsors != null ? formatNumber(sponsors, { maximumFractionDigits: 0 }) : '—',
      hint:
        sponsors != null
          ? formatTemplate(metricsT.sponsors?.hint || '', {
              count: formatNumber(sponsors, { maximumFractionDigits: 0 }),
            })
          : '',
    },
  ].filter(Boolean);

  const programs = Array.isArray(community.programs) ? community.programs.filter(Boolean).slice(0, 2) : [];
  const resources = Array.isArray(community.resources)
    ? community.resources.filter(Boolean).slice(0, 2)
    : [];

  const programItems = programs
    .map((program) => {
      const name = program?.name || program?.title;
      const url = safeExternalUrl(program?.url || program?.href);
      return `
        <li>
          <a class="tp-community-spotlight__program" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(String(name || panelT.programs?.fallback || 'Program'))}
          </a>
        </li>
      `;
    })
    .join('');

  const resourceItems = resources
    .map((resource) => {
      const name = resource?.label || resource?.title;
      const url = safeExternalUrl(resource?.url || resource?.href);
      return `
        <li>
          <a class="tp-community-spotlight__resource" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(String(name || panelT.resources?.fallback || 'Resource'))}
          </a>
        </li>
      `;
    })
    .join('');

  const hasPrograms = Boolean(programItems);
  const hasResources = Boolean(resourceItems);
  if (metricItems.length === 0 && !hasPrograms && !hasResources) {
    return '';
  }

  return `
    <section class="tp-card tp-community-spotlight" aria-labelledby="tp-community-spotlight">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-spotlight">${escapeHtml(
          String(panelT.title || 'Open-source community'),
        )}</h3>
        ${
          panelT.subtitle
            ? `<p class="tp-text-subtle">${escapeHtml(String(panelT.subtitle))}</p>`
            : ''
        }
      </header>
      ${
        metricItems.length
          ? `
              <dl class="tp-community-spotlight__metrics">
                ${metricItems
                  .map(
                    (item) => `
                      <div class="tp-community-spotlight__metric">
                        <dt>${escapeHtml(String(item.label))}</dt>
                        <dd>${escapeHtml(String(item.value))}</dd>
                        ${
                          item.hint
                            ? `<p class="tp-community-spotlight__metric-hint">${escapeHtml(String(item.hint))}</p>`
                            : ''
                        }
                      </div>
                    `,
                  )
                  .join('')}
              </dl>
            `
          : ''
      }
      ${
        hasPrograms
          ? `
              <div class="tp-community-spotlight__section">
                <h4>${escapeHtml(String(panelT.programs?.title || 'Active programs'))}</h4>
                <ul class="tp-community-spotlight__list">${programItems}</ul>
              </div>
            `
          : ''
      }
      ${
        hasResources
          ? `
              <div class="tp-community-spotlight__section">
                <h4>${escapeHtml(String(panelT.resources?.title || 'Contributor resources'))}</h4>
                <ul class="tp-community-spotlight__list">${resourceItems}</ul>
              </div>
            `
          : ''
      }
    </section>
  `;
}

/**
 * @param {DashboardOverviewPayload | { github?: GithubOverview | null }} [options]
 * @returns {{ html: string; github: GithubOverview }}
 */
export function renderOverviewView({ github = {} } = {}) {
  /** @type {GithubOverview} */
  const githubProfile = github ?? {};
  const translations = getTranslations();
  const heroHtml = renderHero(translations.hero, githubProfile);
  const badgesHtml = renderBadges(githubProfile, translations.badges);
  const releasePanel = renderReleasePanel(githubProfile, translations.panels);
  const languagesPanel = renderLanguagesPanel(githubProfile, translations.panels || {});
  const workflowPanel = renderWorkflowBadges(githubProfile, translations.panels || {});
  const momentumPanel = renderMomentumPanel(githubProfile, translations.panels || {});
  const qualityPanel = renderQualityPanel(githubProfile, translations.panels || {});
  const communityPanel = renderCommunitySpotlight(githubProfile.community, translations.panels || {});

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
        ${momentumPanel}
        ${qualityPanel}
        ${languagesPanel}
        ${workflowPanel}
        ${communityPanel}
      </section>
    </article>
  `;

  return {
    html,
    github: githubProfile,
  };
}


import { escapeHtml, formatCurrency, formatNumber } from '../core/formatters.js';
import { getLocaleConfig, getMessage, t } from '../i18n/index.js';

/**
 * @typedef {import('../types/api').CommunityProfile} CommunityProfile
 * @typedef {import('../types/api').CommunityProgram} CommunityProgram
 * @typedef {import('../types/api').CommunityEvent} CommunityEvent
 * @typedef {import('../types/api').CommunityResource} CommunityResource
 * @typedef {import('../types/api').CommunityHub} CommunityHub
 * @typedef {import('../types/api').CommunityOpportunity} CommunityOpportunity
 * @typedef {import('../types/api').CommunityChampion} CommunityChampion
 * @typedef {import('../types/api').CommunityChannel} CommunityChannel
 * @typedef {import('../types/api').GithubOverview} GithubOverview
 * @typedef {import('../types/api').DashboardCommunityPayload} DashboardCommunityPayload
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

function safeExternalUrl(url) {
  const raw = typeof url === 'string' ? url.trim() : '';
  if (raw.startsWith('https://') || raw.startsWith('http://')) {
    return raw;
  }
  return '#';
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

function normaliseCategory(value) {
  if (typeof value !== 'string') {
    return '';
  }
  return value.trim().toLowerCase().replace(/\s+/g, '-');
}

function parseDateLabel(value, fallback = '') {
  if (!value) {
    return fallback;
  }
  const date = new Date(value);
  if (!Number.isNaN(date.getTime())) {
    return date.toISOString().slice(0, 7);
  }
  const iso = `${value}`;
  if (/^\d{4}-\d{2}$/.test(iso)) {
    return iso;
  }
  return fallback || String(value);
}

function formatTimelineLabel(value, translations = {}) {
  const label = parseDateLabel(value, '');
  if (!label) {
    return escapeHtml(String(value || translations.fallbackPeriod || ''));
  }
  const [year, month] = label.split('-');
  if (!year || !month) {
    return escapeHtml(String(label));
  }
  try {
    const formatted = new Date(Number(year), Number(month) - 1, 1).toLocaleString(undefined, {
      month: 'short',
      year: 'numeric',
    });
    return escapeHtml(formatted);
  } catch {
    return escapeHtml(String(label));
  }
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @returns {Array<{ period: string | undefined; contributions: number | null; newcomers: number | null; ships: number | null; highlights: string[]; }>}
 */
function buildEngagementEntries(community = {}) {
  const timeline = Array.isArray(community.engagement)
    ? community.engagement
    : Array.isArray(community.timeline)
    ? community.timeline
    : Array.isArray(community.milestones)
    ? community.milestones
    : [];

  return timeline
    .map((entry) => {
      if (!entry) {
        return null;
      }
      const contributions = coerceNumber(entry.contributions ?? entry.total ?? entry.count, null);
      const newcomers = coerceNumber(entry.newContributors ?? entry.newcomers, null);
      const highlights = Array.isArray(entry.highlights)
        ? entry.highlights.filter(Boolean).slice(0, 3)
        : entry.highlight
        ? [entry.highlight]
        : [];
      const ships = coerceNumber(entry.releases ?? entry.majorReleases ?? entry.ships, null);
      if (contributions == null && newcomers == null && ships == null && highlights.length === 0) {
        return null;
      }
      return {
        period: entry.period || entry.month || entry.label || entry.date,
        contributions,
        newcomers,
        ships,
        highlights,
      };
    })
    .filter(Boolean);
}

/**
 * @param {{ period: string | undefined; contributions: number | null; newcomers: number | null; ships: number | null; highlights: string[] }} entry
 * @param {Record<string, unknown>} translations
 */
function renderTimelineEntry(entry, translations = {}) {
  const labels = translations.labels || {};
  const contributionsLabel = labels.contributions || 'Contributions';
  const newcomersLabel = labels.newcomers || 'New contributors';
  const releasesLabel = labels.releases || 'Major releases';
  const highlightsLabel = labels.highlights || 'Highlights';

  const contributions =
    entry.contributions != null
      ? `<div class="tp-community__timeline-metric">
          <span class="tp-community__timeline-value">${escapeHtml(
            String(formatNumber(entry.contributions, { maximumFractionDigits: 0 })),
          )}</span>
          <span class="tp-community__timeline-label">${escapeHtml(String(contributionsLabel))}</span>
        </div>`
      : '';

  const newcomers =
    entry.newcomers != null
      ? `<div class="tp-community__timeline-metric">
          <span class="tp-community__timeline-value">${escapeHtml(
            String(formatNumber(entry.newcomers, { maximumFractionDigits: 0 })),
          )}</span>
          <span class="tp-community__timeline-label">${escapeHtml(String(newcomersLabel))}</span>
        </div>`
      : '';

  const releases =
    entry.ships != null
      ? `<div class="tp-community__timeline-metric">
          <span class="tp-community__timeline-value">${escapeHtml(
            String(formatNumber(entry.ships, { maximumFractionDigits: 0 })),
          )}</span>
          <span class="tp-community__timeline-label">${escapeHtml(String(releasesLabel))}</span>
        </div>`
      : '';

  const highlights = entry.highlights.length
    ? `<ul class="tp-community__timeline-highlights" aria-label="${escapeHtml(String(highlightsLabel))}">
        ${entry.highlights
          .map((highlight) => `<li>${escapeHtml(String(highlight))}</li>`)
          .join('')}
      </ul>`
    : '';

  return `
    <li class="tp-community__timeline-entry">
      <div class="tp-community__timeline-period">${formatTimelineLabel(entry.period, translations)}</div>
      <div class="tp-community__timeline-grid">
        ${contributions}
        ${newcomers}
        ${releases}
      </div>
      ${highlights}
    </li>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderEngagementSection(community = {}, translations = {}) {
  const entries = buildEngagementEntries(community);
  if (entries.length === 0) {
    return '';
  }

  return `
    <section class="tp-card tp-community__engagement" aria-labelledby="tp-community-engagement">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-engagement">${escapeHtml(
          String(translations.title || 'Engagement timeline'),
        )}</h3>
        ${
          translations.subtitle
            ? `<p class="tp-text-subtle">${escapeHtml(String(translations.subtitle))}</p>`
            : ''
        }
      </header>
      <ol class="tp-community__timeline">
        ${entries.map((entry) => renderTimelineEntry(entry, translations)).join('')}
      </ol>
    </section>
  `;
}

/**
 * @param {CommunityHub | null | undefined} hub
 * @param {Record<string, unknown>} translations
 */
function renderHub(hub, translations = {}) {
  if (!hub) {
    return '';
  }
  const title = hub.region || hub.name || translations.fallbackTitle || 'Hub';
  const leads = coerceNumber(hub.leads ?? hub.maintainers, null);
  const focus = hub.focus || hub.specialty || '';
  const url = safeExternalUrl(hub.url || hub.href);
  const location = hub.location || '';
  const cta = translations.cta || 'View hub guide';

  return `
    <li class="tp-community__hub">
      <div class="tp-community__hub-header">
        <h4 class="tp-community__hub-title">${escapeHtml(String(title))}</h4>
        ${location ? `<span class="tp-community__hub-location">${escapeHtml(String(location))}</span>` : ''}
      </div>
      ${
        leads != null
          ? `<p class="tp-community__hub-leads">${escapeHtml(
              String(formatTemplate(translations.leads || '{count} regional leads', {
                count: formatNumber(leads, { maximumFractionDigits: 0 }),
              })),
            )}</p>`
          : ''
      }
      ${focus ? `<p class="tp-community__hub-focus">${escapeHtml(String(focus))}</p>` : ''}
      ${
        url === '#'
          ? ''
          : `<a class="tp-community__hub-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
              String(cta),
            )}</a>`
      }
    </li>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderHubsSection(community = {}, translations = {}) {
  const hubs = Array.isArray(community.hubs) ? community.hubs.filter(Boolean) : [];
  if (hubs.length === 0) {
    return '';
  }

  return `
    <section class="tp-card tp-community__hubs" aria-labelledby="tp-community-hubs">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-hubs">${escapeHtml(
          String(translations.title || 'Regional hubs'),
        )}</h3>
        ${
          translations.subtitle
            ? `<p class="tp-text-subtle">${escapeHtml(String(translations.subtitle))}</p>`
            : ''
        }
      </header>
      <ul class="tp-community__hub-list">
        ${hubs.map((hub) => renderHub(hub, translations)).join('')}
      </ul>
    </section>
  `;
}

/**
 * @param {CommunityOpportunity | null | undefined} opportunity
 * @param {Record<string, unknown>} translations
 */
function renderOpportunity(opportunity, translations = {}) {
  if (!opportunity) {
    return '';
  }
  const title = opportunity.title || opportunity.name || translations.fallbackTitle || 'Opportunity';
  const description = opportunity.description || opportunity.summary || '';
  const scope = opportunity.scope || opportunity.track || '';
  const url = safeExternalUrl(opportunity.url || opportunity.href);
  const cta = translations.cta || 'Express interest';

  return `
    <li class="tp-community__opportunity">
      <div class="tp-community__opportunity-copy">
        <h4 class="tp-community__opportunity-title">${escapeHtml(String(title))}</h4>
        ${scope ? `<p class="tp-community__opportunity-scope">${escapeHtml(String(scope))}</p>` : ''}
        ${
          description
            ? `<p class="tp-community__opportunity-description">${escapeHtml(String(description))}</p>`
            : ''
        }
      </div>
      ${
        url === '#'
          ? ''
          : `<a class="tp-community__opportunity-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
              String(cta),
            )}</a>`
      }
    </li>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderOpportunitiesSection(community = {}, translations = {}) {
  const opportunities = Array.isArray(community.opportunities)
    ? community.opportunities.filter(Boolean)
    : [];
  if (opportunities.length === 0) {
    return '';
  }

  return `
    <section class="tp-card tp-community__opportunities" aria-labelledby="tp-community-opportunities">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-opportunities">${escapeHtml(
          String(translations.title || 'Contribution opportunities'),
        )}</h3>
        ${
          translations.subtitle
            ? `<p class="tp-text-subtle">${escapeHtml(String(translations.subtitle))}</p>`
            : ''
        }
      </header>
      <ul class="tp-community__opportunity-list">
        ${opportunities.map((opportunity) => renderOpportunity(opportunity, translations)).join('')}
      </ul>
    </section>
  `;
}

function getTranslations() {
  const view = getMessage('views.community') || {};
  return {
    title: view.title || 'Community',
    heading: view.heading || 'Community Impact',
    subtitle: view.subtitle || '',
    hero: view.hero || {},
    metrics: view.metrics || {},
    engagement: view.engagement || {},
    hubs: view.hubs || {},
    programs: view.programs || {},
    events: view.events || {},
    opportunities: view.opportunities || {},
    resources: view.resources || {},
    champions: view.champions || {},
  };
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function buildMetrics(community = {}, translations = {}) {
  const metrics = community.metrics || {};
  const currencyCode = getLocaleConfig()?.defaultCurrency || 'USD';

  const maintainers = coerceNumber(metrics.maintainers ?? community.maintainers, null);
  const sponsors = coerceNumber(metrics.sponsors ?? community.sponsors?.total, null);
  const sponsorshipMonthly = coerceNumber(
    metrics.sponsorshipMonthly ?? community.sponsors?.monthly,
    null,
  );
  const downloads = coerceNumber(metrics.monthlyDownloads ?? metrics.downloadsMonthly, null);
  const responseHours = coerceNumber(
    metrics.responseHours ?? community.response_hours ?? community.responseHours,
    null,
  );
  const goodFirstIssues = coerceNumber(
    metrics.goodFirstIssues ?? community.good_first_issues ?? community.goodFirstIssues,
    null,
  );
  const mentorshipSeats = coerceNumber(
    metrics.mentorshipSeats ?? community.mentorship_seats ?? community.mentorshipSeats,
    null,
  );

  const metricConfigs = [
    {
      key: 'maintainers',
      value: maintainers,
      format: (value) => formatNumber(value, { maximumFractionDigits: 0 }),
      params: { count: maintainers != null ? formatNumber(maintainers, { maximumFractionDigits: 0 }) : '—' },
    },
    {
      key: 'sponsors',
      value: sponsors,
      format: (value) => formatNumber(value, { maximumFractionDigits: 0 }),
      params: {
        count: sponsors != null ? formatNumber(sponsors, { maximumFractionDigits: 0 }) : '—',
        monthly:
          Number.isFinite(sponsorshipMonthly)
            ? formatCurrency(sponsorshipMonthly, currencyCode)
            : '—',
      },
    },
    {
      key: 'downloads',
      value: downloads,
      format: (value) => formatNumber(value, { maximumFractionDigits: 0 }),
      params: {
        count: downloads != null ? formatNumber(downloads, { maximumFractionDigits: 0 }) : '—',
      },
    },
    {
      key: 'response',
      value: responseHours,
      format: (value) => `${formatNumber(value, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}h`,
      params: {
        hours:
          responseHours != null
            ? formatNumber(responseHours, { minimumFractionDigits: 1, maximumFractionDigits: 1 })
            : '—',
      },
    },
    {
      key: 'goodFirstIssues',
      value: goodFirstIssues,
      format: (value) => formatNumber(value, { maximumFractionDigits: 0 }),
      params: {
        count:
          goodFirstIssues != null ? formatNumber(goodFirstIssues, { maximumFractionDigits: 0 }) : '—',
      },
    },
    {
      key: 'mentorship',
      value: mentorshipSeats,
      format: (value) => formatNumber(value, { maximumFractionDigits: 0 }),
      params: {
        count:
          mentorshipSeats != null ? formatNumber(mentorshipSeats, { maximumFractionDigits: 0 }) : '—',
      },
    },
  ];

  return metricConfigs
    .map((config) => {
      const meta = translations[config.key] || {};
      if (config.value == null) {
        return null;
      }
      const value = config.format(config.value);
      const caption = formatTemplate(meta.hint || '', config.params);
      return {
        key: config.key,
        label: meta.label || config.key,
        value,
        caption,
      };
    })
    .filter(Boolean);
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderMetricsSection(community, translations = {}) {
  const metrics = buildMetrics(community, translations);
  if (metrics.length === 0) {
    return '';
  }

  return `
    <section class="tp-card tp-community__metrics" aria-labelledby="tp-community-metrics">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-metrics">${escapeHtml(
          String(translations.title || t('views.community.metrics.title')),
        )}</h3>
        <p class="tp-text-subtle">${escapeHtml(
          String(translations.subtitle || t('views.community.metrics.subtitle')),
        )}</p>
      </header>
      <ul class="tp-community__metrics-grid">
        ${metrics
          .map(
            (metric) => `
              <li class="tp-community__metric">
                <span class="tp-community__metric-label">${escapeHtml(String(metric.label))}</span>
                <span class="tp-community__metric-value">${escapeHtml(String(metric.value))}</span>
                ${
                  metric.caption
                    ? `<p class="tp-community__metric-caption">${escapeHtml(String(metric.caption))}</p>`
                    : ''
                }
              </li>
            `,
          )
          .join('')}
      </ul>
    </section>
  `;
}

/**
 * @param {CommunityProgram | null | undefined} program
 * @param {Record<string, unknown>} translations
 */
function renderProgram(program, translations = {}) {
  const title = program?.name || program?.title;
  const description = program?.description || program?.summary || '';
  const url = safeExternalUrl(program?.url || program?.href);
  const cta = program?.cta || translations.cta;

  return `
    <li class="tp-community__program">
      <div class="tp-community__program-copy">
        <h4 class="tp-community__program-title">${escapeHtml(String(title || translations.fallbackTitle || 'Program'))}</h4>
        ${
          description
            ? `<p class="tp-community__program-description">${escapeHtml(String(description))}</p>`
            : ''
        }
      </div>
      ${
        url === '#'
          ? ''
          : `<a class="tp-community__program-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
              String(cta || translations.cta || 'View details'),
            )}</a>`
      }
    </li>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderProgramsSection(community = {}, translations = {}) {
  const programs = Array.isArray(community.programs) ? community.programs.filter(Boolean) : [];
  if (programs.length === 0) {
    return '';
  }

  return `
    <section class="tp-card tp-community__programs" aria-labelledby="tp-community-programs">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-programs">${escapeHtml(
          String(translations.title || 'Contributor programs'),
        )}</h3>
        ${
          translations.subtitle
            ? `<p class="tp-text-subtle">${escapeHtml(String(translations.subtitle))}</p>`
            : ''
        }
      </header>
      <ul class="tp-community__programs-list">
        ${programs.map((program) => renderProgram(program, translations)).join('')}
      </ul>
    </section>
  `;
}

function formatEventDate(value) {
  if (!value) {
    return '—';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return escapeHtml(String(value));
  }
  return date.toISOString().split('T')[0];
}

/**
 * @param {CommunityEvent | null | undefined} event
 * @param {Record<string, unknown>} translations
 */
function renderEvent(event, translations = {}) {
  const url = safeExternalUrl(event?.url || event?.href);
  const title = event?.name || event?.title || translations.fallbackTitle || 'Event';
  const location = event?.location || event?.region;
  const date = formatEventDate(event?.date || event?.start);
  const type = event?.type;

  return `
    <li class="tp-community__event">
      <div class="tp-community__event-meta">
        <span class="tp-community__event-date">${escapeHtml(String(date))}</span>
        ${type ? `<span class="tp-community__event-type">${escapeHtml(String(type))}</span>` : ''}
      </div>
      <div class="tp-community__event-content">
        <h4 class="tp-community__event-title">${escapeHtml(String(title))}</h4>
        ${
          location
            ? `<p class="tp-community__event-location">${escapeHtml(String(location))}</p>`
            : ''
        }
        ${
          url === '#'
            ? ''
            : `<a class="tp-community__event-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
                String(translations.cta || 'Register'),
              )}</a>`
        }
      </div>
    </li>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderEventsSection(community = {}, translations = {}) {
  const events = Array.isArray(community.events) ? community.events.filter(Boolean) : [];
  if (events.length === 0) {
    return '';
  }

  return `
    <section class="tp-card tp-community__events" aria-labelledby="tp-community-events">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-events">${escapeHtml(
          String(translations.title || 'Community events'),
        )}</h3>
        ${
          translations.subtitle
            ? `<p class="tp-text-subtle">${escapeHtml(String(translations.subtitle))}</p>`
            : ''
        }
      </header>
      <ul class="tp-community__event-list">
        ${events.map((event) => renderEvent(event, translations)).join('')}
      </ul>
    </section>
  `;
}

/**
 * @param {CommunityResource[]} resources
 */
function buildResourceFilters(resources = []) {
  const categories = new Map();
  resources.forEach((resource) => {
    if (resource && typeof resource.category === 'string' && resource.category.trim() !== '') {
      const raw = resource.category.trim();
      const normalised = normaliseCategory(raw);
      if (normalised && !categories.has(normalised)) {
        categories.set(normalised, raw);
      }
    }
  });
  return Array.from(categories.entries()).map(([value, label]) => ({ value, label }));
}

/**
 * @param {Array<{ value: string; label: string }>} filters
 * @param {Record<string, unknown>} translations
 */
function renderResourceFilters(filters, translations = {}) {
  if (!filters.length) {
    return '';
  }
  const allLabel = translations.all || 'All';
  const helper = translations.helper || '';
  const buttons = [`
    <button type="button" class="tp-community__filter tp-community__filter--active" data-action="filter-resources" data-filter="all" aria-pressed="true">
      ${escapeHtml(String(allLabel))}
    </button>
  `]
    .concat(
      filters.map((filter) => `
        <button type="button" class="tp-community__filter" data-action="filter-resources" data-filter="${escapeHtml(
          filter.value,
        )}" aria-pressed="false">
          ${escapeHtml(String(filter.label))}
        </button>
      `),
    )
    .join('');

  return `
    <div class="tp-community__filters" data-role="resource-filters" data-target="tp-community-resources-list" data-default="all">
      <div class="tp-community__filters-toolbar" role="toolbar" aria-label="${escapeHtml(
        String(translations.label || 'Filter resources'),
      )}">
        ${buttons}
      </div>
      ${helper ? `<p class="tp-community__filters-helper">${escapeHtml(String(helper))}</p>` : ''}
    </div>
  `;
}

/**
 * @param {CommunityResource | null | undefined} resource
 * @param {Record<string, unknown>} translations
 */
function renderResource(resource, translations = {}) {
  const label = resource?.label || resource?.title || translations.fallbackTitle || 'Resource';
  const description = resource?.description || resource?.summary || '';
  const url = safeExternalUrl(resource?.url || resource?.href);
  const category = resource?.category ? normaliseCategory(resource.category) : '';

  return `
    <li class="tp-community__resource"${category ? ` data-category="${escapeHtml(category)}"` : ''}>
      <div class="tp-community__resource-copy">
        <h4 class="tp-community__resource-title">${escapeHtml(String(label))}</h4>
        ${
          description
            ? `<p class="tp-community__resource-description">${escapeHtml(String(description))}</p>`
            : ''
        }
      </div>
      ${
        url === '#'
          ? ''
          : `<a class="tp-community__resource-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
              String(translations.cta || 'Open'),
            )}</a>`
      }
    </li>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderResourcesSection(community = {}, translations = {}) {
  const resources = Array.isArray(community.resources) ? community.resources.filter(Boolean) : [];
  if (resources.length === 0) {
    return '';
  }

  const filters = buildResourceFilters(resources);
  const filterMarkup = renderResourceFilters(filters, translations.filters || {});

  return `
    <section class="tp-card tp-community__resources" aria-labelledby="tp-community-resources">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-resources">${escapeHtml(
          String(translations.title || 'Contributor resources'),
        )}</h3>
        ${
          translations.subtitle
            ? `<p class="tp-text-subtle">${escapeHtml(String(translations.subtitle))}</p>`
            : ''
        }
      </header>
      ${filterMarkup}
      <ul class="tp-community__resource-list" id="tp-community-resources-list">
        ${resources.map((resource) => renderResource(resource, translations)).join('')}
      </ul>
    </section>
  `;
}

/**
 * @param {CommunityChampion | null | undefined} champion
 * @param {Record<string, unknown>} translations
 */
function renderChampion(champion, translations = {}) {
  const name = champion?.name || champion?.handle || translations.fallbackTitle || 'Champion';
  const contributions = coerceNumber(champion?.contributions, null);
  const speciality = champion?.specialty || champion?.focus;
  const url = safeExternalUrl(champion?.url || champion?.profile);
  const contributionLabel = translations.contributions || '{count} contributions';
  const contributionsText = contributions != null
    ? formatTemplate(contributionLabel, {
        count: formatNumber(contributions, { maximumFractionDigits: 0 }),
      })
    : '';

  return `
    <li class="tp-community__champion">
      <div class="tp-community__champion-badge" aria-hidden="true">★</div>
      <div class="tp-community__champion-copy">
        <h4 class="tp-community__champion-name">${escapeHtml(String(name))}</h4>
        ${
          speciality
            ? `<p class="tp-community__champion-specialty">${escapeHtml(String(speciality))}</p>`
            : ''
        }
        ${
          contributionsText
            ? `<p class="tp-community__champion-contributions">${escapeHtml(String(contributionsText))}</p>`
            : ''
        }
      </div>
      ${
        url === '#'
          ? ''
          : `<a class="tp-community__champion-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(
              String(translations.cta || 'View profile'),
            )}</a>`
      }
    </li>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} translations
 */
function renderChampionsSection(community = {}, translations = {}) {
  const champions = Array.isArray(community.champions) ? community.champions.filter(Boolean) : [];
  if (champions.length === 0) {
    return '';
  }

  return `
    <section class="tp-card tp-community__champions" aria-labelledby="tp-community-champions">
      <header class="tp-card__header">
        <h3 class="tp-card__title" id="tp-community-champions">${escapeHtml(
          String(translations.title || 'Community champions'),
        )}</h3>
        ${
          translations.subtitle
            ? `<p class="tp-text-subtle">${escapeHtml(String(translations.subtitle))}</p>`
            : ''
        }
      </header>
      <ul class="tp-community__champion-list">
        ${champions.map((champion) => renderChampion(champion, translations)).join('')}
      </ul>
    </section>
  `;
}

/**
 * @param {CommunityProfile | null | undefined} community
 * @param {Record<string, unknown>} heroTranslations
 */
function renderChannels(community = {}, heroTranslations = {}) {
  const channels = Array.isArray(community.channels) ? community.channels.filter(Boolean) : [];
  if (channels.length === 0) {
    return '';
  }

  const items = channels
    .map((channel) => {
      const url = safeExternalUrl(channel?.url || channel?.href);
      const label = channel?.label || channel?.name || heroTranslations.fallbackChannel || 'Community channel';
      if (url === '#') {
        return '';
      }
      return `
        <a class="tp-community__hero-channel" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
          ${escapeHtml(String(label))}
        </a>
      `;
    })
    .filter(Boolean)
    .join('');

  if (!items) {
    return '';
  }

  return `
    <div class="tp-community__hero-channels" role="list">
      ${items}
    </div>
  `;
}

/**
 * @param {Record<string, unknown>} translations
 * @param {CommunityProfile} community
 * @param {GithubOverview} github
 */
function renderCommunityHero(translations = {}, community = {}, github = {}) {
  /** @type {CommunityProfile} */
  const profile = community || {};
  /** @type {GithubOverview} */
  const repository = github || {};
  const hero = translations.hero || {};
  const eyebrow = hero.eyebrow || t('views.community.hero.eyebrow');
  const title = hero.title || t('views.community.hero.title');
  const subtitle = hero.subtitle || t('views.community.hero.subtitle');
  const primaryUrl = safeExternalUrl(
    profile.primaryCta?.url || profile.primaryCTA?.url || profile.resources?.[0]?.url || repository.url,
  );
  const primaryLabel = profile.primaryCta?.label || profile.primaryCTA?.label || hero.cta || t('views.community.hero.cta');
  const secondaryLabel = hero.secondaryCta;
  const channels = renderChannels(profile, hero);

  const primaryAction =
    primaryUrl === '#'
      ? ''
      : `
          <a class="tp-community__hero-cta" href="${escapeHtml(primaryUrl)}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(String(primaryLabel || 'View contribution guide'))}
          </a>
        `;

  const secondaryChannel =
    typeof secondaryLabel === 'string' && profile.secondaryCta?.url
      ? safeExternalUrl(profile.secondaryCta.url)
      : '#';

  const secondaryAction =
    secondaryChannel === '#'
      ? ''
      : `
          <a class="tp-community__hero-secondary" href="${escapeHtml(secondaryChannel)}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(String(secondaryLabel))}
          </a>
        `;

  return `
    <section class="tp-community__hero">
      <div class="tp-community__hero-content">
        <p class="tp-community__hero-eyebrow">${escapeHtml(String(eyebrow))}</p>
        <h2 class="tp-community__hero-title">${escapeHtml(String(title))}</h2>
        <p class="tp-community__hero-subtitle">${escapeHtml(String(subtitle))}</p>
        <div class="tp-community__hero-actions">
          ${primaryAction}
          ${secondaryAction}
        </div>
        ${channels}
      </div>
      <div class="tp-community__hero-visual" aria-hidden="true">
        <div class="tp-community__hero-orb tp-community__hero-orb--primary"></div>
        <div class="tp-community__hero-orb tp-community__hero-orb--secondary"></div>
      </div>
    </section>
  `;
}

/**
 * @param {DashboardCommunityPayload | { community?: CommunityProfile | null; github?: GithubOverview | null }} [options]
 * @returns {{ html: string; community: CommunityProfile; github: GithubOverview }}
 */
export function renderCommunityView({ community = {}, github = {} } = {}) {
  /** @type {CommunityProfile} */
  const communityProfile = community ?? {};
  /** @type {GithubOverview} */
  const githubProfile = github ?? {};
  const translations = getTranslations();
  const hero = renderCommunityHero(translations, communityProfile, githubProfile);
  const metrics = renderMetricsSection(communityProfile, translations.metrics || {});
  const engagement = renderEngagementSection(communityProfile, translations.engagement || {});
  const hubs = renderHubsSection(communityProfile, translations.hubs || {});
  const programs = renderProgramsSection(communityProfile, translations.programs || {});
  const events = renderEventsSection(communityProfile, translations.events || {});
  const opportunities = renderOpportunitiesSection(communityProfile, translations.opportunities || {});
  const resources = renderResourcesSection(communityProfile, translations.resources || {});
  const champions = renderChampionsSection(communityProfile, translations.champions || {});

  const sections = [metrics, engagement, hubs, programs, opportunities, events, champions, resources]
    .filter(Boolean)
    .join('');

  return {
    html: `
      <article class="tp-view tp-view--community">
        <header class="tp-view__header">
          <h1 class="tp-view__title">${escapeHtml(String(translations.heading))}</h1>
          ${
            translations.subtitle
              ? `<p class="tp-view__subtitle">${escapeHtml(String(translations.subtitle))}</p>`
              : ''
          }
        </header>
        ${hero}
        <section class="tp-grid tp-grid--two tp-community__grid">
          ${sections}
        </section>
      </article>
    `,
    community: communityProfile,
    github: githubProfile,
  };
}

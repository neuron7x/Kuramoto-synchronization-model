/**
 * Canonical data interfaces exposed by the TradePulse dashboard API layer.
 * These definitions are consumed from JSDoc in the runtime `.js` modules so the
 * TypeScript compiler can type-check the integration points between the
 * rendered views and the backend payloads.
 */

import type { BarEvent, FillEvent, OrderEvent, SignalEvent, TickEvent } from '../types/events';

export interface OnboardingStep {
  id?: string;
  title?: string;
  description?: string;
  selector?: string | string[];
  selectors?: string[];
}

export interface OnboardingConfig {
  enabled?: boolean;
  storageKey?: string;
  steps?: OnboardingStep[];
}

export interface GithubPullRequestSummary {
  merged_30d?: number | string | null;
  merged?: number | string | null;
  open?: number | string | null;
  closed?: number | string | null;
  total?: number | string | null;
}

export interface GithubReleaseInfo {
  tag?: string;
  name?: string;
  version?: string;
  published_at?: string;
  publishedAt?: string;
  date?: string;
  url?: string;
  html_url?: string;
  notes?: string;
}

export interface GithubLanguageShare {
  name: string;
  share: number;
  color?: string | null;
  percent?: number;
  percentage?: number;
}

export interface GithubWorkflowBadge {
  name?: string;
  label?: string;
  badge: string;
  status_badge?: string;
  url?: string;
  html_url?: string;
  href?: string;
}

export interface GithubQualitySlo {
  coverage?: number | string | null;
  coverage_target?: number | string | null;
  uptime?: number | string | null;
  uptime_target?: number | string | null;
  [key: string]: unknown;
}

export interface GithubQualityMetrics {
  coverage?: number | string | null;
  coverage_ratio?: number | string | null;
  coverageRate?: number | string | null;
  coverage_target?: number | string | null;
  coverageTarget?: number | string | null;
  uptime?: number | string | null;
  uptime_90d?: number | string | null;
  uptimeRolling?: number | string | null;
  uptime_target?: number | string | null;
  uptimeTarget?: number | string | null;
  incidents_30d?: number | string | null;
  incidents?: number | string | null;
  mttr_hours?: number | string | null;
  mttr?: number | string | null;
  health_score?: number | string | null;
  health?: number | string | null;
  status?: string | null;
  last_audit?: string | null;
  lastAudit?: string | null;
  [key: string]: unknown;
}

export interface GithubQualityProfile {
  metrics?: GithubQualityMetrics | null;
  slo?: GithubQualitySlo | null;
  status?: string | null;
  last_audit?: string | null;
  lastAudit?: string | null;
  audit?: { completed_at?: string | null; notes?: string | null } | null;
  health_score?: number | string | null;
  incidents_30d?: number | string | null;
  mttr_hours?: number | string | null;
  [key: string]: unknown;
}

export interface CommunityMetrics {
  maintainers?: number | string | null;
  sponsors?: number | string | null;
  sponsorshipMonthly?: number | string | null;
  sponsorship_monthly?: number | string | null;
  monthlyDownloads?: number | string | null;
  downloadsMonthly?: number | string | null;
  responseHours?: number | string | null;
  response_hours?: number | string | null;
  goodFirstIssues?: number | string | null;
  good_first_issues?: number | string | null;
  mentorshipSeats?: number | string | null;
  mentorship_seats?: number | string | null;
}

export interface CommunityEngagementEntry {
  period?: string;
  month?: string;
  label?: string;
  date?: string;
  contributions?: number | string | null;
  total?: number | string | null;
  count?: number | string | null;
  newcomers?: number | string | null;
  newContributors?: number | string | null;
  releases?: number | string | null;
  majorReleases?: number | string | null;
  ships?: number | string | null;
  highlights?: string[];
  highlight?: string;
}

export interface CommunityProgram {
  name?: string;
  title?: string;
  description?: string;
  summary?: string;
  url?: string;
  href?: string;
  cta?: string;
}

export interface CommunityEvent {
  name?: string;
  title?: string;
  date?: string;
  start?: string;
  type?: string;
  location?: string;
  region?: string;
  url?: string;
  href?: string;
}

export interface CommunityResource {
  label?: string;
  title?: string;
  description?: string;
  summary?: string;
  url?: string;
  href?: string;
  category?: string;
}

export interface CommunityHub {
  region?: string;
  name?: string;
  leads?: number | string | null;
  maintainers?: number | string | null;
  focus?: string;
  specialty?: string;
  location?: string;
  url?: string;
  href?: string;
}

export interface CommunityOpportunity {
  title?: string;
  name?: string;
  description?: string;
  summary?: string;
  scope?: string;
  track?: string;
  url?: string;
  href?: string;
}

export interface CommunityChampion {
  name?: string;
  handle?: string;
  contributions?: number | string | null;
  specialty?: string;
  focus?: string;
  url?: string;
  profile?: string;
}

export interface CommunityChannel {
  label?: string;
  name?: string;
  url?: string;
  href?: string;
}

export interface CommunityCta {
  label?: string;
  url: string;
}

export interface CommunityProfile {
  metrics?: CommunityMetrics;
  engagement?: CommunityEngagementEntry[];
  timeline?: CommunityEngagementEntry[];
  milestones?: CommunityEngagementEntry[];
  programs?: CommunityProgram[];
  events?: CommunityEvent[];
  resources?: CommunityResource[];
  hubs?: CommunityHub[];
  opportunities?: CommunityOpportunity[];
  champions?: CommunityChampion[];
  channels?: CommunityChannel[];
  sponsors?: {
    total?: number | string | null;
    monthly?: number | string | null;
  } | null;
  primaryCta?: CommunityCta;
  primaryCTA?: CommunityCta;
  secondaryCta?: CommunityCta;
  secondaryCTA?: CommunityCta;
  good_first_issues?: number | string | null;
  goodFirstIssues?: number | string | null;
  mentorship_seats?: number | string | null;
  mentorshipSeats?: number | string | null;
  response_hours?: number | string | null;
  responseHours?: number | string | null;
  maintainers?: number | string | null;
  newcomers?: number | string | null;
  [key: string]: unknown;
}

export interface GithubOverview {
  organization?: string;
  owner?: string;
  repository?: string;
  repo?: string;
  url?: string;
  html_url?: string;
  stars?: number | string | null;
  stars_delta?: number | string | null;
  forks?: number | string | null;
  active_forks?: number | string | null;
  watchers?: number | string | null;
  watchers_growth?: number | string | null;
  contributors?: number | string | null;
  new_contributors_30d?: number | string | null;
  commits_30d?: number | string | null;
  merged_prs_30d?: number | string | null;
  open_prs?: number | string | null;
  prs?: GithubPullRequestSummary | null;
  last_release?: GithubReleaseInfo | null;
  release?: GithubReleaseInfo | null;
  releases?: GithubReleaseInfo[];
  languages?: GithubLanguageShare[];
  workflows?: GithubWorkflowBadge[];
  badges?: GithubWorkflowBadge[];
  quality?: GithubQualityProfile | GithubQualityMetrics | null;
  community?: CommunityProfile | null;
  programs?: CommunityProgram[];
  resources?: CommunityResource[];
  momentum?: {
    velocity?: number | string | null;
    engagement?: number | string | null;
    contributors?: number | string | null;
    [key: string]: unknown;
  } | null;
  [key: string]: unknown;
}

export interface PnlPoint {
  timestamp: number;
  value: number;
}

export interface QuotePoint {
  timestamp: number;
  value: number;
  label?: string;
}

export type PnlDatum = PnlPoint | BarEvent;
export type QuoteDatum = QuotePoint | TickEvent;

export interface DashboardOverviewPayload {
  github?: GithubOverview | null;
}

export interface DashboardCommunityPayload {
  community?: CommunityProfile | null;
  github?: GithubOverview | null;
}

export interface DashboardMonitoringControls {
  killSwitch?: {
    enabled?: boolean | number | string | null;
    state?: string | null;
    status?: string | null;
    changedAt?: number | string | null;
    updatedAt?: number | string | null;
    changedBy?: string | null;
    actor?: string | null;
    reason?: string | null;
  } | null;
  circuitBreaker?: {
    state?: string | null;
    status?: string | null;
    triggeredAt?: number | string | null;
    lastTripAt?: number | string | null;
    reason?: string | null;
    lastReason?: string | null;
    cooldownSeconds?: number | string | null;
    cooldown?: number | string | null;
  } | null;
}

export interface DashboardMonitoringMetrics {
  grossExposure?: {
    value?: number | string | null;
    limit?: number | string | null;
    change?: number | string | null;
  } | null;
  drawdown?: {
    value?: number | string | null;
    limit?: number | string | null;
    mode?: string | null;
  } | null;
  openOrders?: {
    value?: number | string | null;
    limit?: number | string | null;
  } | null;
  rejectionRate?: {
    value?: number | string | null;
    threshold?: number | string | null;
    window?: string | null;
  } | null;
  circuitTrips?: {
    value?: number | string | null;
    threshold?: number | string | null;
    window?: string | null;
  } | null;
}

export interface DashboardMonitoringSeriesPoint {
  timestamp: number | string;
  value: number | string;
  label?: string | null;
}

export interface DashboardMonitoringAlert {
  id?: string | null;
  severity?: string | null;
  message?: string | null;
  timestamp?: number | string | null;
}

export interface DashboardMonitoringPayload {
  environment?: string | null;
  currency?: string | null;
  controls?: DashboardMonitoringControls | null;
  metrics?: DashboardMonitoringMetrics | null;
  timeSeries?: {
    exposure?: DashboardMonitoringSeriesPoint[] | null;
    drawdown?: DashboardMonitoringSeriesPoint[] | null;
  } | null;
  alerts?: DashboardMonitoringAlert[] | null;
}

export interface DashboardData {
  route?: string;
  overview?: DashboardOverviewPayload;
  monitoring?: DashboardMonitoringPayload;
  positions?: {
    fills?: FillEvent[];
    orders?: OrderEvent[];
    ticks?: TickEvent[];
  };
  orders?: {
    orders?: OrderEvent[];
    fills?: FillEvent[];
  };
  pnl?: {
    pnlPoints?: PnlDatum[];
    quotes?: QuoteDatum[];
    currency?: string;
  };
  signals?: {
    signals?: SignalEvent[];
  };
  community?: DashboardCommunityPayload;
  header?: {
    title?: string;
    subtitle?: string;
    tags?: string[];
  };
  onboarding?: OnboardingConfig | null;
}

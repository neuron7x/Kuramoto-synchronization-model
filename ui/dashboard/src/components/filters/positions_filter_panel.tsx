/**
 * Positions Filter Panel
 * Multi-selector filters for position analytics
 */

import { escapeHtml } from '../../core/formatters.js';

export interface FilterOption {
  value: string;
  label: string;
  count?: number;
}

export interface FilterConfig {
  symbol?: FilterOption[];
  exchange?: FilterOption[];
  strategy?: FilterOption[];
}

export interface FilterValues {
  symbol: string[];
  exchange: string[];
  strategy: string[];
}

export interface Position {
  id: string;
  symbol: string;
  exchange: string;
  strategy: string;
  exposure?: number;
  pnl?: number;
  unrealizedPnl?: number;
  realizedPnl?: number;
  [key: string]: unknown;
}

export interface PositionTotals {
  count: number;
  netExposure: number;
  netPnl: number;
  unrealizedPnl: number;
  realizedPnl: number;
}

export interface PositionGroup extends PositionTotals {
  key: string;
  positions: Position[];
}

export interface AggregatedPositions {
  positions: Position[];
  totals: PositionTotals;
  groups: PositionGroup[] | null;
}

export interface QuickPreset {
  id: string;
  label: string;
  filters: Partial<FilterValues>;
}

const DEFAULT_PRESETS: QuickPreset[] = [
  {
    id: 'all',
    label: 'All Positions',
    filters: {},
  },
  {
    id: 'profitable',
    label: 'Profitable Only',
    filters: {},
  },
  {
    id: 'losing',
    label: 'Losing Only',
    filters: {},
  },
  {
    id: 'high-exposure',
    label: 'High Exposure',
    filters: {},
  },
];

export function renderPositionsFilterPanel(
  config: FilterConfig,
  currentFilters: FilterValues,
  presets: QuickPreset[] = DEFAULT_PRESETS
): string {
  const renderCheckbox = (type: keyof FilterValues, option: FilterOption): string => {
    const isChecked = currentFilters[type].includes(option.value);
    const countBadge = option.count !== undefined ? ` <span class="tp-filter__count">(${option.count})</span>` : '';
    
    return `
      <label class="tp-filter__option">
        <input
          type="checkbox"
          class="tp-filter__checkbox"
          name="${escapeHtml(type)}"
          value="${escapeHtml(option.value)}"
          ${isChecked ? 'checked' : ''}
          data-filter-type="${escapeHtml(type)}"
        />
        <span class="tp-filter__label">${escapeHtml(option.label)}${countBadge}</span>
      </label>
    `;
  };

  const renderFilterGroup = (
    type: keyof FilterValues,
    label: string,
    options: FilterOption[]
  ): string => {
    if (!options || options.length === 0) {
      return '';
    }

    const optionsHtml = options.map((opt) => renderCheckbox(type, opt)).join('');
    const selectedCount = currentFilters[type].length;
    const badge = selectedCount > 0 ? ` <span class="tp-filter__badge">${selectedCount}</span>` : '';

    return `
      <div class="tp-filter__group" data-filter-group="${escapeHtml(type)}">
        <div class="tp-filter__group-header">
          <h3 class="tp-filter__group-title">${escapeHtml(label)}${badge}</h3>
          ${selectedCount > 0 ? `<button type="button" class="tp-filter__clear" data-clear="${escapeHtml(type)}">Clear</button>` : ''}
        </div>
        <div class="tp-filter__options">
          ${optionsHtml}
        </div>
      </div>
    `;
  };

  const presetsHtml = presets
    .map((preset) => {
      const isActive = false; // TODO: implement active preset detection
      return `
        <button
          type="button"
          class="tp-filter__preset${isActive ? ' tp-filter__preset--active' : ''}"
          data-preset="${escapeHtml(preset.id)}"
        >
          ${escapeHtml(preset.label)}
        </button>
      `;
    })
    .join('');

  const symbolGroup = config.symbol ? renderFilterGroup('symbol', 'Symbol', config.symbol) : '';
  const exchangeGroup = config.exchange ? renderFilterGroup('exchange', 'Exchange', config.exchange) : '';
  const strategyGroup = config.strategy ? renderFilterGroup('strategy', 'Strategy', config.strategy) : '';

  const hasActiveFilters = currentFilters.symbol.length > 0 || currentFilters.exchange.length > 0 || currentFilters.strategy.length > 0;

  return `
    <aside class="tp-filter-panel" data-role="positions-filter-panel" role="complementary" aria-label="Position filters">
      <div class="tp-filter-panel__header">
        <h2 class="tp-filter-panel__title">Filters</h2>
        ${hasActiveFilters ? '<button type="button" class="tp-filter-panel__reset" data-action="reset-filters">Reset All</button>' : ''}
      </div>

      ${presets.length > 0 ? `
        <div class="tp-filter-panel__presets" data-role="quick-presets">
          <h3 class="tp-filter-panel__presets-title">Quick Presets</h3>
          <div class="tp-filter-panel__presets-list">
            ${presetsHtml}
          </div>
        </div>
      ` : ''}

      <div class="tp-filter-panel__groups">
        ${symbolGroup}
        ${exchangeGroup}
        ${strategyGroup}
      </div>

      <div class="tp-filter-panel__actions">
        <button type="button" class="tp-filter-panel__apply" data-action="apply-filters">
          Apply Filters
        </button>
      </div>
    </aside>
  `;
}

export function extractFilterValues(formData: FormData | HTMLFormElement): FilterValues {
  const data = formData instanceof HTMLFormElement ? new FormData(formData) : formData;
  
  return {
    symbol: data.getAll('symbol').map(String),
    exchange: data.getAll('exchange').map(String),
    strategy: data.getAll('strategy').map(String),
  };
}

export function aggregatePositions(
  positions: Position[],
  filters: FilterValues,
  groupBy: 'symbol' | 'exchange' | 'strategy' | null = null
): AggregatedPositions {
  // Filter positions
  const filtered = positions.filter((pos) => {
    if (filters.symbol.length > 0 && !filters.symbol.includes(pos.symbol)) {
      return false;
    }
    if (filters.exchange.length > 0 && !filters.exchange.includes(pos.exchange)) {
      return false;
    }
    if (filters.strategy.length > 0 && !filters.strategy.includes(pos.strategy)) {
      return false;
    }
    return true;
  });

  // Calculate totals
  const totals = filtered.reduce(
    (acc, pos) => {
      acc.count += 1;
      acc.netExposure += pos.exposure || 0;
      acc.netPnl += pos.pnl || 0;
      acc.unrealizedPnl += pos.unrealizedPnl || 0;
      acc.realizedPnl += pos.realizedPnl || 0;
      return acc;
    },
    {
      count: 0,
      netExposure: 0,
      netPnl: 0,
      unrealizedPnl: 0,
      realizedPnl: 0,
    }
  );

  if (!groupBy) {
    return {
      positions: filtered,
      totals,
      groups: null,
    };
  }

  // Group positions
  const groups = filtered.reduce((acc: Record<string, PositionGroup>, pos: Position) => {
    const key = pos[groupBy] || 'unknown';
    if (!acc[key]) {
      acc[key] = {
        key,
        positions: [],
        count: 0,
        netExposure: 0,
        netPnl: 0,
        unrealizedPnl: 0,
        realizedPnl: 0,
      };
    }
    acc[key].positions.push(pos);
    acc[key].count += 1;
    acc[key].netExposure += pos.exposure || 0;
    acc[key].netPnl += pos.pnl || 0;
    acc[key].unrealizedPnl += pos.unrealizedPnl || 0;
    acc[key].realizedPnl += pos.realizedPnl || 0;
    return acc;
  }, {} as Record<string, PositionGroup>);

  return {
    positions: filtered,
    totals,
    groups: Object.values(groups),
  };
}

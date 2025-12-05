import { escapeHtml } from '../core/formatters.js';

const DEFAULT_PAGE_SIZE = 10;
const SORT_DIRECTIONS = new Set(['asc', 'desc']);
const VIEWPORT_LABEL = 'Scrollable table viewport. Use arrow keys to pan horizontally.';

function normaliseDirection(direction = 'desc') {
  const lower = String(direction).toLowerCase();
  return SORT_DIRECTIONS.has(lower) ? lower : 'desc';
}

function clampPage(page, pageCount) {
  if (!Number.isFinite(page) || page < 1) {
    return 1;
  }
  if (page > pageCount) {
    return pageCount;
  }
  return page;
}

function buildSummaryId(columns) {
  const base = columns
    .map((column) => column.id)
    .filter((id) => typeof id === 'string' && id.trim().length > 0)
    .join('-');
  const safeBase = base || 'table';
  return `tp-live-table-summary-${safeBase.replace(/[^a-z0-9_-]/gi, '-').toLowerCase()}`;
}

export class LiveTable {
  constructor({ columns = [], rows = [], sortBy, sortDirection = 'desc', pageSize = DEFAULT_PAGE_SIZE } = {}) {
    if (!Array.isArray(columns) || columns.length === 0) {
      throw new Error('LiveTable requires at least one column definition');
    }
    this.columns = columns.map((column) => ({
      id: column.id,
      label: column.label,
      accessor: typeof column.accessor === 'function' ? column.accessor : (row) => row[column.id],
      formatter: column.formatter,
      align: column.align || 'left',
      sortValue: column.sortValue,
    }));
    this.rows = Array.isArray(rows) ? rows.slice() : [];
    this.sortBy = sortBy || this.columns[0].id;
    this.sortDirection = normaliseDirection(sortDirection);
    this.pageSize = Number.isFinite(pageSize) && pageSize > 0 ? Math.floor(pageSize) : DEFAULT_PAGE_SIZE;
    this.page = 1;
  }

  setRows(rows = []) {
    this.rows = Array.isArray(rows) ? rows.slice() : [];
    return this;
  }

  setSort(columnId, direction = this.sortDirection) {
    if (!this.columns.find((column) => column.id === columnId)) {
      throw new Error(`Unknown column: ${columnId}`);
    }
    this.sortBy = columnId;
    this.sortDirection = normaliseDirection(direction);
    return this;
  }

  setPage(page) {
    this.page = Number.isFinite(page) ? Math.max(1, Math.floor(page)) : 1;
    return this;
  }

  setPageSize(size) {
    if (!Number.isFinite(size) || size <= 0) {
      throw new Error('Page size must be a positive number');
    }
    this.pageSize = Math.floor(size);
    return this;
  }

  getSortedRows() {
    const column = this.columns.find((col) => col.id === this.sortBy) || this.columns[0];
    const rows = this.rows.slice();
    const directionMultiplier = this.sortDirection === 'asc' ? 1 : -1;
    const accessor = column.accessor;
    const sortValue = column.sortValue;
    return rows.sort((a, b) => {
      const aValue = sortValue ? sortValue(a) : accessor(a);
      const bValue = sortValue ? sortValue(b) : accessor(b);
      if (aValue === bValue) {
        return 0;
      }
      if (aValue === undefined || aValue === null) {
        return 1 * directionMultiplier;
      }
      if (bValue === undefined || bValue === null) {
        return -1 * directionMultiplier;
      }
      if (typeof aValue === 'number' && typeof bValue === 'number') {
        return (aValue - bValue) * directionMultiplier;
      }
      return String(aValue).localeCompare(String(bValue)) * directionMultiplier;
    });
  }

  renderRow(row) {
    const cells = this.columns
      .map((column) => {
        const rawValue = column.accessor(row);
        const display = column.formatter ? column.formatter(rawValue, row) : escapeHtml(rawValue ?? '—');
        return `<td class="tp-live-table__cell tp-live-table__cell--${column.align}">${display}</td>`;
      })
      .join('');
    return `<tr class="tp-live-table__row">${cells}</tr>`;
  }

  render(page = this.page) {
    const sortedRows = this.getSortedRows();
    const pageCount = Math.max(Math.ceil(sortedRows.length / this.pageSize), 1);
    const currentPage = clampPage(page, pageCount);
    const start = (currentPage - 1) * this.pageSize;
    const end = start + this.pageSize;
    const pageRows = sortedRows.slice(start, end);

    const body = pageRows.length
      ? pageRows.map((row) => this.renderRow(row)).join('')
      : `<tr class="tp-live-table__row tp-live-table__row--empty"><td class="tp-live-table__cell tp-live-table__cell--empty" colspan="${this.columns.length}">No data available. Data will appear here when trading activity begins.</td></tr>`;

    const header = this.columns
      .map((column) => {
        const isActive = column.id === this.sortBy;
        const indicator = isActive ? `<span class="tp-live-table__sort" aria-label="Sorted ${this.sortDirection === 'asc' ? 'ascending' : 'descending'}">${this.sortDirection === 'asc' ? '▲' : '▼'}</span>` : '';
        return `<th class="tp-live-table__header tp-live-table__cell--${column.align}" scope="col" data-column="${escapeHtml(column.id)}" aria-sort="${isActive ? (this.sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}">${escapeHtml(column.label)}${indicator}</th>`;
      })
      .join('');

    const summaryId = buildSummaryId(this.columns);
    const activeColumn = this.columns.find((column) => column.id === this.sortBy) || this.columns[0];
    const directionLabel = this.sortDirection === 'asc' ? 'ascending' : 'descending';
    const summaryText = `Sorted by ${escapeHtml(activeColumn.label)} (${directionLabel}). Total rows ${sortedRows.length}. Page ${currentPage} of ${pageCount}.`;

    const html = `
      <div class="tp-live-table" role="region" aria-live="polite">
        <div
          class="tp-live-table__viewport"
          role="group"
          tabindex="0"
          aria-label="${VIEWPORT_LABEL}"
        >
          <table class="tp-live-table__table" role="table" aria-describedby="${summaryId}">
            <thead class="tp-live-table__head">
              <tr class="tp-live-table__row">${header}</tr>
            </thead>
            <tbody class="tp-live-table__body">${body}</tbody>
          </table>
        </div>
        <footer class="tp-live-table__footer">
          <span class="tp-live-table__footer-item">Page ${currentPage} of ${pageCount}</span>
          <span class="tp-live-table__footer-item">Rows ${sortedRows.length}</span>
          <p id="${summaryId}" class="tp-live-table__summary" aria-live="polite">${summaryText}</p>
        </footer>
      </div>
    `;

    return {
      html,
      page: currentPage,
      pageCount,
      totalRows: sortedRows.length,
      pageSize: this.pageSize,
    };
  }
}

export function createLiveTable(config) {
  return new LiveTable(config);
}

/**
 * LiveTable Controller
 * Manages real-time table updates with WebSocket/SSE integration
 */

import type { DataSource } from '../core/data_source.js';

export interface TableRow {
  id: string;
  [key: string]: unknown;
}

export interface UpdateMetrics {
  latency: number;
  queueSize: number;
  updatesPerSecond: number;
}

export interface LiveTableConfig {
  dataSource: DataSource;
  channel: string;
  debounceMs?: number;
  maxQueueSize?: number;
  onUpdate?: (rows: TableRow[]) => void;
  onMetrics?: (metrics: UpdateMetrics) => void;
  onError?: (error: Error) => void;
}

export class LiveTableController {
  private dataSource: DataSource;
  private channel: string;
  private debounceMs: number;
  private maxQueueSize: number;
  private rows: Map<string, TableRow>;
  private updateQueue: TableRow[];
  private debounceTimer: ReturnType<typeof setTimeout> | null;
  private isPaused: boolean;
  private unsubscribe: (() => void) | null;
  private onUpdate?: (rows: TableRow[]) => void;
  private onMetrics?: (metrics: UpdateMetrics) => void;
  private onError?: (error: Error) => void;
  private metricsTimer: ReturnType<typeof setInterval> | null;
  private updateCount: number;
  private lastUpdateTime: number;

  constructor(config: LiveTableConfig) {
    this.dataSource = config.dataSource;
    this.channel = config.channel;
    this.debounceMs = config.debounceMs || 100;
    this.maxQueueSize = config.maxQueueSize || 1000;
    this.rows = new Map();
    this.updateQueue = [];
    this.debounceTimer = null;
    this.isPaused = false;
    this.unsubscribe = null;
    this.onUpdate = config.onUpdate;
    this.onMetrics = config.onMetrics;
    this.onError = config.onError;
    this.metricsTimer = null;
    this.updateCount = 0;
    this.lastUpdateTime = Date.now();
  }

  /**
   * Start streaming updates
   */
  start(): void {
    if (this.unsubscribe) {
      return;
    }

    const streamMethod = this.getStreamMethod();
    this.unsubscribe = streamMethod((data: unknown) => {
      this.handleUpdate(data as TableRow);
    });

    // Start metrics collection
    this.startMetricsCollection();
  }

  /**
   * Stop streaming updates
   */
  stop(): void {
    if (this.unsubscribe) {
      this.unsubscribe();
      this.unsubscribe = null;
    }

    if (this.debounceTimer) {
      clearTimeout(this.debounceTimer);
      this.debounceTimer = null;
    }

    this.stopMetricsCollection();
  }

  /**
   * Pause updates (keep receiving but don't process)
   */
  pause(): void {
    this.isPaused = true;
  }

  /**
   * Resume updates
   */
  resume(): void {
    this.isPaused = false;
    if (this.updateQueue.length > 0) {
      this.flushQueue();
    }
  }

  /**
   * Check if updates are paused
   */
  isPausedState(): boolean {
    return this.isPaused;
  }

  /**
   * Get current queue size
   */
  getQueueSize(): number {
    return this.updateQueue.length;
  }

  /**
   * Get all rows
   */
  getRows(): TableRow[] {
    return Array.from(this.rows.values());
  }

  /**
   * Append new rows
   */
  appendRows(newRows: TableRow[]): void {
    newRows.forEach((row) => {
      if (row.id) {
        this.rows.set(row.id, { ...row, _updated: Date.now() });
      }
    });
    this.notifyUpdate();
  }

  /**
   * Replace a single row
   */
  replaceRow(id: string, row: TableRow): void {
    if (this.rows.has(id)) {
      this.rows.set(id, { ...row, id, _updated: Date.now() });
      this.notifyUpdate();
    }
  }

  /**
   * Mark row as updated
   */
  markUpdated(id: string): void {
    const row = this.rows.get(id);
    if (row) {
      this.rows.set(id, { ...row, _updated: Date.now() });
    }
  }

  /**
   * Remove row
   */
  removeRow(id: string): void {
    if (this.rows.delete(id)) {
      this.notifyUpdate();
    }
  }

  /**
   * Clear all rows
   */
  clear(): void {
    this.rows.clear();
    this.updateQueue = [];
    this.notifyUpdate();
  }

  /**
   * Handle incoming update
   */
  private handleUpdate(data: TableRow): void {
    this.updateCount++;

    if (this.isPaused) {
      this.updateQueue.push(data);
      
      // Prevent queue overflow
      if (this.updateQueue.length > this.maxQueueSize) {
        this.updateQueue.shift();
      }
      return;
    }

    // Process update immediately or queue for debouncing
    this.updateQueue.push(data);
    this.scheduleFlush();
  }

  /**
   * Schedule queue flush with debouncing
   */
  private scheduleFlush(): void {
    if (this.debounceTimer) {
      return;
    }

    this.debounceTimer = setTimeout(() => {
      this.flushQueue();
      this.debounceTimer = null;
    }, this.debounceMs);
  }

  /**
   * Flush update queue
   */
  private flushQueue(): void {
    if (this.updateQueue.length === 0) {
      return;
    }

    const batch = this.updateQueue.splice(0);

    try {
      batch.forEach((row) => {
        if (row.id) {
          this.rows.set(row.id, { ...row, _updated: Date.now() });
        }
      });

      this.notifyUpdate();
    } catch (error) {
      if (this.onError) {
        this.onError(error as Error);
      }
    }
  }

  /**
   * Notify subscribers of update
   */
  private notifyUpdate(): void {
    if (this.onUpdate) {
      try {
        this.onUpdate(this.getRows());
      } catch (error) {
        if (this.onError) {
          this.onError(error as Error);
        }
      }
    }
  }

  /**
   * Get appropriate stream method based on channel
   */
  private getStreamMethod(): (handler: (data: unknown) => void) => () => void {
    switch (this.channel) {
      case 'orders':
        return this.dataSource.streamOrders.bind(this.dataSource);
      case 'positions':
        return this.dataSource.streamPositions.bind(this.dataSource);
      case 'signals':
        return this.dataSource.streamSignals.bind(this.dataSource);
      default:
        throw new Error(`Unknown channel: ${this.channel}`);
    }
  }

  /**
   * Start metrics collection
   */
  private startMetricsCollection(): void {
    if (this.metricsTimer) {
      return;
    }

    this.metricsTimer = setInterval(() => {
      this.collectMetrics();
    }, 1000);
  }

  /**
   * Stop metrics collection
   */
  private stopMetricsCollection(): void {
    if (this.metricsTimer) {
      clearInterval(this.metricsTimer);
      this.metricsTimer = null;
    }
  }

  /**
   * Collect and emit metrics
   */
  private collectMetrics(): void {
    const now = Date.now();
    const elapsed = (now - this.lastUpdateTime) / 1000;
    const updatesPerSecond = elapsed > 0 ? this.updateCount / elapsed : 0;

    const metrics: UpdateMetrics = {
      latency: this.debounceMs,
      queueSize: this.updateQueue.length,
      updatesPerSecond: Math.round(updatesPerSecond * 100) / 100,
    };

    if (this.onMetrics) {
      this.onMetrics(metrics);
    }

    // Reset counters
    this.updateCount = 0;
    this.lastUpdateTime = now;
  }
}

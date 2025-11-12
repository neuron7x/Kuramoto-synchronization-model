/**
 * Example: Using TradePulse Dashboard with async data loading
 * 
 * This example demonstrates how to use the dashboard with progressive
 * enhancement and live backend integration.
 */

import { renderDashboard } from '../src/core/index.js';

/**
 * Example 1: Basic async dashboard with default configuration
 * 
 * This will:
 * - Render the dashboard shell with empty data
 * - Initialize progressive enhancement to load data from backend
 * - Connect to WebSocket for real-time updates
 */
export function renderAsyncDashboard() {
  return renderDashboard({
    route: 'overview',
    asyncMode: true, // Enable async data loading
    enableWebSocket: true, // Enable WebSocket for real-time updates
  });
}

/**
 * Example 2: Async dashboard with custom API endpoints
 * 
 * Use this when your API is hosted on a different domain or port
 */
export function renderAsyncDashboardWithCustomApi() {
  return renderDashboard({
    route: 'overview',
    asyncMode: true,
    enableWebSocket: true,
    apiBaseUrl: 'https://api.tradepulse.example.com/v1',
    apiWsUrl: 'wss://api.tradepulse.example.com/v1/ws',
  });
}

/**
 * Example 3: Hybrid mode - SSR with progressive enhancement
 * 
 * This combines server-side rendering with client-side updates:
 * - Initial render uses provided data (fast first paint)
 * - Progressive enhancement loads fresh data in background
 * - WebSocket provides real-time updates
 */
export function renderHybridDashboard(initialData = {}) {
  return renderDashboard({
    route: 'overview',
    // Provide initial SSR data
    overview: initialData.overview || {},
    positions: initialData.positions || {},
    orders: initialData.orders || {},
    pnl: initialData.pnl || {},
    // Enable async mode to refresh data
    asyncMode: false, // Use initial data for first render
    enableWebSocket: true, // But enable WebSocket for updates
  });
}

/**
 * Example 4: Async dashboard without WebSocket (REST-only)
 * 
 * Use this in environments where WebSocket is not available
 * or when you only want periodic polling
 */
export function renderRestOnlyDashboard() {
  return renderDashboard({
    route: 'overview',
    asyncMode: true,
    enableWebSocket: false, // Disable WebSocket
  });
}

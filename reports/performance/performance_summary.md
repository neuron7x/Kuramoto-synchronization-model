# Performance Test Results
Generated: 2025-12-07 15:25:34 UTC

## Summary
- **total_runs**: 9
- **passed**: 2
- **failed**: 7
- **git_commit**: ec92e2e6
- **git_branch**: copilot/perform-technical-audit

## Test Runs

### regime_transitions_4phases
- **Exchange**: synthetic
- **Symbol**: BTCUSD
- **Ticks**: 300

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 44.84ms | 60.00ms | ✅ |
| Latency (p95) | 69.03ms | 100.00ms | ✅ |
| Latency (max) | 83.83ms | 200.00ms | ✅ |
| Throughput | 10.74 tps | 5.00 tps | ✅ |
| Slippage (median) | 6.12bps | 5.00bps | ❌ |
| Slippage (p95) | 7.99bps | 15.00bps | ✅ |

#### ⚠️ Regression Violations
- Slippage median 6.12bps exceeds budget 5.00bps

### flash_crash_5pct_mid
- **Exchange**: synthetic
- **Symbol**: BTCUSD
- **Ticks**: 100

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 44.17ms | 60.00ms | ✅ |
| Latency (p95) | 70.92ms | 100.00ms | ✅ |
| Latency (max) | 88.71ms | 200.00ms | ✅ |
| Throughput | 9.97 tps | 5.00 tps | ✅ |
| Slippage (median) | 5.00bps | 5.00bps | ❌ |
| Slippage (p95) | 15.00bps | 15.00bps | ✅ |

#### ⚠️ Regression Violations
- Slippage median 5.00bps exceeds budget 5.00bps

### coinbase_btcusd
- **Exchange**: coinbase
- **Symbol**: BTC-USD
- **Ticks**: 10

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 44.57ms | 60.00ms | ✅ |
| Latency (p95) | 45.57ms | 100.00ms | ✅ |
| Latency (max) | 45.65ms | 200.00ms | ✅ |
| Throughput | 11.11 tps | 5.00 tps | ✅ |
| Slippage (median) | 0.06bps | 5.00bps | ✅ |
| Slippage (p95) | 0.07bps | 15.00bps | ✅ |

### stable_btcusd_100ticks
- **Exchange**: synthetic
- **Symbol**: BTCUSD
- **Ticks**: 100

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 46.06ms | 60.00ms | ✅ |
| Latency (p95) | 70.86ms | 100.00ms | ✅ |
| Latency (max) | 88.58ms | 200.00ms | ✅ |
| Throughput | 10.34 tps | 5.00 tps | ✅ |
| Slippage (median) | 5.83bps | 5.00bps | ❌ |
| Slippage (p95) | 8.19bps | 15.00bps | ✅ |

#### ⚠️ Regression Violations
- Slippage median 5.83bps exceeds budget 5.00bps

### flash_crash_10pct_early
- **Exchange**: synthetic
- **Symbol**: BTCUSD
- **Ticks**: 150

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 45.82ms | 60.00ms | ✅ |
| Latency (p95) | 67.88ms | 100.00ms | ✅ |
| Latency (max) | 81.64ms | 200.00ms | ✅ |
| Throughput | 9.64 tps | 5.00 tps | ✅ |
| Slippage (median) | 5.00bps | 5.00bps | ✅ |
| Slippage (p95) | 15.00bps | 15.00bps | ✅ |

### trending_down_btcusd_200ticks
- **Exchange**: synthetic
- **Symbol**: BTCUSD
- **Ticks**: 200

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 46.53ms | 60.00ms | ✅ |
| Latency (p95) | 71.61ms | 100.00ms | ✅ |
| Latency (max) | 82.58ms | 200.00ms | ✅ |
| Throughput | 10.31 tps | 5.00 tps | ✅ |
| Slippage (median) | 5.84bps | 5.00bps | ❌ |
| Slippage (p95) | 7.88bps | 15.00bps | ✅ |

#### ⚠️ Regression Violations
- Slippage median 5.84bps exceeds budget 5.00bps

### volatile_btcusd_150ticks
- **Exchange**: synthetic
- **Symbol**: BTCUSD
- **Ticks**: 150

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 44.31ms | 60.00ms | ✅ |
| Latency (p95) | 70.10ms | 100.00ms | ✅ |
| Latency (max) | 88.79ms | 200.00ms | ✅ |
| Throughput | 12.45 tps | 5.00 tps | ✅ |
| Slippage (median) | 6.14bps | 5.00bps | ❌ |
| Slippage (p95) | 8.15bps | 15.00bps | ✅ |

#### ⚠️ Regression Violations
- Slippage median 6.14bps exceeds budget 5.00bps

### mean_reverting_btcusd_250ticks
- **Exchange**: synthetic
- **Symbol**: BTCUSD
- **Ticks**: 250

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 43.63ms | 60.00ms | ✅ |
| Latency (p95) | 67.30ms | 100.00ms | ✅ |
| Latency (max) | 79.51ms | 200.00ms | ✅ |
| Throughput | 9.57 tps | 5.00 tps | ✅ |
| Slippage (median) | 5.86bps | 5.00bps | ❌ |
| Slippage (p95) | 7.75bps | 15.00bps | ✅ |

#### ⚠️ Regression Violations
- Slippage median 5.86bps exceeds budget 5.00bps

### trending_up_btcusd_200ticks
- **Exchange**: synthetic
- **Symbol**: BTCUSD
- **Ticks**: 200

#### Metrics
| Metric | Value | Budget | Status |
|--------|-------|--------|--------|
| Latency (median) | 47.04ms | 60.00ms | ✅ |
| Latency (p95) | 70.07ms | 100.00ms | ✅ |
| Latency (max) | 83.76ms | 200.00ms | ✅ |
| Throughput | 8.81 tps | 5.00 tps | ✅ |
| Slippage (median) | 6.16bps | 5.00bps | ❌ |
| Slippage (p95) | 7.84bps | 15.00bps | ✅ |

#### ⚠️ Regression Violations
- Slippage median 6.16bps exceeds budget 5.00bps

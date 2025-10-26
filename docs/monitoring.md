# Monitoring Guide

This guide covers monitoring, logging, alerting, and observability for TradePulse in both development and production environments.

---

## Table of Contents

- [Overview](#overview)
- [Metrics](#metrics)
- [Logging](#logging)
- [Alerting](#alerting)
- [Prometheus Integration](#prometheus-integration)
- [Grafana Dashboards](#grafana-dashboards)
- [Tracing](#tracing)
- [Production Best Practices](#production-best-practices)

---

## Overview

TradePulse provides comprehensive observability through:

- **Metrics**: Prometheus-compatible metrics for quantitative monitoring
- **Logs**: Structured logging for debugging and audit trails
- **Alerts**: Automated alerting for critical conditions
- **Dashboards**: Grafana dashboards for visualization
- **Tracing**: Distributed tracing for performance analysis (planned)

### Key Principles

1. **Observability First**: Instrument code as you write it
2. **Structured Logging**: Use structured formats (JSON) for easy parsing
3. **Actionable Alerts**: Only alert on conditions requiring human action
4. **Retention Policies**: Balance storage costs with debugging needs

### Observability-as-Code workflow

TradePulse keeps its monitoring stack in the repository under the
`observability/` directory to make dashboards, alerts, and metric catalogues
reproducible across environments. Run the bundle builder after editing any of
the JSON definitions:

```bash
python -m tools.observability.builder --output-dir observability/generated
```

The command validates metric definitions, renders Prometheus alert rules under
`observability/generated/prometheus/alerts.yaml`, and reformats Grafana
dashboards with stable ordering. Include the generated artefacts when promoting
changes to staging or production clusters.

---

## Metrics

### Metric Types

TradePulse uses Prometheus metric types:

#### Counters
Monotonically increasing values (never decrease):
```python
from prometheus_client import Counter

trades_executed = Counter(
    'tradepulse_trades_executed_total',
    'Total number of trades executed',
    ['symbol', 'direction']
)

# Usage
trades_executed.labels(symbol='BTCUSD', direction='buy').inc()
```

#### Gauges
Values that can go up and down:
```python
from prometheus_client import Gauge

open_positions = Gauge(
    'tradepulse_open_positions',
    'Number of currently open positions',
    ['symbol']
)

# Usage
open_positions.labels(symbol='BTCUSD').set(5)
open_positions.labels(symbol='BTCUSD').inc()
open_positions.labels(symbol='BTCUSD').dec()
```

#### Histograms
Distribution of values (e.g., latencies):
```python
from prometheus_client import Histogram

order_latency = Histogram(
    'tradepulse_order_latency_seconds',
    'Time taken to execute orders',
    ['exchange', 'order_type'],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0]
)

# Usage
import time
start = time.time()
execute_order()
order_latency.labels(
    exchange='binance',
    order_type='market'
).observe(time.time() - start)
```

#### Summaries
Similar to histograms, but calculate quantiles on client:
```python
from prometheus_client import Summary

trade_pnl = Summary(
    'tradepulse_trade_pnl',
    'Profit/loss per trade',
    ['strategy', 'symbol']
)

# Usage
trade_pnl.labels(strategy='momentum', symbol='BTCUSD').observe(150.50)
```

TradePulse additionally exports summary-based latency quantiles for the
critical ingestion → signal → execution pipeline. These are enabled automatically
through the `MetricsCollector` helpers:

```python
with collector.measure_signal_generation('momentum'):
    generate_signals()
```

This produces PromQL series such as
`tradepulse_signal_generation_latency_quantiles_seconds{quantile="0.95"}` which map
directly to the p50/p95/p99 panels in Grafana.

### Unified Time and Latency Governance

**Deterministic timestamps depend on a single time source.** All TradePulse
nodes (bare metal, VMs, containers) must synchronise against the same Stratum-1
NTP pool (`time.tradepulse.net`) with `chronyd` configured for a 50 ms maximum
offset. Co-located exchange gateways additionally enable PTP hardware timestamp
support so the matching engine and strategy hosts remain within 5 μs of one
another. Configuration management (Ansible role `infra.time-sync`) enforces the
sources, polling intervals, and drift thresholds, while CI validates that
`chronyc tracking` stays under the permitted offset before promoting an image.

In application code, **timestamps derive from monotonic clocks** to avoid
backwards jumps when wall-clock adjustments occur. Services measure durations via
`time.monotonic_ns()` (Python) or `time.clock_gettime(CLOCK_MONOTONIC_RAW)`
(Go). Every latency metric and span in the signal → order → ack → fill path
records both the raw monotonic duration and the correlated wall-clock time to
preserve auditability without regressing precision.

### Signal → Order → Ack → Fill SLOs

End-to-end trade latency is tracked with explicit service-level objectives and
Grafana visualisations:

- **p50**: ≤ 180 ms for the combined pipeline.
- **p95**: ≤ 400 ms from signal emission to broker acknowledgement.
- **p99**: ≤ 650 ms from signal emission to final fill notification.

Instrumentation emits dedicated gauges for each hop and the aggregate path:

```text
tradepulse_signal_generation_latency_quantiles_seconds{quantile="0.95"}
tradepulse_order_submission_latency_quantiles_seconds{quantile="0.95"}
tradepulse_order_ack_latency_quantiles_seconds{quantile="0.95"}
tradepulse_order_fill_latency_quantiles_seconds{quantile="0.95"}
tradepulse_signal_to_fill_latency_quantiles_seconds{quantile="0.95"}
```

The `quantile` label exposes p50/p95/p99 so alerts can target specific tiers.
Prometheus recording rules aggregate by `strategy` and `exchange` to surface
outliers, and Grafana overlays SLA bands (p95 ≤ 0.4 s, p99 ≤ 0.65 s) for fast
visual validation.

Alerting policy:

1. **Warning (SEV-2)** – p95 signal → ack latency breaches 400 ms for 5 minutes.
2. **Critical (SEV-1)** – p99 signal → fill latency exceeds 650 ms for 5
   minutes, triggering the on-call rotation and automated rollback guardrails.

Alert rules appear in `observability/alerts.json` and the generated Prometheus
manifest so staging and production share identical thresholds.

### Core Metrics

#### Trading Metrics
```python
# Trades
trades_executed_total       # Counter: Total trades executed
trade_errors_total          # Counter: Failed trades
trade_pnl_usd               # Summary: P&L per trade
trade_latency_seconds       # Histogram: Order execution time
tradepulse_signal_generation_latency_quantiles_seconds  # Gauge: Signal engine latency (p50/p95/p99)
tradepulse_order_submission_latency_quantiles_seconds   # Gauge: Order placement latency (p50/p95/p99)
tradepulse_order_ack_latency_quantiles_seconds          # Gauge: Submission → acknowledgement latency (p50/p95/p99)
tradepulse_order_fill_latency_quantiles_seconds         # Gauge: Fill latency (p50/p95/p99)
tradepulse_signal_to_fill_latency_quantiles_seconds     # Gauge: Signal → fill aggregate latency (p50/p95/p99)

# Positions
open_positions_count        # Gauge: Current open positions
position_value_usd          # Gauge: Total position value
position_exposure_percent   # Gauge: Portfolio exposure
tradepulse_backtest_equity_curve              # Gauge: Equity curve samples per backtest run

# Risk
portfolio_value_usd         # Gauge: Current portfolio value
drawdown_percent            # Gauge: Current drawdown
risk_per_trade_percent      # Gauge: Risk per trade
```

#### System Metrics
```python
# Performance
indicator_computation_seconds  # Histogram: Time to compute indicators
backtest_duration_seconds      # Histogram: Backtest execution time
data_ingestion_rate           # Gauge: Ticks/bars per second
tradepulse_data_ingestion_latency_quantiles_seconds    # Gauge: Data ingestion latency (p50/p95/p99)

# Health
service_up                    # Gauge: Service health (1=up, 0=down)
last_heartbeat_timestamp      # Gauge: Last heartbeat time
error_rate                    # Counter: Errors per component
```

#### Data Quality Metrics
```python
# Data
data_gaps_total              # Counter: Missing data points
invalid_prices_total         # Counter: Invalid price data
data_staleness_seconds       # Gauge: Time since last update
```

### Implementing Metrics in Python

```python
# metrics.py
from prometheus_client import Counter, Gauge, Histogram, Summary, generate_latest
import time
from typing import Optional
from contextlib import contextmanager

# Define metrics
trades_counter = Counter(
    'tradepulse_trades_total',
    'Total trades executed',
    ['symbol', 'direction', 'strategy']
)

position_gauge = Gauge(
    'tradepulse_open_positions',
    'Open positions',
    ['symbol']
)

latency_histogram = Histogram(
    'tradepulse_indicator_latency_seconds',
    'Indicator computation latency',
    ['indicator_name']
)

# Helper functions
@contextmanager
def measure_time(metric: Histogram, **labels):
    """Context manager for measuring execution time."""
    start = time.time()
    try:
        yield
    finally:
        metric.labels(**labels).observe(time.time() - start)

# Usage in code
def execute_trade(symbol: str, direction: str, strategy: str):
    """Execute a trade and record metrics."""
    try:
        # Execute trade logic
        result = _do_execute_trade(symbol, direction)
        
        # Record success
        trades_counter.labels(
            symbol=symbol,
            direction=direction,
            strategy=strategy
        ).inc()
        
        return result
    except Exception as e:
        # Record error
        error_counter.labels(error_type=type(e).__name__).inc()
        raise

def compute_indicator(prices, name: str):
    """Compute indicator and measure latency."""
    with measure_time(latency_histogram, indicator_name=name):
        return _compute_indicator_impl(prices)
```

### Exposing Metrics

```python
# Start Prometheus metrics server
from prometheus_client import start_http_server

# Start on port 8000
start_http_server(8000)

# Metrics available at http://localhost:8000/metrics
```

---

## Logging

### Structured Logging

Use Python's `logging` module with JSON formatting:

```python
import logging
import json
from datetime import datetime

class JSONFormatter(logging.Formatter):
    """Format logs as JSON."""
    
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        # Add custom fields
        if hasattr(record, 'extra_fields'):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data)

# Configure logging
logger = logging.getLogger('tradepulse')
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

### Log Levels

Use appropriate log levels:

```python
# DEBUG: Detailed diagnostic information
logger.debug('Computed indicator', extra={
    'extra_fields': {
        'indicator': 'kuramoto',
        'value': 0.85,
        'window': 200
    }
})

# INFO: General informational messages
logger.info('Trade executed', extra={
    'extra_fields': {
        'symbol': 'BTCUSD',
        'direction': 'buy',
        'quantity': 0.1,
        'price': 50000.0
    }
})

# WARNING: Warning messages for potentially problematic situations
logger.warning('High latency detected', extra={
    'extra_fields': {
        'latency_ms': 5000,
        'threshold_ms': 1000,
        'exchange': 'binance'
    }
})

# ERROR: Error messages for recoverable errors
logger.error('Trade execution failed', extra={
    'extra_fields': {
        'symbol': 'BTCUSD',
        'error': str(e),
        'attempt': 3
    }
})

# CRITICAL: Critical messages for non-recoverable errors
logger.critical('Database connection lost', extra={
    'extra_fields': {
        'database': 'trades',
        'host': 'localhost'
    }
})
```

### Log Categories

#### Trading Logs
```python
trade_logger = logging.getLogger('tradepulse.trading')

# Log all trades
trade_logger.info('ORDER_PLACED', extra={'extra_fields': {
    'order_id': '12345',
    'symbol': 'BTCUSD',
    'direction': 'buy',
    'quantity': 0.1,
    'price': 50000.0,
    'order_type': 'limit'
}})

trade_logger.info('ORDER_FILLED', extra={'extra_fields': {
    'order_id': '12345',
    'fill_price': 49950.0,
    'commission': 0.1
}})
```

#### System Logs
```python
sys_logger = logging.getLogger('tradepulse.system')

sys_logger.info('SERVICE_START', extra={'extra_fields': {
    'service': 'execution_engine',
    'version': '1.0.0'
}})

sys_logger.warning('HIGH_MEMORY_USAGE', extra={'extra_fields': {
    'memory_mb': 2048,
    'threshold_mb': 1500
}})
```

#### Audit Logs
```python
audit_logger = logging.getLogger('tradepulse.audit')

audit_logger.info('CONFIG_CHANGED', extra={'extra_fields': {
    'user': 'admin',
    'parameter': 'risk_per_trade',
    'old_value': 0.01,
    'new_value': 0.02
}})
```

### Log Aggregation

For production, use log aggregation tools:

- **ELK Stack** (Elasticsearch, Logstash, Kibana)
- **Loki** (with Grafana)
- **Splunk**
- **Datadog**

Example Loki configuration:
```yaml
# promtail-config.yml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: tradepulse
    static_configs:
      - targets:
          - localhost
        labels:
          job: tradepulse
          __path__: /var/log/tradepulse/*.log
```

---

## Alerting

### Alert Rules

Define alerts for critical conditions:

```yaml
# prometheus-alerts.yml
groups:
  - name: tradepulse_trading
    interval: 30s
    rules:
      # High error rate
      - alert: HighTradeErrorRate
        expr: rate(tradepulse_trade_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High trade error rate"
          description: "Error rate is {{ $value }} trades/sec"
      
      # Large drawdown
      - alert: LargeDrawdown
        expr: tradepulse_drawdown_percent > 10
        for: 1m
        labels:
          severity: warning
        annotations:
          summary: "Large drawdown detected"
          description: "Drawdown is {{ $value }}%"
      
      # Service down
      - alert: ServiceDown
        expr: up{job="tradepulse"} == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "TradePulse service is down"
          description: "Service {{ $labels.instance }} is down"
      
      # High latency
      - alert: HighOrderLatency
        expr: histogram_quantile(0.95, tradepulse_order_latency_seconds_bucket) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High order execution latency"
          description: "95th percentile latency is {{ $value }}s"
      
      # Stale data
      - alert: StaleMarketData
        expr: time() - tradepulse_last_data_timestamp > 300
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Market data is stale"
          description: "No data received for 5+ minutes"
```

### Alert Manager Configuration

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'default'
  routes:
    - match:
        severity: critical
      receiver: pagerduty
      continue: true
    - match:
        severity: warning
      receiver: slack

receivers:
  - name: 'default'
    email_configs:
      - to: 'alerts@tradepulse.local'
  
  - name: 'slack'
    slack_configs:
      - api_url: 'YOUR_SLACK_WEBHOOK_URL'
        channel: '#tradepulse-alerts'
        title: 'TradePulse Alert'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}'
  
  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: 'YOUR_PAGERDUTY_KEY'

inhibit_rules:
  - source_match:
      severity: 'critical'
    target_match:
      severity: 'warning'
    equal: ['alertname', 'instance']
```

### SLO-driven Auto Rollback

TradePulse now ships with an ``AutoRollbackGuard`` helper that consumes error rate
and latency metrics to automatically revert unhealthy releases. Configure the
guard with the expected SLO thresholds and wire a deployment specific callback
that performs the rollback:

```python
from dataclasses import dataclass
from datetime import timedelta

from core.utils import AutoRollbackGuard, SLOBurnRateRule, SLOConfig

@dataclass
class RequestMetrics:
    latency_ms: float
    success: bool

def initiate_canary_rollback(reason: str, summary: dict[str, float]) -> None:
    deployer.rollback_release(summary)

guard = AutoRollbackGuard(
    SLOConfig(
        error_rate_threshold=0.02,       # 2% errors allowed
        latency_threshold_ms=450.0,      # p95 latency ceiling
        evaluation_period=timedelta(minutes=5),
        min_requests=200,
        cooldown=timedelta(minutes=10),
        burn_rate_rules=(
            SLOBurnRateRule(
                window=timedelta(minutes=1),
                max_burn_rate=6.0,
                min_requests=50,
            ),
            SLOBurnRateRule(
                window=timedelta(minutes=5),
                max_burn_rate=3.0,
            ),
        ),
    ),
    rollback_callback=initiate_canary_rollback,
)

def handle_request(result: RequestMetrics) -> None:
    guard.record_outcome(result.latency_ms, result.success)
```

For externally aggregated metrics (e.g. Prometheus or Datadog) feed the guard
with snapshots instead of individual requests:

```python
snapshot = metrics_backend.fetch_slo_snapshot()
guard.evaluate_snapshot(
    error_rate=snapshot.error_rate,
    latency_p95_ms=snapshot.p95_latency_ms,
    total_requests=snapshot.request_count,
)
```

The guard enforces a cooldown window between rollbacks to avoid flapping and
exposes the last evaluation summary for audit dashboards. Instrument the
callback with deployer specific logging to trace mitigation steps. Burn-rate
policies mirror Google's multi-window multi-burn alerts: the guard retains the
largest window duration, annotates summaries with per-window burn rates, and
triggers early rollbacks when fast or slow windows exceed their configured
error-budget consumption.

---

## Prometheus Integration

### Installation

```bash
# Using Docker Compose
docker compose up prometheus

# Or download binary
wget https://github.com/prometheus/prometheus/releases/download/v2.45.0/prometheus-2.45.0.linux-amd64.tar.gz
tar xvfz prometheus-*.tar.gz
cd prometheus-*
./prometheus --config.file=prometheus.yml
```

### Configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Alert manager configuration
alerting:
  alertmanagers:
    - static_configs:
        - targets:
            - alertmanager:9093

# Load alert rules
rule_files:
  - "prometheus-alerts.yml"

# Scrape configurations
scrape_configs:
  # TradePulse Python services
  - job_name: 'tradepulse-python'
    static_configs:
      - targets: ['localhost:8000']
        labels:
          service: 'execution-engine'
  
  # TradePulse Go services
  - job_name: 'tradepulse-go'
    static_configs:
      - targets:
          - 'localhost:8001'  # VPIN service
          - 'localhost:8002'  # Orderbook service
          - 'localhost:8003'  # Regime service
        labels:
          service: 'analytics'
  
  # Node exporter (system metrics)
  - job_name: 'node'
    static_configs:
      - targets: ['localhost:9100']
  
  # Container metrics
  - job_name: 'cadvisor'
    static_configs:
      - targets: ['localhost:8080']
```

### Querying Metrics

```promql
# Total trades in last hour
sum(increase(tradepulse_trades_total[1h]))

# Average order latency by exchange
avg(tradepulse_order_latency_seconds) by (exchange)

# Error rate
rate(tradepulse_trade_errors_total[5m])

# 95th percentile latency
histogram_quantile(0.95, rate(tradepulse_order_latency_seconds_bucket[5m]))

# Current drawdown
tradepulse_drawdown_percent

# Trades per symbol
sum(tradepulse_trades_total) by (symbol)
```

---

## Grafana Dashboards

### Installation

```bash
# Using Docker Compose
docker compose up grafana

# Access at http://localhost:3000
# Default credentials: admin/admin
```

### Dashboard Configuration

```json
{
  "dashboard": {
    "title": "TradePulse Overview",
    "panels": [
      {
        "title": "Trades per Minute",
        "targets": [
          {
            "expr": "rate(tradepulse_trades_total[1m]) * 60"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Current Drawdown",
        "targets": [
          {
            "expr": "tradepulse_drawdown_percent"
          }
        ],
        "type": "singlestat"
      },
      {
        "title": "Order Latency (p95)",
        "targets": [
          {
            "expr": "histogram_quantile(0.95, rate(tradepulse_order_latency_seconds_bucket[5m]))"
          }
        ],
        "type": "graph"
      },
      {
        "title": "Open Positions by Symbol",
        "targets": [
          {
            "expr": "tradepulse_open_positions"
          }
        ],
        "type": "bargauge"
      }
    ]
  }
}
```

### Key Dashboards

#### Trading Dashboard
- Real-time P&L
- Trade count and volume
- Win rate and Sharpe ratio
- Open positions
- Recent trades table

#### System Dashboard
- CPU and memory usage
- Service uptime
- Error rates
- API latency
- Database connections

#### Risk Dashboard
- Current drawdown
- Portfolio value
- Exposure by symbol
- Risk metrics
- VaR and CVaR

---

## Tracing

### OpenTelemetry Integration

TradePulse now ships a first-class tracing module under `observability.tracing`
that configures an OTLP exporter and exposes helpers for the ingest → features →
signals → orders pipeline. Traces automatically correlate with structured logs
when `JSONFormatter` is enabled.

```python
from observability.tracing import TracingConfig, configure_tracing, pipeline_span

# Configure tracing once during application start-up. The exporter endpoint can
# also be controlled via OTEL_EXPORTER_OTLP_ENDPOINT.
configure_tracing(
    TracingConfig(service_name="tradepulse-api", environment="production")
)

def run_pipeline():
    with pipeline_span("ingest.historical_csv", source="csv", symbol="ETHUSDT"):
        load_prices()

    with pipeline_span("features.transform", feature_name="mean_ricci"):
        compute_features()

    with pipeline_span("signals.simulate_performance", strategy="mean-reversion"):
        signal = generate_signal()

    with pipeline_span("orders.submit", symbol="ETHUSDT", side="buy"):
        place_order(signal)
```

Because `pipeline_span` yields the active span, advanced users can attach
custom attributes or record exceptions. When OpenTelemetry libraries are not
installed the helper degrades to a no-op so unit tests remain lightweight.

### Health checks

Use `observability.health.HealthServer` to expose `/healthz` and `/readyz`
endpoints in a background thread:

```python
from observability.health import HealthServer

with HealthServer(port=8085) as server:
    server.set_ready(True)
    server.update_component("postgres", healthy=True)
    run_application_loop()
```

Pair the HTTP server with `observability.health_monitor.PeriodicHealthMonitor`
to keep the readiness state fresh without relying on ad-hoc probes. The helper
executes the default checks in `observability.health_checks` on a cadence and
updates the `HealthServer` object as well as Prometheus metrics:

```python
from observability.health_checks import build_default_health_checks
from observability.health_monitor import PeriodicHealthMonitor

checks = build_default_health_checks(system)
monitor = PeriodicHealthMonitor(server, checks)
monitor.start()
```

Two new metrics help track probe performance:

* `tradepulse_health_check_latency_seconds` – histogram capturing the runtime
  of each periodic check.
* `tradepulse_health_check_status` – gauge signalling the most recent outcome
  (1=healthy, 0=unhealthy).

Operational metrics now also include
`tradepulse_data_ingestion_throughput_ticks_per_second`, exposing how quickly
the ingestion layer is processing raw ticks.

### Exporters in isolated processes

The metrics stack can now be hosted outside the main interpreter to reduce
contention:

```python
from core.utils.metrics import start_metrics_exporter_process, stop_metrics_exporter_process

exporter = start_metrics_exporter_process(port=9000)
try:
    start_application()
finally:
    stop_metrics_exporter_process(exporter)
```

### Pipeline dashboards

Grafana ships with `observability/dashboards/tradepulse-pipeline.json` which
provides latency, throughput, and error-budget panels for the end-to-end
pipeline. Import it alongside the existing overview dashboard to monitor SLOs.

### Shipping logs to Elasticsearch

`docker-compose.yml` provisions Elasticsearch, Logstash, Filebeat, and Kibana to
collect TradePulse container logs. Start the stack with:

```bash
docker compose up tradepulse prometheus elasticsearch logstash kibana filebeat
```

Filebeat autodiscovers containers labelled with `co.elastic.logs/enabled=true`
and forwards their JSON log streams to Logstash, which normalises the payload
before indexing it under the `tradepulse-logs-*` pattern. Kibana surfaces the
data at <http://localhost:5601> for ad-hoc queries and dashboards.

For Kubernetes environments the staging and production Kustomize overlays now
include a `filebeat` DaemonSet and a `logstash` Deployment. Applying either
overlay deploys the log shipping stack and annotates backend pods so their
structured stdout is forwarded automatically. Update the Logstash deployment's
`ELASTICSEARCH_*` environment variables to point at your managed Elastic
Cluster, or provide an `ELASTICSEARCH_API_KEY` when API key auth is preferred.

---

## Production Best Practices

### 1. Metrics Cardinality

**Avoid high-cardinality labels:**
```python
# Bad: user_id as label (millions of unique values)
metric.labels(user_id=user_id).inc()

# Good: Use log aggregation for high cardinality
logger.info('trade_executed', extra={'user_id': user_id})
```

### 2. Retention Policies

```yaml
# prometheus.yml
storage:
  tsdb:
    retention.time: 30d
    retention.size: 50GB
```

### 3. Monitoring the Monitors

- Monitor Prometheus itself
- Set up alerting for monitoring failures
- Have redundant monitoring systems

### 4. Performance

- Use appropriate metric types
- Batch metric updates when possible
- Don't create metrics in hot loops
- Use sampling for high-frequency events

### 5. Security

- Protect metrics endpoints with authentication
- Use TLS for Prometheus scraping
- Limit access to Grafana dashboards
- Sanitize labels to prevent injection

### 6. Documentation

- Document all custom metrics
- Explain alert thresholds
- Maintain runbooks for alerts
- Keep dashboard descriptions updated

---

## Quick Start Checklist

- [ ] Start Prometheus and Grafana
- [ ] Instrument your code with metrics
- [ ] Configure log formatters
- [ ] Set up alert rules
- [ ] Create Grafana dashboards
- [ ] Test alerts in staging
- [ ] Set up on-call rotation
- [ ] Document runbooks

---

## References

- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Best Practices](https://prometheus.io/docs/practices/)
- [Google SRE Book - Monitoring](https://sre.google/sre-book/monitoring-distributed-systems/)
- [The Four Golden Signals](https://sre.google/sre-book/monitoring-distributed-systems/#xref_monitoring_golden-signals)

---

**Last Updated**: 2025-01-01

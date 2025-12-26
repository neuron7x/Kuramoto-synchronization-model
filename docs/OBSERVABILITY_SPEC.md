# TradePulse Observability Specification

> **Principal Observability & Incident Engineering Spec**
>
> Цей документ визначає "золоті сигнали" та телеметрію для TradePulse.
> Система після цього — прозорий організм: видно що вона думає, видно коли їй погано.

## 1. Golden Signals — Ключові Сигнали

### 1.1 Execution Pipeline

| Сигнал | Тип | Назва метрики | Threshold |
|--------|-----|---------------|-----------|
| **Latency** | Histogram | `tradepulse_order_placement_duration_seconds` | p95 < 2s, p99 < 5s |
| **Latency** | Gauge | `tradepulse_order_ack_latency_quantiles_seconds` | p95 < 400ms |
| **Latency** | Gauge | `tradepulse_signal_to_fill_latency_quantiles_seconds` | p99 < 650ms |
| **Error Rate** | Counter | `tradepulse_orders_placed_total{status="error"}` | < 5% за 5 хв |
| **Throughput** | Counter | `tradepulse_orders_placed_total` | baseline-specific |
| **Saturation** | Gauge | `tradepulse_api_queue_depth` | < 1000 pending |

### 1.2 Risk Engine

| Сигнал | Тип | Назва метрики | Threshold |
|--------|-----|---------------|-----------|
| **Blocked Orders** | Counter | `tradepulse_risk_rejections_total` | alert if > 10/min |
| **Kill Switch** | Gauge | `tradepulse_risk_kill_switch` | 1 = ENGAGED → CRITICAL |
| **Circuit State** | Gauge | `tradepulse_risk_circuit_state` | 1 (open) = warn, 2 (half_open) = info |
| **Circuit Trips** | Counter | `tradepulse_risk_circuit_trips_total` | alert on any trip |
| **Gross Exposure** | Gauge | `tradepulse_risk_gross_exposure` | < configured limit |
| **Daily Drawdown** | Gauge | `tradepulse_risk_daily_drawdown` | < configured limit |
| **Risk Validation** | Counter | `tradepulse_risk_validations_total` | track pass/reject ratio |
| **Drawdown** | Gauge | `tradepulse_drawdown_percent` | < configured % |

### 1.3 Trading Mode Transitions

| Сигнал | Тип | Назва метрики | Threshold |
|--------|-----|---------------|-----------|
| **Current Mode** | Gauge | `tradepulse_trading_mode` | label: BACKTEST/PAPER/LIVE |
| **Mode Switch** | Counter | `tradepulse_trading_mode_transitions_total` | audit trail |
| **Time in Mode** | Gauge | `tradepulse_trading_mode_duration_seconds` | monitoring |

### 1.4 Data Ingestion

| Сигнал | Тип | Назва метрики | Threshold |
|--------|-----|---------------|-----------|
| **Latency** | Histogram | `tradepulse_data_ingestion_duration_seconds` | p95 < 1s |
| **Error Rate** | Counter | `tradepulse_data_ingestion_total{status="error"}` | 0 errors |
| **Throughput** | Gauge | `tradepulse_data_ingestion_throughput_ticks_per_second` | > 0 |
| **Freshness** | Gauge | _derived_ | data < 5 min old |

### 1.5 Backtest Pipeline

| Сигнал | Тип | Назва метрики | Threshold |
|--------|-----|---------------|-----------|
| **Duration** | Histogram | `tradepulse_backtest_duration_seconds` | strategy-specific |
| **Error Rate** | Counter | `tradepulse_backtest_total{status="error"}` | 0 errors |
| **PnL** | Gauge | `tradepulse_backtest_pnl` | monitoring |
| **Max Drawdown** | Gauge | `tradepulse_backtest_max_drawdown` | < threshold |

### 1.6 ML/Model Inference (якщо MLSDM підключено)

| Сигнал | Тип | Назва метрики | Threshold |
|--------|-----|---------------|-----------|
| **Latency** | Histogram | `tradepulse_model_inference_latency_seconds` | p99 < 500ms |
| **Error Rate** | Gauge | `tradepulse_model_inference_error_ratio` | < 1% |
| **Throughput** | Gauge | `tradepulse_model_inference_throughput_per_second` | > 0 |
| **Saturation** | Gauge | `tradepulse_model_saturation` | < 0.8 |
| **Aphasia/Blocks** | Counter | `tradepulse_model_quality_degradation_events_total` | monitor |

---

## 2. Structured Logging Requirements

### 2.1 Обов'язкові Поля

Кожен лог запис ПОВИНЕН містити:

```json
{
  "timestamp": "2025-01-15T10:30:00.123Z",
  "level": "INFO|WARN|ERROR|CRITICAL",
  "logger": "module.submodule",
  "message": "Human-readable message",
  "correlation_id": "uuid-v4",
  "trace_id": "hex-32-chars",
  "span_id": "hex-16-chars",
  "component": "execution|risk|backtest|data|api",
  "mode": "BACKTEST|PAPER|LIVE"
}
```

### 2.2 Контекстні Поля (де релевантно)

```json
{
  "trade_id": "string",
  "order_id": "string",
  "strategy_id": "string",
  "symbol": "BTC-USD",
  "exchange": "binance",
  "side": "buy|sell",
  "quantity": 1.5,
  "price": 50000.0,
  "status": "pending|filled|rejected|error",
  "reason": "kill_switch_triggered",
  "duration_seconds": 0.123
}
```

### 2.3 Критичні Сценарії для Логування

1. **Order Lifecycle**
   - Order created → submitted → acknowledged → filled/rejected
   - Кожен етап = окремий лог запис з timing

2. **Risk Engine Decisions**
   - Validation passed/rejected + reason
   - Kill-switch trigger/reset + reason
   - Circuit breaker state changes

3. **Mode Transitions**
   - From BACKTEST → PAPER → LIVE
   - Who initiated, why, timestamp

4. **Errors & Exceptions**
   - Stack trace (sanitized)
   - Context що привело до помилки
   - Recovery actions taken

### 2.4 Sanitization Rules

**НЕ ЛОГУВАТИ:**
- API keys, secrets, tokens
- User passwords
- Full credit card numbers
- Personal identification info

**МАСКУВАТИ:**
- Account IDs → last 4 chars only
- IP addresses in production

---

## 3. Alert Definitions

### 3.1 CRITICAL Alerts (треба дивитися зараз)

| Alert | Expression | For | Description |
|-------|------------|-----|-------------|
| `KillSwitchEngaged` | `tradepulse_risk_kill_switch == 1` | 0m | Kill switch is ON |
| `HighOrderErrorRate` | `rate(orders{status="error"}[5m]) / rate(orders[5m]) > 0.05` | 5m | >5% orders failing |
| `CircuitBreakerOpen` | `tradepulse_risk_circuit_state{state="open"} == 1` | 1m | Circuit breaker tripped |
| `DataIngestionDown` | `rate(data_ingestion{status="error"}[10m]) > 0` | 0m | Data pipeline broken |
| `CriticalIncidentOpen` | `tradepulse_incidents_open{severity="critical"} > 0` | 0m | Unmitigated incident |

### 3.2 WARNING Alerts (можна ігнорувати деякий час)

| Alert | Expression | For | Description |
|-------|------------|-----|-------------|
| `HighOrderLatency` | `histogram_quantile(0.95, order_latency[5m]) > 2` | 10m | p95 > 2 seconds |
| `RiskRejectionsSpike` | `rate(risk_rejections[5m]) > 10` | 5m | Too many blocked orders |
| `DrawdownWarning` | `tradepulse_drawdown_percent > 5` | 10m | Drawdown > 5% |
| `ModelLatencyHigh` | `model_latency{quantile="0.99"} > 0.5` | 5m | ML p99 > 500ms |
| `MetricsMissing` | `absent(up{job="tradepulse"})` | 5m | Service unreachable |

---

## 4. Dashboard Panels

### 4.1 TradePulse Core Dashboard

**Execution Panel:**
- Order throughput (orders/sec)
- Error rate (% failed)
- Latency heatmap (p50, p95, p99)
- Open positions count

**Risk Panel:**
- Blocked orders timeline
- Kill-switch status indicator
- Circuit breaker state
- Current exposure vs limits
- Drawdown %

**Mode Panel:**
- Current trading mode (BACKTEST/PAPER/LIVE)
- Mode transition history
- Time in current mode

### 4.2 Risk Engine Dashboard

- Rejections by reason (pie chart)
- Circuit trips over time
- Gross exposure trend
- Daily drawdown progression
- Kill-switch events timeline

### 4.3 ML/MLSDM Health Dashboard (optional)

- Inference latency distribution
- Error ratio trend
- Throughput over time
- Saturation level
- Degradation events

---

## 5. Health Check Probes

### 5.1 Liveness Probe
```
GET /health/live
Response: {"status": "ok"} or 503
```
Перевіряє:
- Process is running
- Main loop responsive

### 5.2 Readiness Probe
```
GET /health/ready
Response: {"status": "ready", "checks": {...}} or 503
```
Перевіряє:
- Database connection
- Exchange connectivity
- Risk engine initialized
- Data feed active

### 5.3 Deep Health Check
```
GET /health/deep
Response: detailed component status
```
Перевіряє все + latency кожного компонента

---

## 6. Telemetry Collection Points

| Component | Collection Point | Frequency |
|-----------|------------------|-----------|
| API Server | Request middleware | per-request |
| Execution | Order placement | per-order |
| Risk Engine | Validation hook | per-validation |
| Backtest | Engine wrapper | per-backtest |
| Data Ingestion | Pipeline stage | per-tick batch |
| Model Inference | Inference wrapper | per-inference |

---

## 7. Retention & Storage

| Data Type | Retention | Storage |
|-----------|-----------|---------|
| Metrics | 15 days high-res, 1 year downsampled | Prometheus + Thanos |
| Logs | 30 days hot, 1 year cold | Elasticsearch + S3 |
| Traces | 7 days | Jaeger/Tempo |
| Alerts History | 90 days | Prometheus/Alertmanager |

---

## 8. Implementation Checklist

- [x] Structured logging configured in `core/utils/logging.py`
- [x] Core metrics defined in `core/utils/metrics.py`
- [x] Risk metrics in `execution/metrics.py`
- [ ] Trading mode metrics (NEW)
- [x] Alert rules in `observability/alerts.json`
- [ ] Risk-specific alerts (PENDING UPDATE)
- [x] Grafana dashboards in `observability/dashboards/`
- [ ] Risk Engine dashboard panel (PENDING UPDATE)
- [ ] Health check endpoints standardized
- [ ] Log sanitization enforced

---

## Appendix: Control-gate decision telemetry

Example `DECISION_EVENT` log line:

```json
{"config_fingerprint":"<sha256>","controller_states":{"serotonin":{"action_gate":"ALLOW"},"thermo":{"controller_state":"STABLE"}},"decision":"ALLOW","inputs_summary":{"risk_score":1.0,"free_energy":0.2},"position_multiplier":1.0,"proxies":{"flags":[],"missing_metrics":false,"proxy_energy":false,"proxy_risk":false},"reasons":[],"throttle_ms":0,"trace_id":null,"ts_unix_ms":1735226400000,"version":"gate_pipeline.v1"}
```

Runtime checks (no network bind):

- `python -m application.runtime.server --config <path> --dry-run`
- `python -m application.runtime.server --config <path> --health`

---

*Last updated: 2025-12-02*
*Owner: Principal Observability & Incident Engineer*

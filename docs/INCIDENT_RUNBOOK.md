# GeoSync Incident Runbook

> **Коли все йде по пизді — відкривай цей документ.**
>
> Структурований план дій для типових інцидентів GeoSync.

---

## Incident Severity Levels

| Level | Response Time | Description |
|-------|--------------|-------------|
| **SEV1 - CRITICAL** | 5 хвилин | Втрата грошей, повна зупинка, kill-switch спрацював |
| **SEV2 - HIGH** | 30 хвилин | Деградація сервісу, часткова втрата функціональності |
| **SEV3 - MEDIUM** | 4 години | Незначні проблеми, workaround існує |
| **SEV4 - LOW** | 24 години | Косметичні проблеми, оптимізації |

---

## Типові Інциденти

<a id="1-kill-switch-triggered"></a>
### 1. Kill-Switch Спрацював

**Симптоми:**
- Alert: `KillSwitchEngaged`
- Metric: `geosync_risk_kill_switch == 1`
- Всі ордери блокуються

**Перші дії (< 5 хв):**

1. **Перевір причину в логах:**
   ```bash
   grep -i "kill.switch.trigger" /var/log/geosync/*.log | tail -20
   ```
   Або в Kibana: `event: "kill_switch_triggered"`

2. **Перевір метрики:**
   - Grafana → GeoSync Risk Dashboard
   - Подивись `geosync_risk_rejections_total` — що саме блокувалось?
   - `geosync_drawdown_percent` — чи є drawdown breach?

3. **Визнач root cause:**
   - Position limit exceeded?
   - Notional cap breached?
   - Drawdown limit hit?
   - Rate limit violations?

**Рішення:**

| Причина | Дія |
|---------|-----|
| Position limit | Перевір відкриті позиції, закрий якщо потрібно |
| Drawdown | Зачекай або reset equity tracking |
| Rate limit | Перевір логіку throttling |
| False positive | Reset kill-switch через admin API |

**Reset Kill-Switch:**
```bash
# Через CLI
geosync-admin kill-switch reset --reason "Manual reset after investigation"

# Або через API
curl -X POST http://localhost:8080/admin/kill-switch/reset \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"reason": "Investigated, false positive"}'
```

**Postmortem trigger:** ОБОВ'ЯЗКОВО якщо SEV1/SEV2.

---

<a id="2-no-new-orders"></a>
### 2. Немає Нових Ордерів

**Симптоми:**
- `rate(geosync_orders_placed_total[5m]) == 0`
- Alert: `NoOrdersPlaced`
- Стратегія "мовчить"

**Diagnosis:**

1. **Перевір чи сервіс живий:**
   ```bash
   curl http://localhost:8080/health/ready
   ```

2. **Перевір data feed:**
   ```bash
   # Чи приходять тики?
   grep "tick.processed" /var/log/geosync/data.log | tail -5
   ```
   Metric: `geosync_ticks_processed_total` — чи зростає?

3. **Перевір signal generation:**
   ```bash
   grep "signal.generated" /var/log/geosync/strategy.log | tail -5
   ```
   Metric: `geosync_signal_generation_total`

4. **Перевір risk-engine:**
   ```bash
   # Чи все блокується?
   grep "risk_validation.*rejected" /var/log/geosync/execution.log | tail -10
   ```

5. **Перевір exchange connectivity:**
   ```bash
   geosync-admin exchange status
   ```

**Decision Tree:**

```
Тики не приходять?
  → Restart data feed service
  → Перевір API keys exchange

Сигнали не генеруються?
  → Перевір strategy configuration
  → Перевір warmup period

Все блокується risk-engine?
  → Дивись "Kill-Switch Спрацював" вище

Exchange не відповідає?
  → Перевір network/firewall
  → Перевір exchange status page
```

---

<a id="3-risk-engine-blocking"></a>
### 3. Risk-Engine Блокує Все

**Симптоми:**
- Spike в `geosync_risk_rejections_total`
- Alert: `RiskRejectionsSpike`
- Ордери створюються, але не йдуть на exchange

**Diagnosis:**

1. **Подивись reasons:**
   ```bash
   # Grafana: Risk Rejections by Reason
   # Або в логах:
   grep "risk_validation.*rejected" /var/log/geosync/*.log | \
     grep -oP 'reason="[^"]+"' | sort | uniq -c
   ```

2. **Типові причини:**

| Reason | Що робити |
|--------|-----------|
| `position_limit` | Перевір поточні позиції, можливо вже на max |
| `notional_limit` | Exposure занадто великий |
| `rate_limit` | Занадто багато ордерів, throttle працює |
| `kill_switch` | Kill-switch активний |
| `circuit_breaker` | Circuit breaker open |

3. **Перевір ліміти:**
   ```bash
   geosync-admin risk limits show
   ```

**Рішення:**
- Якщо ліміти коректні → це працює як треба, нічого не робити
- Якщо ліміти занадто жорсткі → update через config
- Якщо помилка в position tracking → reset state

---

<a id="4-ml-errors-timeouts"></a>
### 4. ML Відповідає з Помилками / Таймаутами

**Симптоми:**
- Alert: `ModelLatencyHigh` або `ModelErrorRateHigh`
- Metric: `geosync_model_inference_error_ratio > 0.01`
- Логи: `model_inference.*error`

**Diagnosis:**

1. **Перевір model serving:**
   ```bash
   curl http://model-server:8501/v1/models/trading_model
   ```

2. **Перевір latency:**
   - Grafana → MLSDM Health Dashboard
   - `geosync_model_inference_latency_seconds`

3. **Перевір ресурси:**
   ```bash
   # GPU utilization
   nvidia-smi
   # CPU/Memory
   top -b -n1 | head -20
   ```

**Рішення:**

| Симптом | Дія |
|---------|-----|
| Model server down | Restart model service |
| High latency | Scale up, check batch size |
| OOM | Reduce batch size, add memory |
| GPU issues | Check CUDA, restart GPU process |

**Fallback:**
```bash
# Переключити на fallback model
geosync-admin model switch --to fallback
```

---

<a id="5-metrics-logs-missing"></a>
### 5. Метрики/Логи Пропали

**Симптоми:**
- Alert: `MetricsMissing`
- Grafana dashboards empty
- Kibana no recent logs

**Diagnosis:**

1. **Чи сервіс працює?**
   ```bash
   systemctl status geosync
   ps aux | grep geosync
   ```

2. **Чи /metrics endpoint відповідає?**
   ```bash
   curl http://localhost:8080/metrics | head -20
   ```

3. **Чи Prometheus scrape працює?**
   - Prometheus UI → Targets → перевір geosync target

4. **Чи логи пишуться?**
   ```bash
   tail -f /var/log/geosync/app.log
   # Якщо disk full:
   df -h
   ```

**Рішення:**

| Причина | Дія |
|---------|-----|
| Service down | Restart service |
| Prometheus can't reach | Check network, firewall |
| Disk full | Clean old logs, expand disk |
| Metrics endpoint broken | Check for errors in startup logs |

---

<a id="6-high-latency-order-execution"></a>
### 6. High Latency на Order Execution

**Симптоми:**
- Alert: `HighOrderLatency`
- p95 > 2 seconds
- Metric: `geosync_order_placement_duration_seconds`

**Diagnosis:**

1. **Де саме затримка?**
   - `geosync_order_ack_latency_quantiles_seconds` — exchange slow?
   - Signal generation slow?
   - Risk validation slow?

2. **Перевір exchange status:**
   ```bash
   curl https://api.exchange.com/status
   ```

3. **Перевір internal queues:**
   - Metric: `geosync_api_queue_depth`

**Рішення:**

| Причина | Дія |
|---------|-----|
| Exchange slow | Wait, nothing to do |
| Internal queue backed up | Scale up workers |
| Network issues | Check connectivity |
| CPU saturation | Scale up, reduce load |

---

## Communication Templates

### Initial Incident Notification
```
🚨 INCIDENT DETECTED

Severity: SEV[1-4]
Time: [UTC timestamp]
Component: [affected component]
Impact: [what users see]
Status: INVESTIGATING

Current on-call: @name
```

### Status Update
```
📊 INCIDENT UPDATE

Time: [UTC timestamp]
Status: [INVESTIGATING | IDENTIFIED | MONITORING | RESOLVED]
RCA: [brief root cause if known]
Next steps: [what's being done]
ETA to resolution: [if known]
```

### Resolution
```
✅ INCIDENT RESOLVED

Time: [UTC timestamp]
Duration: [total time]
Root cause: [brief summary]
Resolution: [what fixed it]
Postmortem: [scheduled for X / not required]
```

---

## Escalation Path

```
On-call Engineer (5 min)
    ↓ not resolved in 30 min
Tech Lead (notify)
    ↓ not resolved in 1 hour
Engineering Manager
    ↓ SEV1 lasting > 2 hours
VP Engineering / CTO
```

---

## Emergency Contacts

| Role | Contact | When to Use |
|------|---------|-------------|
| On-call Engineer | PagerDuty | First responder |
| Tech Lead | Slack @techlead | Escalation |
| Infrastructure | Slack #infra-oncall | Infra issues |
| Security | security@company.com | Security incidents |

---

## Post-Incident Actions

1. **Document timeline** в Slack/incident channel
2. **Create postmortem** якщо SEV1/SEV2
3. **File follow-up tickets** для preventive measures
4. **Update runbook** якщо знайшов нові патерни

---

*Last updated: 2025-12-02*
*Owner: Principal Observability & Incident Engineer*

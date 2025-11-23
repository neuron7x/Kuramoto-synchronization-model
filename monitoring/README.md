# Monitoring Module

## Overview

The `monitoring` module provides real-time monitoring, alerting, and health check capabilities for TradePulse systems.

## Purpose

- **Health Checks**: System and service health monitoring
- **Alerting**: Real-time alerts for critical events
- **Metrics Collection**: Gather and export performance metrics
- **Dashboards**: Visualization of system state

## Key Features

- 🏥 **Health Endpoints**: HTTP health check endpoints
- 🚨 **Alert Management**: Configurable alerting rules
- 📊 **Metrics Export**: Prometheus-compatible metrics
- 🔔 **Notifications**: Multiple notification channels (email, Slack, PagerDuty)

## Usage Examples

### Health Checks

```python
from monitoring import HealthChecker

checker = HealthChecker()
checker.add_check("database", check_database_connection)
checker.add_check("exchange", check_exchange_connectivity)

status = await checker.check_all()
if status.healthy:
    print("All systems operational")
```

### Alerting

```python
from monitoring import AlertManager, Alert, Severity

alert_mgr = AlertManager()

# Send alert
alert_mgr.send(Alert(
    title="High latency detected",
    message="Order execution latency >500ms",
    severity=Severity.WARNING,
    tags=["execution", "performance"]
))
```

## Configuration

```yaml
# config/monitoring.yaml
monitoring:
  health_checks:
    enabled: true
    interval_seconds: 30
    
  alerts:
    channels:
      - type: slack
        webhook_url: ${SLACK_WEBHOOK}
      - type: email
        recipients: [ops@example.com]
```

## Related Modules

- [`observability`](../observability/README.md): Observability stack
- [`core`](../core/README.md): Core metrics

## Documentation

- [Monitoring Guide](https://docs.tradepulse.io/monitoring)
- [Alerting Guide](https://docs.tradepulse.io/alerting)

## License

See [LICENSE](../LICENSE) for licensing information.

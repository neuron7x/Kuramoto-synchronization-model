# GeoSync L2 collector — systemd deployment

Production-grade long-running Binance USDT-M perp depth@100ms collector
under systemd, with periodic health-check timer. Closes the U1 multi-day
substrate gap documented in PR #240's adversarial review.

## Files

- `geosync-l2-collector.service` — long-running unbounded collector
- `geosync-l2-health.service` — one-shot health probe (exit codes
  classify verdict)
- `geosync-l2-health.timer` — fires the probe every 60s

## Install (Linux, systemd ≥ 240)

1. Clone the repo to `/opt/geosync` (or edit paths in the unit files).
2. Create a venv at `/opt/geosync/.venv` and install dependencies.
3. Copy the three unit files into `/etc/systemd/system/`:

   ```bash
   sudo install -m 0644 deploy/systemd/geosync-l2-collector.service \
       /etc/systemd/system/geosync-l2-collector@<user>.service
   sudo install -m 0644 deploy/systemd/geosync-l2-health.service \
       /etc/systemd/system/geosync-l2-health@<user>.service
   sudo install -m 0644 deploy/systemd/geosync-l2-health.timer \
       /etc/systemd/system/geosync-l2-health@<user>.timer
   ```

4. Enable and start:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now geosync-l2-collector@<user>.service
   sudo systemctl enable --now geosync-l2-health@<user>.timer
   ```

5. Verify:

   ```bash
   systemctl status geosync-l2-collector@<user>.service
   journalctl -u geosync-l2-collector@<user>.service -f
   systemctl list-timers | grep geosync
   ```

## Health verdict taxonomy

| exit | verdict | thresholds |
|---|---|---|
| 0 | HEALTHY | gap_sec < 120 AND disconnects/hr < 10 |
| 1 | DEGRADED | 120 ≤ gap_sec < 600 OR disconnects/hr ≥ 10 |
| 2 | STALE | gap_sec ≥ 3600 |
| 3 | UNREACHABLE | log missing or zero flush lines |

`OnFailure=<alert-unit>` on `geosync-l2-health@<user>.service` wires
alerts to any downstream notifier (systemd-email, ntfy, telegram-send).

## U1 closure criterion

≥10 disjoint 24-hour windows with zero STALE verdicts, zero DNS-outage
downtime > 300s. Measured from `logs/collector_health_history.jsonl`.
Once closed, diurnal filter calibration (U4) unblocks.

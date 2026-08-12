# Automation — systemd units for the cross-asset Kuramoto shadow pipeline

This directory contains **user-level** systemd units that run the
frozen shadow pipeline once per day, append-only. No retries, no hidden
error suppression; failed runs surface as non-zero exit codes and
append to `operational_incidents.csv`.

## Files

- `cross_asset_kuramoto_shadow.service` — one-shot unit wrapping the
  three entry-point scripts (runner → evaluator → renderer) in order.
  `ExecStartPost` is used so that a failing runner aborts the chain
  (instead of `MultiExec`).
- `cross_asset_kuramoto_shadow.timer` — fires daily at **22:00 UTC**
  (locked rebalance clock 21:00 UTC + 1 h buffer for data ingestion).
  `Persistent=true` so catch-up runs are executed after long offline
  intervals; the runner is idempotent against already-written daily
  directories, so catch-up is safe.

## Install (user scope, no root)

```
mkdir -p ~/.config/systemd/user
cp ops/systemd/cross_asset_kuramoto_shadow.service ~/.config/systemd/user/
cp ops/systemd/cross_asset_kuramoto_shadow.timer   ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now cross_asset_kuramoto_shadow.timer
systemctl --user list-timers --all | grep cross_asset
```

## Uninstall

```
systemctl --user disable --now cross_asset_kuramoto_shadow.timer
rm ~/.config/systemd/user/cross_asset_kuramoto_shadow.{service,timer}
systemctl --user daemon-reload
```

## Verification

```
systemctl --user status cross_asset_kuramoto_shadow.service
journalctl --user -u cross_asset_kuramoto_shadow.service --since "24h ago"
tail -n 50 results/cross_asset_kuramoto/shadow_validation/daily/systemd.out.log
tail -n 20 results/cross_asset_kuramoto/shadow_validation/operational_incidents.csv
```

## Non-negotiables enforced by these units

- `Restart=no` — failed runs surface as operational incidents, never
  silent retry.
- `NoNewPrivileges=true`, `ProtectSystem=strict`,
  `ReadWritePaths=...shadow_validation` — the unit cannot modify
  anything outside the shadow directory (and a cache dir).
- No network dependency. The runner explicitly does not make network
  calls; `network-online.target` is used only as an ordering hint for
  hosts that boot the unit at machine-startup time.
- `WantedBy=default.target` for the service and `timers.target` for
  the timer — standard user-unit install path.

## Operational contract

- A failed run MUST append at least one row to
  `operational_incidents.csv` (the runner does this internally on any
  fail-closed exit).
- A run that finds the dated directory already populated is a valid
  no-op — expected behaviour when catching up.
- No unit here authorises capital deployment. The `gate_decision`
  column of `live_scoreboard.csv` is advisory.

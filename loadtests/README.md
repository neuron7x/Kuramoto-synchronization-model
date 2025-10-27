# TradePulse Load Testing

This directory contains utilities for exercising the TradePulse services under load
using [Locust](https://locust.io/).

## Prerequisites

* Install the development requirements (includes Locust):
  ```bash
  pip install -r requirements-dev.txt
  ```
* Ensure the FastAPI service and the gRPC trading stub used for the tests are
  running locally. Deterministic, load-test friendly variants are provided in
  this package.

## Start the target services

1. **REST API**
   ```bash
   uvicorn loadtests.service_app:app --host 127.0.0.1 --port 8000
   ```
   The helper app wires deterministic credentials and state directories so the
   standard Locust users can authenticate without additional setup.

2. **gRPC trading service**
   ```bash
   python loadtests/run_grpc_service.py
   ```
   The server replays the market scenario derived from
   `tests/fixtures/recordings/coinbase_btcusd.jsonl` by default. Override the
   `LOADTEST_MARKET_RECORDING` environment variable to supply custom recordings.

## Execute the load tests

Run Locust in headless mode from another shell once the targets are ready:

```bash
locust -f loadtests/locustfile.py --headless \
       --users 40 --spawn-rate 10 --run-time 5m \
       --host http://127.0.0.1:8000 \
       --csv reports/tradepulse_loadtest
```

The tasks are tagged to allow focused scenarios:

* `http` – Online feature and prediction endpoints (`TradeApiUser`).
* `grpc` – Execution-layer gRPC surface (`ExecutionGrpcUser`).
* `backtest` – Backtesting microservice pipeline (`BacktestingUser`).

Use `--tags backtest` (or `--tags http,grpc`) to limit execution to specific
interfaces.

## Validate throughput

After the run completes, validate the captured statistics using the helper
script. It enforces a minimum throughput of 500 requests/second and an error
rate below 5%:

```bash
python loadtests/validate_results.py reports/tradepulse_loadtest_stats.csv
```

Adjust `MIN_REQUESTS_PER_SECOND` or `MAX_ERROR_RATE` inside
`loadtests/validate_results.py` if different SLOs are required for your
environment.

# GeoSync Order Book Model

`markets/orderbook` is now formalized as an **independent market microstructure model**
that can be installed and evolved separately from the rest of the repository.

## Purpose

The package provides a deterministic limit-order-book core and a stream-ingestion
layer for exchange snapshots and diffs. It is intended for:

- execution simulation,
- queue-priority research,
- venue adapter validation,
- and market-microstructure feature generation.

## Public surfaces

- `geosync_orderbook.PriceTimeOrderBook`
- `geosync_orderbook.Order`
- `geosync_orderbook.OrderBookIngestService`
- `geosync_orderbook.ConsistencyValidator`
- `geosync_orderbook.InMemoryMetricsRecorder`

## Local development

```bash
cd markets/orderbook
python -m pip install -e .[test]
pytest tests/test_ingest_streams.py
```

## Internal layout

- `src/core/` — matching engine and price-time queue logic.
- `src/ingest/` — snapshots, diffs, consistency checks, metrics, venue parsers.
- `api/` — OpenAPI description for the model-facing service surface.
- `config/` — package-local configuration notes.
- `tests/` — deterministic unit coverage.

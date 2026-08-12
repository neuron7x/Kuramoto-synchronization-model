# Scaling GeoSync

This guide outlines the architectural and operational changes required to prepare GeoSync for higher throughput and large scale workloads. It complements the existing performance and monitoring guides by describing a phased roadmap that balances immediate wins with long term platform investments.

## 1. Profile and Optimise Critical Paths

Before making invasive changes, establish a clear baseline.

1. **Trace core execution paths**:
   - Use `cProfile` or `pyinstrument` on representative backtests to locate hotspots across `core/indicators`, `core/data`, and `execution`.
   - Capture flamegraphs for CPU-bound sections and leverage `async-profiler` or built-in asyncio debug logging for I/O-bound routines.
2. **Automate regression profiling**:
   - Add profiling targets to `Makefile` (e.g. `make profile-backtest`) that emit comparable reports.
   - Store reports for historical comparison in `reports/performance/`.
3. **Prioritise optimisations**:
   - Optimise the 20% of code responsible for 80% of runtime first, focusing on indicator calculation and market data ingestion.

### Implementation Tips
- Replace Python loops with vectorised NumPy/pandas operations wherever possible. Maintain indicator interfaces but implement accelerated backends (`numba`, `polars`, or `pandas.eval`) for tight loops.
- Consolidate redundant data transformations in `core/data` to avoid repeated conversions between pandas, numpy, and custom classes.
- Introduce `functools.lru_cache` or Redis-backed caches for deterministic indicator outputs keyed by `(symbol, timeframe, parameters)`.

## 2. Introduce Concurrency and Parallelism

GeoSync workloads mix CPU-bound calculations with network and disk I/O. Apply the appropriate concurrency primitives per workload type.

- **I/O-bound** (`core/data` ingestion, REST/WebSocket APIs): migrate synchronous flows to `asyncio` using FastAPI/Starlette and async database drivers. Run under `uvicorn` with workers sized to CPU cores.
- **CPU-bound** (`core/indicators`, heavy simulations): offload to multiprocessing pools or job queues. Provide a worker abstraction that can execute multiple strategies concurrently.
- **Batch and streaming pipelines**: adopt producer/consumer patterns using `asyncio.Queue` internally and pluggable external queues (Redis Streams, RabbitMQ, Kafka) for horizontal scaling.

Document concurrency models and thread-safety requirements in module docstrings to prevent race conditions.

## 3. Containerise Components for Horizontal Scale

Break monolithic execution into deployable services.

| Component | Responsibility | Containerisation Notes |
|-----------|----------------|-------------------------|
| Data Ingestion | Stream and persist market data | Stateless workers pulling from exchanges; use environment variables for credentials. |
| Indicator/Strategy Workers | Compute signals, run backtests | Build a base image with compiled dependencies; enable autoscaling via Kubernetes `HorizontalPodAutoscaler`. |
| Execution Gateway | Place orders, manage risk | Expose gRPC/REST API with health checks; run behind a load balancer. |
| API / UI | Serve dashboards, reports | Prefer async web framework; ensure static assets are CDN-friendly. |

Publish versioned Docker images via CI, tagging by git SHA. Provide Helm charts or Compose files illustrating multi-service deployments.

## 4. Distributed Task Orchestration

Adopt a queue-based architecture so that scale-out is limited only by available workers.

1. **Message broker selection**: Redis Streams for lightweight deployment, RabbitMQ for reliable routing, or Kafka for high-throughput event logs.
2. **Task framework**: Celery, Dramatiq, or custom asyncio workers can dispatch backtests, indicator recalculations, and risk checks.
3. **Idempotent tasks**: Ensure every worker is idempotent and stateless by persisting progress to databases or object storage.
4. **Backpressure and scheduling**: Monitor queue length and processing latency to trigger autoscaling policies.

## 5. Scalable Storage and Data Access

- **Historical market data**: move cold datasets to object storage (S3, GCS) with lifecycle policies; keep hot data on NVMe or memory-mapped files.
- **Analytical queries**: introduce columnar databases such as ClickHouse for fast aggregations; use PostgreSQL for transactional metadata.
- **Schema contracts**: define schemas in `docs/schemas/` (or protobuf for gRPC) and version them to avoid breaking consumers.
- **Caching layer**: colocate Redis near computation clusters for low-latency access to recent candles and computed signals.

### Time-Series Warehouses

- **ClickHouse or TimescaleDB** provide the OLAP layer for tick and bar level series that require millisecond aggregations for
  research dashboards and signal validation.
  - Partition raw ticks by trading day and symbol using `MergeTree` engines (ClickHouse) or hypertables (TimescaleDB) keyed on
    `ts` to preserve ingestion order.
  - Maintain rolling TTL windows (e.g., 30 days of raw ticks, 180 days of minute bars) with automatic eviction policies (`ALTER
    TABLE ... MODIFY TTL` in ClickHouse or `SELECT add_retention_policy(...)` in TimescaleDB).
  - Enable built-in compression (ClickHouse codecs or Timescale columnar compression) once data ages beyond the hot tier to
    minimise storage without sacrificing aggregation speed.
  - Schedule nightly `OPTIMIZE TABLE`/`REORDER` jobs to keep partitions compact and prune unused indices.

### Dataset Manifests for Backtesting

- Publish immutable manifests alongside every curated dataset under `data/manifests/<dataset>.yaml` capturing:
  - semantic version, snapshot timestamp, checksum (SHA256), and upstream source URI;
  - schema hash or contract version to detect incompatible field changes;
  - dependency notes (e.g., signal feature version) that downstream jobs must honour.
- Extend ingestion pipelines to emit the manifest and register it in a catalogue table so backtests can query the latest
  compatible snapshot.
- Before each backtest run, the driver should:
  1. resolve requested dataset versions to manifest records;
  2. verify all manifests share the same trading calendar and clock skew tolerances;
  3. recompute checksums on local artefacts and halt if mismatches are detected.
- Surface manifest mismatches as explicit errors in CLI/CI jobs and provide remediation guidance (refresh dataset, downgrade to
  compatible snapshot, or regenerate features).

## 6. API Gateway and Service Communication

- Standardise service-to-service communication on gRPC or REST with OpenAPI/Protocol Buffers definitions stored in `docs/schemas/`.
- Deploy an API gateway (Nginx, Traefik) with TLS termination, authentication, and request throttling.
- Implement rolling deployment strategies (blue/green or canary) to prevent downtime during upgrades.

## 7. Observability, Reliability, and Autoscaling

- **Monitoring**: instrument services with Prometheus exporters (CPU, memory, queue depth, execution latency). Visualise in Grafana dashboards stored under `docs/assets/dashboards/`.
- **Logging**: standardise structured JSON logs, ship to ELK/OpenSearch for retention.
- **Tracing**: integrate OpenTelemetry to correlate requests across services.
- **Health checks**: expose `/healthz` and `/readyz` endpoints for Kubernetes probes.
- **Autoscaling**: configure Kubernetes HPAs or Docker Swarm scaling rules based on metrics (queue length, CPU usage).
- **Resiliency**: add retry policies, circuit breakers, and graceful shutdown handlers.

## 8. Implementation Roadmap

1. **Baseline performance**: complete profiling, create optimisation backlog, and lock performance targets.
2. **Refactor hotspots**: vectorise top indicators and cache expensive data pulls.
3. **Introduce task queue**: deploy Redis + Celery (or alternative) with separate worker pools for CPU and I/O tasks.
4. **Container orchestration**: produce Dockerfiles per component and orchestrate via Kubernetes or Docker Compose profiles.
5. **Observability foundation**: deploy Prometheus/Grafana stack, add alerting on SLO breaches.
6. **Documentation & runbooks**: update `docs/` with deployment diagrams, scaling runbooks, and operational checklists.

## 9. Checklist for Production Readiness

- [ ] Profiling jobs automated (`make profile-*`).
- [ ] Performance regression guardrails integrated into CI.
- [ ] Containers published and versioned for each service.
- [ ] Message broker and worker tier deployed with autoscaling policies.
- [ ] Monitoring, logging, tracing pipelines operational.
- [ ] Disaster recovery plan documented (backups, restore drills).
- [ ] On-call runbooks and escalation procedures defined.

By following this plan, GeoSync will evolve from a monolithic backtesting toolkit into a scalable, resilient trading platform capable of handling high-throughput workloads and production-grade execution.

# Cache Coherence Abstraction Map (SMT ↔ Runtime)

## Mapping

- `db_write` (Z3) ↔ `MemoryRepository.store_regime(...)` call path in `RegimeService.update_regime`.
- `cache_sync` (Z3) ↔ `RegimeCache.write_through(...)` update path.
- `read_through` (Z3) ↔ `_fetch_latest_state(...)` followed by `write_through(...)` in slow/recovery path.

## Invariants encoded

1. Cache/DB mismatch implies divergent status (coherence safety).
2. Stale snapshots cannot emit action verdicts without read-through safety gate.
3. Sync writes cannot regress cache version.
4. Eventual read-through implies eventual coherence (bounded liveness).
5. HLC happened-before implies monotonic encoded version.

## Explicit non-modeled concerns

- Thread interleavings and race schedules.
- Exception paths from storage/network layers.
- Network partitions and replication lag.
- External clock synchronization failures beyond modeled bounds.
- Prometheus/audit sink backpressure effects.

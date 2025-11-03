# Order Ledger Data Directory

This directory contains persistent order ledger files for crash-safe execution.

## Structure

```
data/ledger/
├── production/          # Production environment ledgers
├── staging/            # Staging environment ledgers
├── development/        # Development environment ledgers
└── archives/           # Archived/compacted ledger segments
```

## File Naming Convention

Ledger files follow this naming pattern:
- `order-ledger-{environment}-{date}.jsonl` - Main ledger file
- `order-ledger-{environment}-{date}.jsonl.snapshots/` - Snapshot directory
- `order-ledger-{environment}-{date}.jsonl.index` - Offset index
- `order-ledger-{environment}-{date}.jsonl.meta.json` - Metadata

## Usage

The order ledger system is automatically initialized by the OrderManagementSystem (OMS).
Files are created on-demand when the OMS starts.

### Default Configuration

```python
from execution.order_ledger import OrderLedger, OrderLedgerConfig

config = OrderLedgerConfig(
    snapshot_interval=500,          # Snapshot every 500 events
    snapshot_retention=8,           # Keep 8 most recent snapshots
    compaction_threshold_events=10_000,  # Compact after 10k events
    max_journal_size=128 * 1024 * 1024,  # 128 MB max size
    corruption_action="read_only",  # Set to read-only on corruption
)

ledger = OrderLedger("data/ledger/production/order-ledger.jsonl", config=config)
```

## Corruption Detection

The ledger system automatically detects corruption through:
- SHA256 digest verification on every event
- Chain integrity checking (previous_digest validation)
- JSON decode error detection

When corruption is detected, the system can:
1. **read_only** (default): Prevent writes, continue reads
2. **truncate**: Auto-remove corrupted data
3. **abort**: Raise exception and halt

## Recovery

Fast recovery is supported via snapshots:

```python
from execution.recovery import recover_from_ledger

ledger, stats = recover_from_ledger("data/ledger/production/order-ledger.jsonl")

print(f"Recovery time: {stats.duration_seconds:.3f}s")
print(f"Events replayed: {stats.events_replayed}")
print(f"Snapshot used: {stats.snapshot_used}")
```

**RTO Target**: ≤ 2 seconds for 10,000 orders (verified in tests)

## Database Persistence

Optional database backends are available for enhanced durability:

### Timescale/PostgreSQL

```python
from execution.ledger_db_backend import TimescaleLedgerBackend

backend = TimescaleLedgerBackend(
    connection_string="postgresql://user:pass@localhost/tradepulse",
    table_name="order_ledger_events"
)
backend.initialize_schema()
```

### ClickHouse

```python
from execution.ledger_db_backend import ClickHouseLedgerBackend

backend = ClickHouseLedgerBackend(
    connection_string="clickhouse://localhost:8123",
    database="tradepulse"
)
backend.initialize_schema()
```

## Monitoring

Key metrics to monitor:
- Ledger file size
- Snapshot count
- Recovery time
- Corruption events
- Compaction frequency

## Backup & Disaster Recovery

Ledger files should be included in regular backups:

```bash
# Backup ledger and snapshots
tar -czf ledger-backup-$(date +%Y%m%d).tar.gz data/ledger/production/

# Verify backup integrity
tar -tzf ledger-backup-20250103.tar.gz
```

For database backends, use native backup tools:
- Timescale: `pg_basebackup` or continuous archiving
- ClickHouse: `clickhouse-backup` utility

## Troubleshooting

### Read-Only Mode

If ledger enters read-only mode due to corruption:

1. Check corruption details:
   ```python
   ledger = OrderLedger("data/ledger/production/order-ledger.jsonl")
   if ledger.is_read_only:
       print(f"Corruption: {ledger.corruption_details}")
   ```

2. Recover to last known good state using snapshots
3. Investigate root cause (disk errors, incomplete writes, etc.)

### Slow Recovery

If recovery exceeds RTO target:

1. Ensure snapshots are enabled and frequent enough
2. Check disk I/O performance
3. Consider compacting old ledger data
4. Evaluate moving to database backend for large volumes

## See Also

- `execution/order_ledger.py` - Core implementation
- `execution/recovery.py` - Recovery utilities
- `execution/ledger_db_backend.py` - Database backends
- `tests/execution/test_ledger_corruption.py` - Corruption detection tests
- `tests/execution/test_recovery_performance.py` - RTO validation tests

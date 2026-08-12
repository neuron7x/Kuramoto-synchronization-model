# ADR-0002: Versioned Market Data Storage Architecture

## Status
Accepted

**Date:** 2025-11-18

**Decision makers:** Principal System Architect, Data Platform Guild, Security Guild

**Related Requirements:** SEC-001

## Context

The system needs to store primary market data streams with full versioning to enable:
- Signal provenance tracking for regulatory compliance
- Data lineage auditing for debugging and forensics
- Protection against data loss through immutable storage
- Reproducibility of backtest results using historical data snapshots

Current limitations:
- No systematic version tracking of raw market data
- Inability to trace which data version produced specific signals
- Risk of data corruption or loss without recovery mechanism
- Compliance gaps for regulatory audits requiring data provenance

The solution must handle:
- High-throughput ingestion (100K+ ticks/second)
- Immutable append-only storage semantics
- Efficient versioned retrieval for backtesting
- Compliance with data retention policies (7+ years)
- Point-in-time recovery for forensic analysis

## Decision

We will implement a **Versioned Market Data Storage System** using:

1. **Iceberg Lakehouse** as the primary storage layer
   - Immutable Parquet files with snapshot isolation
   - Time-travel queries for point-in-time data access
   - Schema evolution without breaking existing queries

2. **Multi-Layer Architecture:**
   - **Hot Layer:** Redis Streams for real-time ingestion buffer (1-hour retention)
   - **Warm Layer:** PostgreSQL with temporal tables for recent data (30-day retention)
   - **Cold Layer:** Iceberg on S3-compatible storage for long-term archive (7+ years)

3. **Version Tracking:**
   - Every data write gets an immutable version ID (UUIDv7 with timestamp)
   - Provenance metadata linking versions to downstream signals
   - Audit log connecting data versions to strategy executions

4. **Storage Organization:**
   ```
   s3://geosync-data/
   ├── market-data/
   │   ├── raw/                    # Unprocessed market feeds
   │   │   ├── binance/
   │   │   │   └── BTCUSDT/
   │   │   │       └── v=<version>/
   │   │   │           └── year=2025/month=11/day=18/*.parquet
   │   │   └── coinbase/...
   │   ├── normalized/             # Standardized OHLCV format
   │   │   └── v=<version>/...
   │   └── enriched/               # With computed features
   │       └── v=<version>/...
   ├── metadata/
   │   └── versions.db             # Version catalog (PostgreSQL)
   └── provenance/
       └── lineage.jsonl           # Data lineage audit trail
   ```

5. **Version Retention Policy:**
   - Hot layer: 1 hour rolling window
   - Warm layer: 30 days with automatic promotion to cold storage
   - Cold layer: 7 years minimum for regulatory compliance
   - Snapshot consolidation: weekly for efficient storage

## Consequences

### Positive
- **Compliance:** Full data provenance enables regulatory audits (MiFID II, SEC Rule 17a-4)
- **Reproducibility:** Time-travel queries ensure backtest reproducibility
- **Disaster Recovery:** Immutable storage prevents data loss
- **Debugging:** Ability to trace signals back to exact data versions
- **Cost Efficiency:** Tiered storage optimizes cost vs. access patterns

### Negative
- **Storage Costs:** Versioning increases storage requirements by 20-30%
- **Query Complexity:** Time-travel queries require understanding of versioning semantics
- **Operational Overhead:** Managing multiple storage tiers adds complexity

### Neutral
- **Write Performance:** Append-only writes maintain high throughput
- **Read Performance:** Recent data in warm layer ensures fast access
- **Compaction:** Periodic compaction required for cold storage optimization

## Alternatives Considered

### Alternative 1: Git-LFS for Data Versioning
**Pros:**
- Familiar version control semantics
- Built-in diff and merge capabilities

**Cons:**
- Not designed for high-throughput streaming data
- Poor performance for large binary files
- No native time-series query optimization

**Reason for rejection:** Not suitable for real-time market data volumes

### Alternative 2: Timescale DB with Hypertables
**Pros:**
- Native time-series optimization
- SQL compatibility
- Built-in compression

**Cons:**
- Limited to single database instance
- Schema changes require downtime
- Higher operational cost than object storage

**Reason for rejection:** Cost and scalability limitations for long-term storage

### Alternative 3: Delta Lake
**Pros:**
- ACID transactions on object storage
- Time travel capabilities
- Schema evolution

**Cons:**
- Fewer ecosystem integrations than Iceberg
- Less mature tooling
- Limited multi-table transaction support

**Reason for rejection:** Iceberg has better ecosystem support and performance

## Implementation

### Required Changes

1. **Iceberg Infrastructure** (`infra/lakehouse/`)
   - Deploy Iceberg catalog (REST or Hive Metastore)
   - Configure S3-compatible storage backend
   - Set up compaction and snapshot expiration policies
   - Implement access control via IAM roles

2. **Ingestion Pipeline** (`core/ingestion/versioned/`)
   - Create versioned writer interface
   - Implement buffering and batching for efficiency
   - Add version metadata stamping
   - Build provenance tracking hooks

3. **Query Layer** (`core/data/versioned/`)
   - Time-travel query API
   - Version resolution service
   - Efficient range scan optimization
   - Cache layer for hot data

4. **Operational Tools** (`tools/data-ops/`)
   - Version catalog management CLI
   - Data quality validation on ingestion
   - Compaction and maintenance automation
   - Retention policy enforcement

### Validation Criteria

1. **Functional Validation:**
   - Can retrieve exact data snapshot from any point in time
   - Provenance correctly links data versions to signals
   - No data loss during layer transitions
   - Schema evolution doesn't break existing queries

2. **Performance Validation:**
   - Ingestion throughput: 100K+ ticks/second sustained
   - Query latency (hot data): < 50ms p99
   - Query latency (warm data): < 200ms p99
   - Query latency (cold data): < 2s p99
   - Storage overhead: < 30% vs. non-versioned

3. **Compliance Validation:**
   - Audit trail completeness: 100% of ingestion events logged
   - Immutability: No modification of historical data possible
   - Retention: All required data available for 7+ years
   - Access control: All data access logged and attributable

### Migration Path

**Phase 1 (Month 1):** Infrastructure setup
- Deploy Iceberg catalog and storage
- Implement ingestion pipeline for test feed (one exchange)
- Build basic query layer
- Validate performance with load tests

**Phase 2 (Month 2):** Full migration
- Migrate all exchange feeds to versioned ingestion
- Backfill historical data from existing sources
- Update all consumers to use versioned queries
- Deploy operational monitoring

**Phase 3 (Month 3):** Optimization and governance
- Implement compaction automation
- Deploy data quality monitoring
- Create compliance audit tooling
- Decommission legacy storage systems

## Related Decisions
- ADR-0001: Fractal Indicator Composition (consumers of versioned data)
- ADR-0004: Data Quality Validation Framework (quality checks on ingestion)
- ADR-0007: Compliance Audit Trail Architecture (uses version metadata)

## References
- [Apache Iceberg Documentation](https://iceberg.apache.org/)
- [MiFID II Data Retention Requirements](https://www.esma.europa.eu/policy-rules/mifid-ii)
- [SEC Rule 17a-4: Electronic Storage](https://www.sec.gov/rules/interp/2003/34-47806.htm)
- SEC-001: Versioned storage requirement from docs/requirements/product_specification.md

## Notes

- UUIDv7 provides time-ordered IDs enabling efficient range scans
- Iceberg's metadata layer enables sub-second query planning for large datasets
- S3 object versioning provides additional layer of immutability
- Parquet compression achieves 10:1 compression ratio for market data
- Weekly snapshot consolidation reduces metadata overhead by 70%
- Hot layer buffer prevents data loss during Iceberg compaction

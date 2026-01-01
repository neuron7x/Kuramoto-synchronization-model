# Feature store retention and validation

The online feature stores back real-time serving with two persistence
backends:

* **Redis** for low-latency access.
* **SQLite** for lightweight, embedded deployments.

Both backends share the same retention primitives implemented in
`core.data.feature_store`:

* `RetentionPolicy.ttl` expires rows that fall outside of the configured
  time-to-live window.
* `RetentionPolicy.max_versions` keeps only the latest *N* rows per
  entity identifier.

The Redis integration now propagates TTL values down to the key-value
store whenever possible. Clients exposing Redis compatible `setex`
semantics inherit automatic key expiry while the in-memory/testing
clients fall back to the existing retention pruning logic.

Offline Delta Lake or Apache Iceberg tables remain the source of truth.
`OfflineStoreValidator` periodically compares the offline snapshot with
the materialised online payloads and raises
`FeatureStoreIntegrityError` whenever mismatches are detected. This
allows production runs to gate deployments on validation checks while
still benefiting from hot storage TTL enforcement.

## Streaming materialisation

Real-time payloads are ingested through the `StreamMaterializer`
utility in `core.data.materialization`. It turns potentially unbounded
streams into deterministic micro-batches that can be reconciled with the
online store safely:

* **Micro-batching** keeps memory utilisation predictable while still
  delivering timely writes to the online store.
* **Checkpointing** persists a digest of each processed batch so that
  replays remain idempotent even when the streaming source delivers data
  with at-least-once semantics.
* **Backfill integration** consults the existing online payload through
  an optional loader hook, preventing duplicate `(entity_id, ts)` rows
  from being written twice.
* **Deterministic deduplication** normalises both stream payloads and
  historical frames before hashing, ensuring consistent behaviour across
  pandas and backend versions.

## Internal topology

<figure markdown>
![Feature store internal topology](assets/feature_store_internals.svg){ width="960" }
<figcaption>Streaming materialisers enforce schema validation, retention policies, and deterministic deduplication before upserting into Redis or SQLite, while the offline validator reconciles lakehouse snapshots.</figcaption>
</figure>

Update the Mermaid source in [`assets/feature_store_internals.mmd`](assets/feature_store_internals.mmd) to regenerate the rendered diagram alongside this page.

## Related model & dataset cards

- [Feature Store Market Snapshot](../datasets/market_feature_snapshot.md)
- [Market Regime Classifier](../model_cards/market_regime_classifier.md)

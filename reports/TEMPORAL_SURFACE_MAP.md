# Temporal Surface Map — 2026-04-18

Every file in production paths that calls a wall-clock or monotonic API directly.
Sprint-1 lands Clock.epoch_ns() as the DI boundary; migrating these sites is the
follow-up work measured against reports/baseline_defects.txt.

## datetime.now(...) call sites (production code)
core/maintenance/backups.py:37:    return datetime.now(timezone.utc)
core/engine/core.py:21:    as_of: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/engine/core.py:31:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/engine/core.py:68:    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/engine/core.py:205:                cycle_started_at = datetime.now(timezone.utc)
core/engine/core.py:256:                completed_at = datetime.now(timezone.utc)
core/security/integrity.py:42:        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
core/ml/pipeline.py:312:                    "generated_at": datetime.now(timezone.utc).isoformat(),
core/ml/pipeline.py:348:        {"payload": payload, "recorded_at": datetime.now(timezone.utc).isoformat()}
core/versioning.py:239:        build_time=datetime.now(timezone.utc),
core/versioning.py:261:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/risk_monitoring/performance_tracker.py:77:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/risk_monitoring/performance_tracker.py:237:        self._time = time_source or (lambda: datetime.now(timezone.utc))
core/risk_monitoring/compliance.py:246:                "reported_at": datetime.now(timezone.utc).isoformat(),
core/risk_monitoring/compliance.py:282:                "reported_at": datetime.now(timezone.utc).isoformat(),
core/risk_monitoring/compliance.py:313:                    "detected_at": datetime.now(timezone.utc).isoformat(),
core/risk_monitoring/compliance.py:331:            timestamp = datetime.now(timezone.utc)
core/risk_monitoring/compliance.py:370:        cutoff = datetime.now(timezone.utc) - self._retention_delta
core/risk_monitoring/compliance.py:464:                timestamp=datetime.now(timezone.utc),
core/risk_monitoring/compliance.py:509:                timestamp=datetime.now(timezone.utc),
core/risk_monitoring/compliance.py:607:                report_id=f"REP-{regulation.value}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
core/risk_monitoring/compliance.py:608:                generated_at=datetime.now(timezone.utc),
core/risk_monitoring/compliance.py:647:            timestamp = datetime.now(timezone.utc)
core/risk_monitoring/framework.py:194:        self._time = time_source or (lambda: datetime.now(timezone.utc))
core/risk_monitoring/fail_safe.py:210:        self._time = time_source or (lambda: datetime.now(timezone.utc))
core/risk_monitoring/stress_detection.py:139:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/risk_monitoring/stress_detection.py:231:        self._time = time_source or (lambda: datetime.now(timezone.utc))
core/risk_monitoring/advanced_risk_manager.py:192:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/risk_monitoring/advanced_risk_manager.py:238:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/risk_monitoring/advanced_risk_manager.py:530:        self._time = time_source or (lambda: datetime.now(timezone.utc))
core/risk_monitoring/adaptive_thresholds.py:114:    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/risk_monitoring/adaptive_thresholds.py:154:        self._time = time_source or (lambda: datetime.now(timezone.utc))
core/interfaces.py:131:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/interfaces.py:209:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/interfaces.py:310:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/interfaces.py:399:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/interfaces.py:492:        return datetime.now(timezone.utc)
core/idempotency/operations.py:79:    first_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/idempotency/operations.py:80:    last_seen_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/idempotency/operations.py:379:        return datetime.now(timezone.utc)
core/utils/slo.py:100:        self._clock = clock or (lambda: datetime.now(timezone.utc))
core/architecture_integrator/component.py:38:    last_check: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/architecture_integrator/component.py:91:    registered_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/architecture_integrator/component.py:92:    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/architecture_integrator/component.py:115:            self.last_updated = datetime.now(timezone.utc)
core/architecture_integrator/component.py:136:            self.last_updated = datetime.now(timezone.utc)
core/architecture_integrator/component.py:155:            self.last_updated = datetime.now(timezone.utc)
core/architecture_integrator/validator.py:37:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/architecture_integrator/validator.py:51:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/architecture_integrator/lifecycle.py:53:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/architecture_integrator/lifecycle.py:80:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/agent/prompting/models.py:252:        timestamp = datetime.now(timezone.utc)
core/errors.py:41:    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
core/data/warehouses/clickhouse.py:399:            "ingest_ts": datetime.now(timezone.utc).isoformat(),
core/data/versioning.py:35:            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
core/data/feature_catalog.py:67:            "created_at": datetime.now(tz=timezone.utc).isoformat(),
core/data/async_ingestion.py:494:                    timestamp=normalize_timestamp(datetime.now(timezone.utc)),
core/data/fingerprint.py:80:        "generated_at": datetime.now(timezone.utc).isoformat(),
core/data/fingerprint.py:99:        "generated_at": datetime.now(timezone.utc).isoformat(),
core/data/fingerprint.py:148:        "recorded_at": datetime.now(timezone.utc).isoformat(),

... 201 total sites.

## time.time_ns / time.monotonic_ns (production)
core/utils/clock.py:53:            mock.patch("time.time_ns", lambda: int(frozen_epoch * 1_000_000_000))
core/utils/clock.py:56:        stack.enter_context(mock.patch("time.monotonic_ns", lambda: 1_000_000_000))
core/architecture_integrator/lifecycle.py:373:        start_time = time.monotonic()
core/architecture_integrator/lifecycle.py:403:            elapsed = time.monotonic() - start_time
core/architecture_integrator/lifecycle.py:461:        total_time = time.monotonic() - start_time
core/agent/sandbox.py:123:        start = time.monotonic()
core/agent/sandbox.py:129:                elapsed = time.monotonic() - start
core/data/dead_letter.py:491:        now = time.monotonic()
core/data/dead_letter.py:503:            self._recent_replays[item.payload_digest] = time.monotonic()
core/data/backfill.py:369:        self._last_check = time.monotonic()
core/data/backfill.py:377:                current = time.monotonic()
src/geosync/core/compat.py:82:    return time.monotonic_ns()
src/geosync/core/compat.py:132:    Equivalent to :func:`time.time_ns` on CPython. Use this only when
src/geosync/core/compat.py:138:    return time.time_ns()
src/audit/audit_logger.py:341:        self._schedule(path, ready_at=time.monotonic())
src/audit/audit_logger.py:345:        self._queue.put((time.monotonic(), next(self._sequence), None))
src/audit/audit_logger.py:358:            self._schedule(path, ready_at=time.monotonic())
src/audit/audit_logger.py:395:            delay = max(0.0, ready_at - time.monotonic())
src/audit/audit_logger.py:489:        self._schedule(pending_path, ready_at=time.monotonic() + retry_delay)
src/mycelium_fractal_net/connectors/metrics.py:104:        self._start_time = time.monotonic()
src/mycelium_fractal_net/connectors/metrics.py:127:            self._last_event_time = time.monotonic()
src/mycelium_fractal_net/connectors/metrics.py:219:        runtime = time.monotonic() - self._start_time
src/mycelium_fractal_net/connectors/metrics.py:249:            self._start_time = time.monotonic()
src/data/kafka_ingestion.py:285:        self.last_seen = time.monotonic()
execution/resilience/circuit_breaker.py:64:            now = time.monotonic()
execution/resilience/circuit_breaker.py:93:            self._last_failure_time = time.monotonic()
execution/resilience/circuit_breaker.py:134:            now = time.monotonic()
execution/resilience/circuit_breaker.py:149:                now = time.monotonic()
execution/resilience/circuit_breaker.py:169:            elapsed = time.monotonic() - self._last_failure_time
execution/resilience/circuit_breaker.py:223:        now = time.monotonic()

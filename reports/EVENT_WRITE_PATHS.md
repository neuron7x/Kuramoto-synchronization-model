# Event Write Paths — 2026-04-18

Every call to PostgresEventStore.append in production paths.
Sprint-2 lands EventValidator; this map is the work queue for plumbing
validators into each caller.

## PostgresEventStore.append call sites
core/ml/pipeline.py:347:    events.append(
core/events/sourcing.py:238:        self._pending_events.append(event)
core/events/sourcing.py:897:            envelopes.append(
core/events/sourcing.py:932:                    envelopes.append(
core/events/sourcing.py:1066:            timeline.append(timeline_entry)
core/utils/slo.py:144:        self._events.append(RequestSample(event_time, float(latency_ms), success))
core/data/connectors/market.py:92:                events.append(event)
core/data/connectors/market.py:342:                events.append(event)
core/strategies/fete_runtime.py:402:            self.events.append(RiskEvent(timestamp, "reset", "Risk guard reset"))
core/strategies/fete_runtime.py:405:        self.events.append(RiskEvent(timestamp, code, message))
core/neuro/serotonin/profiler/behavioral_profiler.py:378:            self._veto_events.append(
core/neuro/serotonin/profiler/behavioral_profiler.py:409:                    self._cooldown_events.append({"max_duration": cooldown_s})
core/neuro/serotonin/profiler/behavioral_profiler.py:412:            self._cooldown_events.append({})
src/geosync/sdk/engine.py:286:        state.events.append(entry)
src/geosync/core/neuro/serotonin/serotonin_controller.py:1481:        self._trace_events.append(json.dumps(event, separators=(",", ":")))
src/mycelium_fractal_net/connectors/rest_source.py:225:                    events.append(
src/mycelium_fractal_net/connectors/rest_source.py:239:                        events.append(
src/mycelium_fractal_net/connectors/rest_source.py:251:                        events.append(
src/mycelium_fractal_net/connectors/rest_source.py:262:                events.append(
src/system/module_orchestrator.py:230:            events.append((entry.started_at, 1))
src/system/module_orchestrator.py:231:            events.append((entry.completed_at, -1))
execution/adapters/base.py:120:                    self._events.append((now, weight))
observability/drift.py:461:            self._events.append((timestamp, drifted))
observability/model_monitoring.py:488:        self._events.append(label)
observability/model_monitoring.py:600:        self._inference_events.append((now, success))

## store.append discovery (broader)

## direct references to PostgresEventStore
core/events/validation.py:6:protocol invoked inside ``PostgresEventStore.append`` *before* the
core/events/validation.py:82:    """Semantic admission gate invoked by :meth:`PostgresEventStore.append`.
core/events/sourcing.py:86:    "PostgresEventStore",
core/events/sourcing.py:705:class PostgresEventStore:
core/events/sourcing.py:1030:    def __init__(self, store: PostgresEventStore) -> None:
core/events/sourcing.py:1078:    def __init__(self, store: PostgresEventStore) -> None:

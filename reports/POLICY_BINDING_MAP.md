# Policy Binding Map — 2026-04-18

Static policy construction sites that would benefit from runtime hot-swap.
Sprint-4 lands ModulationPolicy + RegimeModulator.swap_policy;
other services (Kuramoto, execution, risk) may need parallel splits.

## RegimeModulator instantiations
cortex_service/app/services/regime_service.py:362:        self._modulator = RegimeModulator(settings)

## Static policy/strategy constructions in runtime paths
core/compliance/mifid2.py:123:        self._retention = retention or MiFID2RetentionPolicy()
core/utils/cache.py:91:class TTLStrategy(ABC):
core/utils/cache.py:109:class AdaptiveTTLStrategy(TTLStrategy):
core/utils/cache.py:161:class EvictionPolicy(ABC):
core/utils/cache.py:189:class LRUEvictionPolicy(EvictionPolicy):
core/utils/cache.py:226:class LFUEvictionPolicy(EvictionPolicy):
core/utils/cache.py:739:            ttl_strategy=AdaptiveTTLStrategy(base_ttl=30.0, max_ttl=300.0),
core/utils/cache.py:740:            eviction_policy=LRUEvictionPolicy(),
core/utils/cache.py:747:            ttl_strategy=AdaptiveTTLStrategy(base_ttl=300.0, max_ttl=3600.0),
core/utils/cache.py:748:            eviction_policy=LFUEvictionPolicy(),
core/agent/strategy.py:29:    >>> strategy = Strategy("mean_reversion", {"lookback": 20, "threshold": 2.0})
core/agent/strategy.py:65:        mutated = Strategy(name=f"{self.name}_mut", params=new_params)
core/data/adapters/base.py:176:        self._policy = FaultTolerancePolicy(
core/data/adapters/unified.py:243:        self._backoff = backoff or BackoffPolicy()
core/data/signal_filter.py:51:class FilterStrategy(str, Enum):
core/config/registry.py:147:class CompatibilityPolicy(Protocol):
core/strategies/engine.py:263:class RiskPolicy(Protocol):
core/strategies/engine.py:330:        self._risk_policy = risk_policy or AcceptAllRiskPolicy()
core/strategies/trading.py:37:class KuramotoStrategy(TradingStrategy):
core/strategies/trading.py:99:class HurstVPINStrategy(TradingStrategy):
core/neuro/shocks.py:48:    class _ShockPolicy(nn.Module):  # type: ignore[misc]
core/neuro/shocks.py:114:        self._policy = _ShockPolicy(feature_dim).to(self._device)
src/geosync/live/__init__.py:33:class Strategy(Protocol):
src/data/knowledge/subsystem.py:61:        self._freshness = FreshnessPolicy(self._config.freshness_half_life_days)
src/data/pipeline.py:33:class TickRoutingStrategy(Protocol):

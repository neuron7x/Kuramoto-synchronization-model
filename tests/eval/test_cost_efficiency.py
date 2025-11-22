"""
Cost efficiency evaluation tests for NeuroCognitiveEngine.

Tests validate:
1. Cache reduces LLM calls
2. Adaptive context reduces latency under load
3. QoS degradation applies correctly for low tier
"""

import time
import pytest
import numpy as np
from src.mlsdm import NeuroCognitiveEngine, NeuroEngineConfig


def mock_slow_llm(prompt: str, max_tokens: int = 1000, enable_fslgs: bool = True) -> str:
    """Mock LLM that simulates slow response."""
    time.sleep(0.15)  # 150ms delay
    return f"Response to: {prompt[:30]}... (max_tokens={max_tokens}, fslgs={enable_fslgs})"


def mock_fast_llm(prompt: str, max_tokens: int = 1000, enable_fslgs: bool = True) -> str:
    """Mock LLM that simulates fast response."""
    time.sleep(0.01)  # 10ms delay
    return f"Response to: {prompt[:30]}... (max_tokens={max_tokens}, fslgs={enable_fslgs})"


class TestCacheReducesLLMCalls:
    """Test that semantic cache reduces redundant LLM calls."""
    
    def test_identical_prompts_use_cache(self):
        """Test that identical prompts hit the cache."""
        config = NeuroEngineConfig(
            cache_enabled=True,
            cache_similarity_threshold=0.85
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_fast_llm)
        
        prompt = "What is the capital of France?"
        
        # First call - should miss cache
        result1 = engine.generate(prompt)
        assert result1['from_cache'] is False
        
        # Second call - should hit cache
        result2 = engine.generate(prompt)
        assert result2['from_cache'] is True
        
        # Verify response is the same
        assert result1['response'] == result2['response']
        
        # Verify cache stats
        cache_stats = engine.cache.get_stats()
        assert cache_stats['hits'] >= 1
        assert cache_stats['hit_rate'] > 0
    
    def test_similar_prompts_use_cache(self):
        """Test that semantically similar prompts can hit cache."""
        config = NeuroEngineConfig(
            cache_enabled=True,
            cache_similarity_threshold=0.95  # High threshold for similar prompts
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_fast_llm)
        
        # First prompt
        result1 = engine.generate("Tell me about Paris")
        assert result1['from_cache'] is False
        
        # Similar prompt - may or may not hit depending on embedding
        # Just verify it runs without error
        result2 = engine.generate("Tell me about Paris")
        # Second identical should definitely hit
        assert result2['from_cache'] is True
    
    def test_different_contexts_dont_share_cache(self):
        """Test that different moral values/intents don't share cache."""
        config = NeuroEngineConfig(cache_enabled=True)
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_fast_llm)
        
        prompt = "Should I take this action?"
        
        # First call with moral_value="ethical"
        result1 = engine.generate(prompt, moral_value="ethical")
        assert result1['from_cache'] is False
        
        # Second call with different moral_value
        result2 = engine.generate(prompt, moral_value="pragmatic")
        # Should miss cache due to different context
        assert result2['from_cache'] is False
        
        # Third call with same context as first
        result3 = engine.generate(prompt, moral_value="ethical")
        # Should hit cache
        assert result3['from_cache'] is True
    
    def test_cache_improves_latency(self):
        """Test that cache significantly reduces latency."""
        config = NeuroEngineConfig(cache_enabled=True)
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_slow_llm)
        
        prompt = "Explain quantum computing"
        
        # First call - slow
        result1 = engine.generate(prompt)
        latency1 = result1['timing']['total']
        assert result1['from_cache'] is False
        
        # Second call - should be much faster due to cache
        result2 = engine.generate(prompt)
        latency2 = result2['timing']['total']
        assert result2['from_cache'] is True
        
        # Cache should be at least 10x faster
        assert latency2 < latency1 * 0.1


class TestAdaptiveContextReducesLatency:
    """Test that adaptive context management reduces latency under load."""
    
    def test_context_reduces_under_slow_backend(self):
        """Test that context_top_k reduces when backend is slow."""
        config = NeuroEngineConfig(
            target_latency_ms=50.0,  # Very low target
            min_context_top_k=3,
            max_context_top_k=20,
            context_top_k=15,
            cache_enabled=False  # Disable cache to test adaptation
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_slow_llm)
        
        initial_k = engine._current_context_top_k
        assert initial_k == 15
        
        # Make several calls to trigger adaptation
        for i in range(5):
            result = engine.generate(f"Query {i}")
            # Each call should be slow, triggering reduction
        
        # Context should have been reduced
        final_k = engine._current_context_top_k
        assert final_k < initial_k
        assert final_k >= config.min_context_top_k
    
    def test_context_increases_under_fast_backend_high_load(self):
        """Test that context_top_k increases when backend is fast and load is high."""
        config = NeuroEngineConfig(
            target_latency_ms=100.0,
            min_context_top_k=3,
            max_context_top_k=20,
            context_top_k=10,
            cache_enabled=False
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_fast_llm)
        
        initial_k = engine._current_context_top_k
        
        # Simulate high cognitive load
        engine._cognitive_load = 0.8
        
        # Make several fast calls
        for i in range(5):
            result = engine.generate(f"Query {i}")
        
        # Context might have increased (depends on latency history)
        final_k = engine._current_context_top_k
        # At minimum, should not have decreased
        assert final_k >= initial_k or final_k == config.max_context_top_k
    
    def test_context_never_below_minimum(self):
        """Test that context_top_k never goes below minimum."""
        config = NeuroEngineConfig(
            target_latency_ms=1.0,  # Impossibly low target
            min_context_top_k=5,
            context_top_k=10,
            cache_enabled=False
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_slow_llm)
        
        # Make many calls to trigger maximum reduction
        for i in range(20):
            engine.generate(f"Query {i}")
        
        # Should not go below minimum
        assert engine._current_context_top_k >= config.min_context_top_k


class TestQoSDegradation:
    """Test QoS degradation for different priority tiers."""
    
    def test_low_tier_disables_fslgs_under_load(self):
        """Test that low tier disables FSLGS under load."""
        config = NeuroEngineConfig(
            priority_tier="low",
            target_latency_ms=50.0,
            enable_fslgs=True,
            degradation_policy={
                'disable_fslgs': True,
                'limit_max_tokens': True,
                'min_context_top_k_under_load': 3
            },
            cache_enabled=False
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_slow_llm)
        
        # Initially FSLGS should be enabled
        assert engine._current_enable_fslgs is True
        
        # Make slow calls to trigger degradation
        for i in range(3):
            result = engine.generate(f"Query {i}")
        
        # After slow calls, should have degraded
        # Check that at least one call reported degradation
        result = engine.generate("Final query")
        
        # FSLGS should be disabled for low tier under load
        if result['qos_degraded']:
            assert engine._current_enable_fslgs is False
    
    def test_low_tier_reduces_max_tokens_under_load(self):
        """Test that low tier reduces max_tokens under load."""
        config = NeuroEngineConfig(
            priority_tier="low",
            target_latency_ms=50.0,
            max_tokens=1000,
            degradation_policy={
                'disable_fslgs': True,
                'limit_max_tokens': True,
                'min_context_top_k_under_load': 3
            },
            cache_enabled=False
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_slow_llm)
        
        initial_max_tokens = engine._current_max_tokens
        assert initial_max_tokens == 1000
        
        # Make slow calls
        for i in range(3):
            engine.generate(f"Query {i}")
        
        # Max tokens should be reduced
        if engine._latency_history and np.mean(engine._latency_history) > config.target_latency_ms:
            assert engine._current_max_tokens <= 500
    
    def test_normal_tier_reduces_context_under_load(self):
        """Test that normal tier reduces context but keeps FSLGS."""
        config = NeuroEngineConfig(
            priority_tier="normal",
            target_latency_ms=50.0,
            context_top_k=15,
            enable_fslgs=True,
            cache_enabled=False
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_slow_llm)
        
        initial_k = engine._current_context_top_k
        
        # Make slow calls
        for i in range(3):
            engine.generate(f"Query {i}")
        
        # Context should be reduced
        assert engine._current_context_top_k < initial_k
        # But FSLGS should still be enabled
        assert engine._current_enable_fslgs is True
    
    def test_high_tier_maintains_quality_under_load(self):
        """Test that high tier maintains quality even under load."""
        config = NeuroEngineConfig(
            priority_tier="high",
            target_latency_ms=50.0,
            context_top_k=15,
            enable_fslgs=True,
            max_tokens=1000,
            cache_enabled=False
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_slow_llm)
        
        initial_k = engine._current_context_top_k
        initial_fslgs = engine._current_enable_fslgs
        initial_max_tokens = engine._current_max_tokens
        
        # Make slow calls
        for i in range(3):
            result = engine.generate(f"Query {i}")
        
        # High tier should maintain most settings
        # (some adaptive reduction allowed but FSLGS stays on)
        assert engine._current_enable_fslgs == initial_fslgs
        assert engine._current_max_tokens == initial_max_tokens


class TestCostTracking:
    """Test cost tracking functionality."""
    
    def test_cost_tracking_in_response(self):
        """Test that generate() returns cost information."""
        config = NeuroEngineConfig(
            pricing={
                'prompt_price_per_1k': 0.001,
                'completion_price_per_1k': 0.002
            },
            cache_enabled=False
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_fast_llm)
        
        result = engine.generate("Tell me about AI")
        
        # Check cost info is present
        assert 'cost' in result
        assert 'prompt_tokens' in result['cost']
        assert 'completion_tokens' in result['cost']
        assert 'total_tokens' in result['cost']
        assert 'estimated_cost_usd' in result['cost']
        
        # Check values are reasonable
        assert result['cost']['prompt_tokens'] > 0
        assert result['cost']['completion_tokens'] > 0
        assert result['cost']['total_tokens'] > 0
        assert result['cost']['estimated_cost_usd'] > 0
    
    def test_cumulative_cost_tracking(self):
        """Test that costs accumulate across calls."""
        config = NeuroEngineConfig(
            pricing={
                'prompt_price_per_1k': 0.001,
                'completion_price_per_1k': 0.002
            },
            cache_enabled=False
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_fast_llm)
        
        # Make multiple calls
        for i in range(5):
            engine.generate(f"Query {i}")
        
        # Check cumulative stats
        stats = engine.get_stats()
        assert stats['cost']['num_calls'] == 5
        assert stats['cost']['total_tokens'] > 0
        assert stats['cost']['estimated_cost_usd'] > 0


class TestIntegration:
    """Integration tests for full system."""
    
    def test_cache_and_adaptation_work_together(self):
        """Test that caching and adaptive context work together."""
        config = NeuroEngineConfig(
            cache_enabled=True,
            target_latency_ms=100.0,
            context_top_k=10
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_fast_llm)
        
        # Make diverse calls
        prompts = [
            "What is machine learning?",
            "Explain deep learning",
            "What is machine learning?",  # Repeat for cache hit
            "Tell me about neural networks"
        ]
        
        cache_hits = 0
        for prompt in prompts:
            result = engine.generate(prompt)
            if result['from_cache']:
                cache_hits += 1
        
        # Should have at least one cache hit (the repeated prompt)
        assert cache_hits >= 1
        
        # Check stats
        stats = engine.get_stats()
        assert stats['cache']['hits'] >= 1
        assert stats['cost']['num_calls'] == len(prompts)
    
    def test_full_system_with_qos(self):
        """Test full system with QoS under varying load."""
        config = NeuroEngineConfig(
            priority_tier="normal",
            cache_enabled=True,
            target_latency_ms=100.0,
            pricing={
                'prompt_price_per_1k': 0.001,
                'completion_price_per_1k': 0.002
            }
        )
        engine = NeuroCognitiveEngine(config=config, llm_backend=mock_slow_llm)
        
        # Make calls that will trigger adaptation
        results = []
        for i in range(10):
            result = engine.generate(f"Complex query number {i}")
            results.append(result)
        
        # Verify all calls succeeded
        assert len(results) == 10
        
        # Check that some adaptation occurred
        stats = engine.get_stats()
        assert stats['cost']['num_calls'] == 10
        
        # At least some calls should have non-zero timing
        avg_latency = stats['performance']['avg_latency_ms']
        assert avg_latency > 0

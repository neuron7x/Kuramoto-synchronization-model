"""
Example usage of the MLSDM NeuroCognitiveEngine.

This file demonstrates various usage patterns and features.
"""

import time
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.mlsdm import NeuroCognitiveEngine, NeuroEngineConfig


def example_mock_llm(prompt: str, max_tokens: int = 1000, enable_fslgs: bool = True) -> str:
    """
    Mock LLM backend for demonstration purposes.
    
    In production, replace this with your actual LLM integration
    (OpenAI, Anthropic, local model, etc.)
    """
    time.sleep(0.1)  # Simulate API latency
    return f"This is a generated response to the prompt: '{prompt[:50]}...'"


def example_1_basic_usage():
    """Example 1: Basic usage with default configuration."""
    print("\n=== Example 1: Basic Usage ===\n")
    
    # Create engine with default config
    engine = NeuroCognitiveEngine(llm_backend=example_mock_llm)
    
    # Generate a response
    result = engine.generate("What is the meaning of life?")
    
    print(f"Response: {result['response']}")
    print(f"From cache: {result['from_cache']}")
    print(f"Latency: {result['timing']['total']:.2f}ms")
    print(f"Tokens: {result['cost']['total_tokens']}")


def example_2_cost_tracking():
    """Example 2: Cost tracking with pricing configuration."""
    print("\n=== Example 2: Cost Tracking ===\n")
    
    config = NeuroEngineConfig(
        pricing={
            'prompt_price_per_1k': 0.0015,  # $1.50 per 1M prompt tokens
            'completion_price_per_1k': 0.002  # $2.00 per 1M completion tokens
        }
    )
    engine = NeuroCognitiveEngine(config=config, llm_backend=example_mock_llm)
    
    # Make several API calls
    prompts = [
        "Explain quantum computing",
        "What is machine learning?",
        "How do neural networks work?",
        "Describe deep learning"
    ]
    
    for prompt in prompts:
        result = engine.generate(prompt)
        print(f"Query: {prompt[:40]}...")
        print(f"  Cost: ${result['cost']['estimated_cost_usd']:.6f}")
        print(f"  Tokens: {result['cost']['total_tokens']}")
    
    # Get cumulative statistics
    stats = engine.get_stats()
    print(f"\nTotal calls: {stats['cost']['num_calls']}")
    print(f"Total tokens: {stats['cost']['total_tokens']}")
    print(f"Total cost: ${stats['cost']['estimated_cost_usd']:.6f}")


def example_3_semantic_caching():
    """Example 3: Semantic caching to reduce redundant calls."""
    print("\n=== Example 3: Semantic Caching ===\n")
    
    config = NeuroEngineConfig(
        cache_enabled=True,
        cache_similarity_threshold=0.85
    )
    engine = NeuroCognitiveEngine(config=config, llm_backend=example_mock_llm)
    
    # First query - will miss cache
    print("First query (cache miss):")
    result1 = engine.generate("What is Python?")
    print(f"  From cache: {result1['from_cache']}")
    print(f"  Latency: {result1['timing']['total']:.2f}ms")
    
    # Identical query - will hit cache
    print("\nSecond query (cache hit):")
    result2 = engine.generate("What is Python?")
    print(f"  From cache: {result2['from_cache']}")
    print(f"  Latency: {result2['timing']['total']:.2f}ms")
    print(f"  Speedup: {result1['timing']['total'] / result2['timing']['total']:.1f}x")
    
    # Check cache statistics
    cache_stats = engine.cache.get_stats()
    print(f"\nCache statistics:")
    print(f"  Hits: {cache_stats['hits']}")
    print(f"  Misses: {cache_stats['misses']}")
    print(f"  Hit rate: {cache_stats['hit_rate']:.1%}")


def example_4_context_aware_caching():
    """Example 4: Context-aware caching with moral values and intents."""
    print("\n=== Example 4: Context-Aware Caching ===\n")
    
    engine = NeuroCognitiveEngine(llm_backend=example_mock_llm)
    
    prompt = "Should I invest in this opportunity?"
    
    # Same prompt, different moral contexts
    print("Query 1: Risk-averse context")
    result1 = engine.generate(
        prompt,
        moral_value="risk_averse",
        user_intent="protect_capital"
    )
    print(f"  From cache: {result1['from_cache']}")
    
    print("\nQuery 2: Growth-oriented context")
    result2 = engine.generate(
        prompt,
        moral_value="growth_oriented",
        user_intent="maximize_returns"
    )
    print(f"  From cache: {result2['from_cache']}")  # Should miss - different context
    
    print("\nQuery 3: Risk-averse context (repeat)")
    result3 = engine.generate(
        prompt,
        moral_value="risk_averse",
        user_intent="protect_capital"
    )
    print(f"  From cache: {result3['from_cache']}")  # Should hit - same context


def example_5_adaptive_context():
    """Example 5: Adaptive context management under load."""
    print("\n=== Example 5: Adaptive Context Management ===\n")
    
    def slow_llm(prompt, max_tokens, enable_fslgs):
        """Simulate a slow LLM backend."""
        time.sleep(0.2)  # 200ms latency
        return f"Response to: {prompt[:30]}"
    
    config = NeuroEngineConfig(
        target_latency_ms=100.0,  # Target 100ms
        min_context_top_k=3,
        max_context_top_k=20,
        context_top_k=15,
        cache_enabled=False  # Disable cache to see adaptation
    )
    engine = NeuroCognitiveEngine(config=config, llm_backend=slow_llm)
    
    print(f"Initial context_top_k: {engine._current_context_top_k}")
    
    # Make several calls - should trigger adaptation
    for i in range(5):
        result = engine.generate(f"Query {i}")
        print(f"Call {i+1}: context_top_k={result['context_top_k']}, "
              f"latency={result['timing']['total']:.1f}ms")
    
    print(f"\nFinal context_top_k: {engine._current_context_top_k}")
    print("Context was reduced to meet latency target!")


def example_6_qos_degradation():
    """Example 6: QoS degradation for different priority tiers."""
    print("\n=== Example 6: QoS Degradation ===\n")
    
    def slow_llm(prompt, max_tokens, enable_fslgs):
        time.sleep(0.15)
        return f"Response (max_tokens={max_tokens}, fslgs={enable_fslgs})"
    
    # Low priority configuration
    config_low = NeuroEngineConfig(
        priority_tier="low",
        target_latency_ms=50.0,  # Strict target
        enable_fslgs=True,
        max_tokens=1000,
        cache_enabled=False
    )
    engine_low = NeuroCognitiveEngine(config=config_low, llm_backend=slow_llm)
    
    print("Low priority tier under load:")
    for i in range(3):
        result = engine_low.generate(f"Query {i}")
        print(f"  Call {i+1}: degraded={result['qos_degraded']}, "
              f"fslgs={result['enable_fslgs']}")
    
    # High priority configuration
    config_high = NeuroEngineConfig(
        priority_tier="high",
        target_latency_ms=50.0,
        enable_fslgs=True,
        cache_enabled=False
    )
    engine_high = NeuroCognitiveEngine(config=config_high, llm_backend=slow_llm)
    
    print("\nHigh priority tier under load:")
    for i in range(3):
        result = engine_high.generate(f"Query {i}")
        print(f"  Call {i+1}: degraded={result['qos_degraded']}, "
              f"fslgs={result['enable_fslgs']}")
    
    print("\nLow tier degrades aggressively, high tier maintains quality!")


def example_7_complete_workflow():
    """Example 7: Complete workflow with all features."""
    print("\n=== Example 7: Complete Workflow ===\n")
    
    config = NeuroEngineConfig(
        # Context management
        min_context_top_k=5,
        max_context_top_k=20,
        context_top_k=10,
        target_latency_ms=150.0,
        
        # QoS
        priority_tier="normal",
        enable_fslgs=True,
        
        # Caching
        cache_enabled=True,
        cache_max_entries=500,
        cache_similarity_threshold=0.85,
        
        # Cost tracking
        pricing={
            'prompt_price_per_1k': 0.001,
            'completion_price_per_1k': 0.002
        }
    )
    
    engine = NeuroCognitiveEngine(config=config, llm_backend=example_mock_llm)
    
    # Simulate a typical workload
    queries = [
        "What are the key market trends?",
        "Explain technical analysis",
        "What are the key market trends?",  # Repeat
        "How to manage risk?",
        "Explain technical analysis",  # Repeat
        "What is portfolio optimization?",
    ]
    
    print("Processing queries:")
    for i, query in enumerate(queries, 1):
        result = engine.generate(query)
        print(f"{i}. {query[:35]:.<35} "
              f"cached={'✓' if result['from_cache'] else '✗'} "
              f"cost=${result['cost']['estimated_cost_usd']:.6f}")
    
    # Final statistics
    stats = engine.get_stats()
    print(f"\n{'='*50}")
    print(f"Summary:")
    print(f"  Total queries: {stats['cost']['num_calls']}")
    print(f"  Cache hits: {stats['cache']['hits']}")
    print(f"  Hit rate: {stats['cache']['hit_rate']:.1%}")
    print(f"  Total cost: ${stats['cost']['estimated_cost_usd']:.6f}")
    print(f"  Avg latency: {stats['performance']['avg_latency_ms']:.1f}ms")
    print(f"  Current context_top_k: {stats['performance']['current_context_top_k']}")


def main():
    """Run all examples."""
    print("=" * 70)
    print("MLSDM NeuroCognitiveEngine Examples")
    print("=" * 70)
    
    example_1_basic_usage()
    example_2_cost_tracking()
    example_3_semantic_caching()
    example_4_context_aware_caching()
    example_5_adaptive_context()
    example_6_qos_degradation()
    example_7_complete_workflow()
    
    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    main()

"""
NeuroCognitiveEngine - Main engine with cost efficiency and QoS.

This module implements the cognitive engine with:
- Cost tracking
- Semantic caching
- Adaptive context management
- QoS and graceful degradation
"""

import time
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, Optional, Literal, Callable, List
from collections import deque

from .observability.cost import CostTracker, estimate_tokens
from .memory.semantic_cache import SemanticResponseCache


@dataclass
class NeuroEngineConfig:
    """
    Configuration for NeuroCognitiveEngine.

    Attributes:
        # Context management
        min_context_top_k: Minimum number of context items to retrieve
        max_context_top_k: Maximum number of context items to retrieve
        context_top_k: Default number of context items
        max_memory_tokens: Maximum tokens to keep in memory before summarization
        
        # Performance targets
        target_latency_ms: Target latency in milliseconds
        
        # QoS settings
        priority_tier: Priority level for this engine
        degradation_policy: Policy for degrading under load
        
        # FSLGS (Few-Shot Learning Grounding System)
        enable_fslgs: Whether to enable FSLGS
        
        # Cost tracking
        pricing: Pricing information for token costs
        
        # Caching
        cache_enabled: Whether to enable semantic caching
        cache_max_entries: Maximum cache entries
        cache_similarity_threshold: Similarity threshold for cache hits
    """
    
    # Context management
    min_context_top_k: int = 3
    max_context_top_k: int = 20
    context_top_k: int = 10
    max_memory_tokens: int = 10000
    
    # Performance targets
    target_latency_ms: float = 1000.0
    
    # QoS settings
    priority_tier: Literal["low", "normal", "high"] = "normal"
    degradation_policy: Dict = field(default_factory=lambda: {
        'disable_fslgs': True,
        'limit_max_tokens': True,
        'min_context_top_k_under_load': 3
    })
    
    # FSLGS
    enable_fslgs: bool = True
    
    # Cost tracking
    pricing: Optional[Dict[str, float]] = None
    
    # Caching
    cache_enabled: bool = True
    cache_max_entries: int = 1000
    cache_similarity_threshold: float = 0.85
    
    # Token limits
    max_tokens: int = 1000


class NeuroCognitiveEngine:
    """
    Cognitive engine with cost efficiency, caching, and QoS.

    This engine provides:
    - Token and cost tracking for all LLM calls
    - Semantic caching to reduce redundant API calls
    - Adaptive context management based on latency
    - QoS with graceful degradation under load
    """
    
    def __init__(
        self,
        config: Optional[NeuroEngineConfig] = None,
        llm_backend: Optional[Callable] = None,
        embedding_fn: Optional[Callable] = None
    ):
        """
        Initialize the cognitive engine.

        Args:
            config: Engine configuration
            llm_backend: Optional LLM backend function (prompt -> response)
            embedding_fn: Optional embedding function (text -> np.ndarray)
        """
        self.config = config or NeuroEngineConfig()
        self.llm_backend = llm_backend
        self.embedding_fn = embedding_fn or self._default_embedding
        
        # Initialize components
        self.cost_tracker = CostTracker()
        self.cache = None
        if self.config.cache_enabled:
            self.cache = SemanticResponseCache(
                max_entries=self.config.cache_max_entries,
                similarity_threshold=self.config.cache_similarity_threshold
            )
        
        # Performance tracking
        self._latency_history: deque = deque(maxlen=10)
        self._cognitive_load = 0.0
        
        # Current adaptive parameters
        self._current_context_top_k = self.config.context_top_k
        self._current_enable_fslgs = self.config.enable_fslgs
        self._current_max_tokens = self.config.max_tokens
        
        # Memory for summarization
        self._memory: List[Dict] = []
    
    def _default_embedding(self, text: str) -> np.ndarray:
        """
        Default simple embedding function.

        Uses a simple hash-based embedding for demonstration.
        In production, use a proper embedding model.

        Args:
            text: Text to embed

        Returns:
            Embedding vector
        """
        # Simple deterministic embedding based on text hash
        np.random.seed(hash(text) % (2**32))
        embedding = np.random.randn(384)  # 384-dimensional embedding
        return embedding / np.linalg.norm(embedding)
    
    def _adapt_context_parameters(self, timing: Dict, cognitive_load: float) -> int:
        """
        Adapt context parameters based on timing and load.

        Args:
            timing: Timing information from recent calls
            cognitive_load: Current cognitive load (0-1)

        Returns:
            Adapted context_top_k value
        """
        avg_latency = np.mean(self._latency_history) if self._latency_history else 0
        
        # If we're running slow, reduce context
        if avg_latency > self.config.target_latency_ms:
            # Reduce context by 20%
            new_k = max(
                self.config.min_context_top_k,
                int(self._current_context_top_k * 0.8)
            )
            self._current_context_top_k = new_k
        
        # If we're running fast and load is high, increase context
        elif avg_latency < self.config.target_latency_ms * 0.7 and cognitive_load > 0.7:
            # Increase context by 20%
            new_k = min(
                self.config.max_context_top_k,
                int(self._current_context_top_k * 1.2)
            )
            self._current_context_top_k = new_k
        
        return self._current_context_top_k
    
    def _apply_qos_degradation(self) -> bool:
        """
        Apply QoS degradation based on priority tier and current load.

        Returns:
            True if degradation was applied
        """
        # Check if we need to degrade
        avg_latency = np.mean(self._latency_history) if self._latency_history else 0
        
        if avg_latency <= self.config.target_latency_ms:
            # No degradation needed
            return False
        
        # Apply tier-specific degradation
        if self.config.priority_tier == "low":
            # Aggressive degradation for low priority
            if self.config.degradation_policy.get('disable_fslgs', False):
                self._current_enable_fslgs = False
            
            if self.config.degradation_policy.get('limit_max_tokens', False):
                self._current_max_tokens = min(500, self.config.max_tokens)
            
            min_k = self.config.degradation_policy.get(
                'min_context_top_k_under_load',
                self.config.min_context_top_k
            )
            self._current_context_top_k = min_k
            
            return True
        
        elif self.config.priority_tier == "normal":
            # Moderate degradation
            self._current_context_top_k = max(
                self.config.min_context_top_k,
                int(self._current_context_top_k * 0.7)
            )
            return True
        
        else:  # high priority
            # Minimal degradation, just log
            return False
    
    def _summarize_old_memory(self):
        """
        Summarize old memory entries when token limit exceeded.

        This is a simple rule-based stub. In production, use LLM for summarization.
        """
        if not self._memory:
            return
        
        # Calculate current memory tokens
        total_tokens = sum(
            estimate_tokens(str(entry))
            for entry in self._memory
        )
        
        if total_tokens <= self.config.max_memory_tokens:
            return
        
        # Simple summarization: take first 25% of entries and summarize
        num_to_summarize = len(self._memory) // 4
        if num_to_summarize == 0:
            return
        
        old_entries = self._memory[:num_to_summarize]
        
        # Create a summary entry (simple concatenation for demo)
        summary = {
            'type': 'summary',
            'summarized_count': len(old_entries),
            'content': f"Summary of {len(old_entries)} entries"
        }
        
        # Replace old entries with summary
        self._memory = [summary] + self._memory[num_to_summarize:]
    
    def generate(
        self,
        prompt: str,
        moral_value: Optional[str] = None,
        user_intent: Optional[str] = None,
        context: Optional[List[Dict]] = None
    ) -> Dict:
        """
        Generate a response with cost tracking, caching, and QoS.

        Args:
            prompt: Input prompt
            moral_value: Optional moral value context
            user_intent: Optional user intent
            context: Optional context items

        Returns:
            Dict with:
                - response: Generated response text
                - cost: Cost tracking info
                - from_cache: Whether response came from cache
                - timing: Timing information
                - qos_degraded: Whether QoS degradation was applied
        """
        start_time = time.time()
        
        # Apply QoS degradation if needed
        qos_degraded = self._apply_qos_degradation()
        
        # Adapt context parameters
        self._current_context_top_k = self._adapt_context_parameters(
            {'total': np.mean(self._latency_history) if self._latency_history else 0},
            self._cognitive_load
        )
        
        # Try cache lookup if enabled
        from_cache = False
        response_text = None
        
        if self.cache is not None:
            query_embedding = self.embedding_fn(prompt)
            cached_response = self.cache.lookup(
                query_embedding,
                moral_value,
                user_intent
            )
            
            if cached_response is not None:
                response_text = cached_response
                from_cache = True
        
        # If not from cache, generate new response
        if response_text is None:
            if self.llm_backend is not None:
                # Call LLM backend
                response_text = self.llm_backend(
                    prompt,
                    max_tokens=self._current_max_tokens,
                    enable_fslgs=self._current_enable_fslgs
                )
            else:
                # Mock response for testing
                response_text = f"Mock response for: {prompt[:50]}..."
            
            # Store in cache
            if self.cache is not None:
                query_embedding = self.embedding_fn(prompt)
                self.cache.store(
                    query_embedding,
                    moral_value,
                    user_intent,
                    response_text
                )
        
        # Track cost
        cost_info = self.cost_tracker.update(
            prompt,
            response_text,
            self.config.pricing
        )
        
        # Record timing
        end_time = time.time()
        total_time_ms = (end_time - start_time) * 1000
        self._latency_history.append(total_time_ms)
        
        # Update memory
        self._memory.append({
            'prompt': prompt,
            'response': response_text,
            'moral_value': moral_value,
            'user_intent': user_intent
        })
        
        # Check if summarization needed
        self._summarize_old_memory()
        
        # Build result
        result = {
            'response': response_text,
            'cost': cost_info,
            'from_cache': from_cache,
            'timing': {
                'total': total_time_ms,
                'avg_latency': np.mean(self._latency_history)
            },
            'qos_degraded': qos_degraded,
            'context_top_k': self._current_context_top_k,
            'enable_fslgs': self._current_enable_fslgs
        }
        
        return result
    
    def get_stats(self) -> Dict:
        """
        Get engine statistics.

        Returns:
            Dict with cost, cache, and performance stats
        """
        stats = {
            'cost': self.cost_tracker.get_summary(),
            'performance': {
                'avg_latency_ms': np.mean(self._latency_history) if self._latency_history else 0,
                'current_context_top_k': self._current_context_top_k
            },
            'memory_size': len(self._memory)
        }
        
        if self.cache is not None:
            stats['cache'] = self.cache.get_stats()
        
        return stats

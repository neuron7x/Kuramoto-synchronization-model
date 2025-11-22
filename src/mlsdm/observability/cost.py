"""
Cost tracking and token estimation for MLSDM.

This module provides utilities to estimate token usage and track costs
associated with LLM API calls.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, Any


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a text string.

    Uses a simple heuristic: approximately 1.3 tokens per word.
    This is a stable approximation for English text.

    Args:
        text: Input text to estimate tokens for

    Returns:
        Estimated token count
    """
    if not text:
        return 0
    
    # Simple heuristic: split by whitespace and multiply by average token ratio
    word_count = len(text.split())
    # Average English word is ~1.3 tokens (accounts for punctuation, subwords)
    return int(word_count * 1.3)


@dataclass
class CostTracker:
    """
    Track token usage and costs for LLM API calls.

    Attributes:
        prompt_tokens: Number of tokens in prompts
        completion_tokens: Number of tokens in completions
        total_tokens: Total token count
        estimated_cost_usd: Estimated cost in USD
    """
    
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float = 0.0
    
    # Track per-call details
    call_history: list = field(default_factory=list)
    
    def update(
        self,
        prompt: str,
        completion: str,
        pricing: Optional[Dict[str, float]] = None
    ) -> Dict[str, Any]:
        """
        Update tracker with a new prompt-completion pair.

        Args:
            prompt: The input prompt text
            completion: The generated completion text
            pricing: Optional pricing dict with 'prompt_price_per_1k' and
                    'completion_price_per_1k' keys (in USD)

        Returns:
            Dict with token counts and cost for this call
        """
        prompt_tokens_count = estimate_tokens(prompt)
        completion_tokens_count = estimate_tokens(completion)
        total = prompt_tokens_count + completion_tokens_count
        
        # Update cumulative counts
        self.prompt_tokens += prompt_tokens_count
        self.completion_tokens += completion_tokens_count
        self.total_tokens += total
        
        # Calculate cost if pricing provided
        call_cost = 0.0
        if pricing:
            prompt_price_per_1k = pricing.get('prompt_price_per_1k', 0.0)
            completion_price_per_1k = pricing.get('completion_price_per_1k', 0.0)
            
            call_cost = (
                (prompt_tokens_count / 1000.0) * prompt_price_per_1k +
                (completion_tokens_count / 1000.0) * completion_price_per_1k
            )
            self.estimated_cost_usd += call_cost
        
        # Record call details
        call_info = {
            'prompt_tokens': prompt_tokens_count,
            'completion_tokens': completion_tokens_count,
            'total_tokens': total,
            'estimated_cost_usd': call_cost
        }
        self.call_history.append(call_info)
        
        return call_info
    
    def get_summary(self) -> Dict[str, Any]:
        """
        Get summary of all tracked costs.

        Returns:
            Dict with cumulative token counts and costs
        """
        return {
            'prompt_tokens': self.prompt_tokens,
            'completion_tokens': self.completion_tokens,
            'total_tokens': self.total_tokens,
            'estimated_cost_usd': self.estimated_cost_usd,
            'num_calls': len(self.call_history)
        }
    
    def reset(self):
        """Reset all tracking counters."""
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.estimated_cost_usd = 0.0
        self.call_history.clear()

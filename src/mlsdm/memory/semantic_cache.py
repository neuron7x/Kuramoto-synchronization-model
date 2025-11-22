"""
Semantic response cache for MLSDM.

This module provides semantic caching of LLM responses based on
query embeddings, moral values, and user intents.
"""

import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, List
from collections import deque


@dataclass
class CacheEntry:
    """
    Single cache entry.

    Attributes:
        query_embedding: Embedding vector of the query
        moral_value: Associated moral value
        user_intent: User intent string
        response: Cached response text
    """
    
    query_embedding: np.ndarray
    moral_value: Optional[str]
    user_intent: Optional[str]
    response: str


class SemanticResponseCache:
    """
    Semantic cache for LLM responses.

    Stores and retrieves responses based on semantic similarity of queries,
    considering moral values and user intents.
    """
    
    def __init__(
        self,
        max_entries: int = 1000,
        similarity_threshold: float = 0.85
    ):
        """
        Initialize semantic cache.

        Args:
            max_entries: Maximum number of cache entries
            similarity_threshold: Minimum cosine similarity for cache hit (0-1)
        """
        self.max_entries = max_entries
        self.similarity_threshold = similarity_threshold
        self._cache: deque = deque(maxlen=max_entries)
        self._hits = 0
        self._misses = 0
    
    def _compute_similarity(
        self,
        embedding1: np.ndarray,
        embedding2: np.ndarray
    ) -> float:
        """
        Compute cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        # Normalize embeddings
        norm1 = np.linalg.norm(embedding1)
        norm2 = np.linalg.norm(embedding2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        # Cosine similarity
        similarity = np.dot(embedding1, embedding2) / (norm1 * norm2)
        return float(similarity)
    
    def _matches_context(
        self,
        entry: CacheEntry,
        moral_value: Optional[str],
        user_intent: Optional[str]
    ) -> bool:
        """
        Check if cache entry matches the context criteria.

        Args:
            entry: Cache entry to check
            moral_value: Moral value to match
            user_intent: User intent to match

        Returns:
            True if context matches
        """
        # If both are None, they match
        if moral_value is None and entry.moral_value is None:
            moral_match = True
        else:
            moral_match = entry.moral_value == moral_value
        
        if user_intent is None and entry.user_intent is None:
            intent_match = True
        else:
            intent_match = entry.user_intent == user_intent
        
        return moral_match and intent_match
    
    def lookup(
        self,
        query_embedding: np.ndarray,
        moral_value: Optional[str] = None,
        user_intent: Optional[str] = None
    ) -> Optional[str]:
        """
        Look up a cached response.

        Args:
            query_embedding: Embedding of the query
            moral_value: Optional moral value context
            user_intent: Optional user intent context

        Returns:
            Cached response if found, None otherwise
        """
        best_similarity = 0.0
        best_response = None
        
        for entry in self._cache:
            # Check if context matches
            if not self._matches_context(entry, moral_value, user_intent):
                continue
            
            # Compute similarity
            similarity = self._compute_similarity(
                query_embedding,
                entry.query_embedding
            )
            
            # Check if this is the best match so far
            if similarity > best_similarity and similarity >= self.similarity_threshold:
                best_similarity = similarity
                best_response = entry.response
        
        # Update stats
        if best_response is not None:
            self._hits += 1
        else:
            self._misses += 1
        
        return best_response
    
    def store(
        self,
        query_embedding: np.ndarray,
        moral_value: Optional[str],
        user_intent: Optional[str],
        response: str
    ):
        """
        Store a response in the cache.

        Args:
            query_embedding: Embedding of the query
            moral_value: Optional moral value context
            user_intent: Optional user intent context
            response: Response text to cache
        """
        entry = CacheEntry(
            query_embedding=query_embedding,
            moral_value=moral_value,
            user_intent=user_intent,
            response=response
        )
        self._cache.append(entry)
    
    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache hits, misses, and hit rate
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': hit_rate,
            'size': len(self._cache),
            'max_entries': self.max_entries
        }
    
    def clear(self):
        """Clear the cache and reset statistics."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

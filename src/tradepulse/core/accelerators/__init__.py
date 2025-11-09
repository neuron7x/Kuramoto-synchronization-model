"""Acceleration utilities bridging Python and Rust implementations."""

from .numeric import convolve, quantiles, sliding_windows

__all__ = ["convolve", "quantiles", "sliding_windows"]

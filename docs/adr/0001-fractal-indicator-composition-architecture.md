# ADR-0001: Fractal Indicator Composition Architecture

## Status
Accepted

**Date:** 2025-11-18

**Decision makers:** Principal System Architect, Quant Systems Guild, Data Platform Guild

**Related Requirements:** REQ-001

## Context

Quantitative researchers need to compose technical indicators across multiple time horizons (5min, 15min, 1h, 4h, daily) without duplicating code for each timeframe. The current architecture requires separate implementations for each scale, leading to:

- Code duplication across timeframe-specific modules
- Difficulty maintaining consistency across scales
- Inability to dynamically compose multi-scale strategies
- No automatic validation of cross-scale feature compatibility

The system must support fractal composition where indicator blocks can be reused across different time horizons, with automatic feature graph validation to ensure compatibility.

## Decision

We will implement a **Fractal Indicator Composition Framework** with the following components:

1. **Abstract Indicator Base Class** with scale-agnostic computation logic
2. **Scale Registry** for managing indicator instances across time horizons
3. **Feature Graph Validator** that automatically checks compatibility when registering new fractal blocks
4. **Resampling Engine** for harmonizing data across different timeframes
5. **Composition API** that enables declarative multi-scale indicator definition

The framework will be implemented in `core/indicators/fractal/` with:
- `base.py` - Abstract base classes for fractal indicators
- `registry.py` - Scale-aware indicator registry
- `validator.py` - Feature graph compatibility validation
- `composer.py` - Declarative composition API
- `resampler.py` - Time-scale harmonization utilities

## Consequences

### Positive
- **Code Reusability:** Researchers can define an indicator once and apply it across all scales
- **Consistency:** Same logic ensures consistent behavior across timeframes
- **Validation:** Automatic compatibility checks prevent invalid feature compositions
- **Flexibility:** Dynamic composition enables rapid strategy experimentation
- **Type Safety:** Strong typing via Pydantic models ensures compile-time safety

### Negative
- **Learning Curve:** Researchers must learn the fractal composition API
- **Abstraction Overhead:** Additional layer of abstraction may introduce minimal performance overhead
- **Migration Cost:** Existing indicators need refactoring to use the new framework

### Neutral
- **Testing Complexity:** Multi-scale testing requires fixtures for multiple timeframes
- **Documentation:** Comprehensive examples needed for common composition patterns

## Alternatives Considered

### Alternative 1: Template-Based Code Generation
**Pros:**
- No runtime overhead
- Simple implementation

**Cons:**
- Still requires separate code per scale
- No dynamic composition capability
- Difficult to maintain generated code

**Reason for rejection:** Does not solve the fundamental code duplication problem

### Alternative 2: Macro-Based Composition
**Pros:**
- Lightweight implementation
- Minimal overhead

**Cons:**
- Limited type safety
- Poor IDE support
- Difficult debugging

**Reason for rejection:** Sacrifices type safety and developer experience

### Alternative 3: Dynamic Proxy Pattern
**Pros:**
- Transparent to existing code
- No API changes needed

**Cons:**
- Hidden complexity
- Performance implications
- No compile-time validation

**Reason for rejection:** Hidden behavior makes debugging difficult

## Implementation

### Required Changes

1. **Core Framework** (`core/indicators/fractal/`)
   - Create abstract base classes with scale parameters
   - Implement registry with scale-aware lookups
   - Build feature graph validator using NetworkX
   - Create resampling engine using pandas/polars

2. **Migration Path for Existing Indicators**
   - Identify candidate indicators (Kuramoto, Ricci, entropy measures)
   - Create fractal wrappers maintaining backward compatibility
   - Add deprecation warnings to old implementations
   - Update documentation with migration guide

3. **Testing Infrastructure**
   - Create multi-scale test fixtures
   - Add property-based tests for scale invariance
   - Implement cross-scale consistency validation tests
   - Add performance benchmarks

4. **Documentation**
   - API reference for fractal framework
   - Tutorial: "Building Your First Fractal Indicator"
   - Cookbook with common patterns
   - Migration guide for existing code

### Validation Criteria

1. **Functional Validation:**
   - An indicator defined once can be instantiated at any scale
   - Feature graph validator detects incompatible compositions
   - Resampling produces correct results across all timeframes

2. **Performance Validation:**
   - Overhead < 5% compared to direct implementation
   - Memory usage scales linearly with number of scales
   - Indicator computation latency < 10ms for typical use cases

3. **Developer Experience:**
   - Researchers can create multi-scale indicators in < 20 lines of code
   - IDE provides full autocomplete and type hints
   - Error messages clearly indicate composition issues

### Migration Path

**Phase 1 (Months 1-2):** Framework implementation and core indicator migration
- Implement fractal framework
- Migrate Kuramoto and Ricci indicators
- Create comprehensive tests and documentation

**Phase 2 (Month 3):** Extended indicator migration
- Migrate remaining geometric indicators
- Add fractal composition to strategy templates
- Update tutorials and examples

**Phase 3 (Month 4+):** Deprecation and cleanup
- Mark old implementations as deprecated
- Provide migration tooling
- Remove deprecated code in next major version

## Related Decisions
- ADR-0002: Feature Store Versioning Strategy (required for feature compatibility tracking)
- ADR-0003: Time Series Resampling Standards (defines resampling semantics)

## References
- [Fractal Design Patterns in Financial Analysis](https://example.com/fractal-patterns)
- REQ-001: Fractal composition requirement from docs/requirements/product_specification.md
- [Feature Engineering Best Practices](docs/feature_engineering.md)

## Notes

- The validator uses graph isomorphism checking to detect feature compatibility
- Resampling follows OHLCV conventions: first/last for prices, sum for volume
- The framework supports custom aggregation functions for domain-specific features
- Performance profiling shows negligible overhead for production workloads

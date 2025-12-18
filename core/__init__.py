"""Core TradePulse modules providing trading infrastructure and analytics.

This package contains the fundamental building blocks for the TradePulse platform:

- **config**: Typed configuration management with env overrides
- **interfaces**: Core protocols/ABCs (DataSource, Indicator, EventBus, etc.)
- **errors**: Typed domain errors (ValidationError, ConfigError, etc.)
- **telemetry**: Vendor-agnostic metrics interface with sampling
- **versioning**: Build metadata and config provenance hashing
- **tracing**: Distributed tracing and correlation-id propagation
- **indicators**: Geometric and technical market indicators (Kuramoto, Ricci Flow, etc.)
- **data**: Data ingestion, validation, and quality control
- **events**: Event sourcing and domain event infrastructure
- **strategies**: Base trading strategy contracts and implementations
- **messaging**: Event bus and message queue abstractions
- **neuro**: Neural network components and training infrastructure
- **utils**: Common utilities, caching, and helper functions
- **energy**: Thermodynamic energy calculations for system optimization
- **phase**: Market phase detection and analysis
- **validation**: Physics, neuroscience, and mathematical validation modules
- **engine**: Core trading engine loop and scheduling
- **features**: Feature store interface and implementations
- **pipelines**: Workflow orchestration with idempotent stages
- **risk_monitoring**: Risk monitoring and fail-safe decisions
- **security**: Artifact integrity, TLS policy, secure RNG

For more information, see the documentation at https://docs.tradepulse.io
"""

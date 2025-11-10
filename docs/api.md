# TradePulse API Documentation

Welcome to the TradePulse API documentation. This guide covers both the REST API for online inference and the internal Python API for algorithmic trading.

## REST API Documentation

### Getting Started
- 🚀 [Quick Start Guide](api/quick_start.md) - Get up and running in 5 minutes
- 📖 [Comprehensive API Guide](api/comprehensive_guide.md) - Complete reference with examples
- 🔐 [Authentication Guide](api/comprehensive_guide.md#authentication)
- ⚡ [Performance & Caching](api/comprehensive_guide.md#caching-and-performance)

### API Endpoints
- **Features API** - Compute technical indicators from market data
- **Predictions API** - Generate AI-powered trading signals
- **Admin API** - Risk management and kill-switch controls
- **Health API** - System health and monitoring
- **Metrics API** - Prometheus-compatible metrics export
- **WebSocket API** - Real-time streaming analytics
- **GraphQL API** - Flexible query interface

### Key Features
- ✅ OAuth 2.0 authentication with mTLS for admin endpoints
- ✅ Rate limiting (100 req/min public, 30 req/min admin)
- ✅ Response caching with ETag support
- ✅ Idempotency keys for safe retries
- ✅ Pagination for large result sets
- ✅ Comprehensive error handling
- ✅ OpenAPI 3.1 specification

### Base URLs
- **Production**: `https://api.tradepulse.example.com`
- **Staging**: `https://staging-api.tradepulse.example.com`

### Quick Example

```bash
curl -X POST https://api.tradepulse.example.com/api/v1/predictions \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC-USD",
    "bars": [{
      "timestamp": "2025-01-01T00:00:00Z",
      "high": 42100.0,
      "low": 41900.0,
      "close": 42050.0,
      "volume": 18.5
    }]
  }'
```

## Python API Reference

### Core Trading Components

## FHMC (Free Energy Homeostatic Model Controller)

- `FHMC.from_yaml(path)` - Load configuration from YAML
- `FHMC.update_biomarkers(action_scalar_series, internal_latents, fs_latents)` - Update biomarker state
- `FHMC.compute_orexin(exp_return, novelty, load)` - Compute orexin (reward seeking)
- `FHMC.compute_threat(maxdd, volshock, cp_score)` - Compute threat level
- `FHMC.flipflop_step()` - Execute state transition
- `FHMC.next_window_seconds()` - Get next evaluation window

## ActorCriticFHMC (Reinforcement Learning Controller)

- `ActorCriticFHMC.act(state_np)` - Select action from state
- `ActorCriticFHMC.learn(s, a, r, s_next, done)` - Update policy from experience

## SleepReplayEngine (Experience Replay)

- `SleepReplayEngine.observe_transition(...)` - Store experience tuple
- `SleepReplayEngine.sample(batch_size)` - Sample batch for training
- `SleepReplayEngine.dgr_batch(generator, m)` - Dynamic goal relabeling

## CFGWO (Chaos-Free Grey Wolf Optimizer)

- `CFGWO.optimize()` - Run optimization algorithm

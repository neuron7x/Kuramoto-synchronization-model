# Frequently Asked Questions (FAQ)

Common questions and answers about TradePulse.

---

## General Questions

### What is TradePulse?

TradePulse is an advanced algorithmic trading framework that combines geometric and topological market analysis (Kuramoto synchronization, Ricci curvature, entropy metrics) with modern backtesting and execution capabilities.

### Is TradePulse free and open source?

TradePulse is distributed under the TradePulse Proprietary License Agreement (TPLA).
You may evaluate and develop internally with the platform, but any commercial
use requires a separate written agreement with TradePulse Technologies.

### What markets does TradePulse support?

TradePulse is market-agnostic and can be used for:
- Cryptocurrencies
- Stocks
- Forex
- Futures
- Options

The framework provides interfaces for connecting to any market data provider and exchange.

### Is TradePulse suitable for beginners?

TradePulse is designed for developers and traders with programming experience (Python). While the framework provides comprehensive documentation, some understanding of:
- Python programming
- Trading concepts
- Technical analysis
- Software development

is recommended.

---

## Installation & Setup

### What are the system requirements?

**Minimum:**
- Python 3.11+
- 4 GB RAM
- 10 GB disk space

**Recommended:**
- Python 3.12+
- 16 GB RAM
- SSD storage
- Multi-core CPU

### Can I run TradePulse on Windows?

Yes, TradePulse runs on:
- Linux (recommended)
- macOS
- Windows (with WSL2 recommended)

### Do I need Docker?

No, Docker is optional. You can run TradePulse with just Python. Docker is recommended for:
- Running the full stack (web dashboard, databases, monitoring)
- Easy deployment
- Consistent environments

### Installation fails with dependency errors

Try:
```bash
# Update pip
pip install --upgrade pip

# Install with verbose output
pip install -v -r requirements.lock

# Or use conda
conda install --file requirements.lock
```

See [Troubleshooting](troubleshooting.md) for more solutions.

---

## Indicators & Features

### What indicators does TradePulse provide?

**Built-in indicators:**
- Kuramoto synchronization (phase coherence)
- Ricci curvature (geometric market analysis)
- Shannon entropy and delta entropy
- Hurst exponent (long memory)
- VPIN (order flow toxicity)

**Easy to add:**
- RSI, MACD, Bollinger Bands
- Custom technical indicators
- Machine learning features

See [Indicators Documentation](indicators.md) for details.

### How do Kuramoto and Ricci indicators work?

- **Kuramoto Order Parameter (R)**: Measures synchronization between price oscillators. High R (close to 1) indicates strong coordination, low R indicates chaos.

- **Ricci Curvature**: Measures geometric properties of price graphs. Positive curvature suggests stability, negative curvature suggests volatility or regime transition.

See the papers referenced in [docs/indicators.md](indicators.md) for mathematical details.

### Can I use traditional indicators like RSI and MACD?

Yes! While TradePulse focuses on geometric indicators, you can easily add traditional indicators. See [Extending TradePulse](extending.md) for examples.

### How do I create custom indicators?

See [Extending TradePulse - Custom Indicators](extending.md#adding-custom-indicators) for a step-by-step guide.

---

## Backtesting

### How accurate is the backtesting?

TradePulse uses walk-forward backtesting with:
- Realistic slippage modeling
- Commission costs
- Position sizing
- Risk management

However, backtesting is always an approximation. Real trading will differ due to:
- Market impact
- Latency
- Liquidity
- Order fills

### Can I use my own data for backtesting?

Yes! TradePulse supports:
- CSV files
- Custom data sources
- Database connections
- Real-time feeds

See [Data Ingestion](integration-api.md#data-ingestion-api) for details.

### How long does backtesting take?

Performance depends on:
- Dataset size
- Indicator complexity
- Walk-forward window size
- Hardware

Typical performance:
- 10,000 bars: ~5-30 seconds
- 100,000 bars: ~1-5 minutes
- 1,000,000 bars: ~10-30 minutes

Use the `--fast` flag or reduce window sizes for faster iteration during development.

### What is walk-forward backtesting?

Walk-forward backtesting:
1. Train on period N
2. Test on period N+1
3. Move window forward
4. Repeat

This prevents look-ahead bias and provides more realistic results than training on the entire dataset.

---

## Trading & Execution

### Can I use TradePulse for live trading?

Yes, but:
1. Test thoroughly with paper trading first
2. Start with small position sizes
3. Monitor closely
4. Understand the risks

**Trading involves financial risk. Use at your own risk.**

### What exchanges are supported?

TradePulse provides adapters for:
- Binance (spot and futures)
- More coming soon

You can implement custom adapters for any exchange. See [Integration API](integration-api.md#execution-api).

### How do I implement paper trading?

Use the `SimulatedExecutionAdapter`:

```python
from execution.simulator import SimulatedExecutionAdapter

adapter = SimulatedExecutionAdapter(
    initial_balance=10000,
    commission=0.001
)
```

### What about risk management?

TradePulse includes:
- Position sizing
- Stop-loss orders
- Take-profit orders
- Maximum drawdown limits
- Portfolio exposure limits

Configure in your strategy or execution settings.

### How fast is order execution?

Execution speed depends on:
- Exchange API latency
- Network connection
- Order complexity

Typical latencies:
- Indicator calculation: <100ms
- Signal generation: <50ms
- Order placement: 50-500ms (network dependent)

---

## Performance & Optimization

### Is TradePulse fast enough for high-frequency trading?

TradePulse is optimized for low to medium frequency trading (seconds to minutes). For sub-second HFT:
- Use the Go microservices for critical paths
- Optimize indicator calculations
- Consider compiled languages (Cython, Rust)

### How can I speed up backtesting?

1. Reduce data size
2. Use simpler indicators
3. Increase walk-forward window
4. Use multiprocessing
5. Profile and optimize bottlenecks

```bash
# Profile code
python -m cProfile -o profile.stats backtest.py
python -m pstats profile.stats
```

### Can I use GPU acceleration?

Some indicators support GPU acceleration:

```python
from core.indicators.kuramoto import compute_phase_gpu

# Requires CuPy
phases = compute_phase_gpu(prices)
```

### How much memory does TradePulse use?

Memory usage depends on:
- Dataset size
- Number of indicators
- Window sizes

Typical usage:
- Small backtests: 100-500 MB
- Large backtests: 1-4 GB
- Live trading: 50-200 MB

---

## Development & Contribution

### How can I contribute?

See [CONTRIBUTING.md](../CONTRIBUTING.md) for:
- Code contribution guidelines
- PR process
- Coding standards
- Testing requirements

### Where should I report bugs?

Report bugs on [GitHub Issues](https://github.com/neuron7x/TradePulse/issues) with:
- Clear description
- Steps to reproduce
- Expected vs actual behavior
- Environment details

### Can I request features?

Yes! Open a [feature request](https://github.com/neuron7x/TradePulse/issues/new) with:
- Use case description
- Proposed solution
- Alternative approaches

### How can I get help?

1. Check this FAQ
2. Read the documentation
3. Search [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
4. Open a new issue
5. Join discussions

---

## Testing

### How do I run the tests?

```bash
# All tests
pytest tests/

# With coverage
pytest tests/ \
  --cov=core --cov=backtest --cov=execution \
  --cov-config=configs/quality/critical_surface.coveragerc \
  --cov-report=term-missing --cov-report=xml

python -m tools.coverage.guardrail \
  --config configs/quality/critical_surface.toml \
  --coverage coverage.xml

# Specific test category
pytest tests/unit/
pytest tests/integration/
pytest tests/property/
```

See [TESTING.md](../TESTING.md) for comprehensive testing documentation.

### What is property-based testing?

Property-based testing uses [Hypothesis](https://hypothesis.readthedocs.io/) to:
- Generate diverse test cases automatically
- Find edge cases
- Verify invariants

Example:
```python
from hypothesis import given, strategies as st

@given(prices=st.lists(st.floats(min_value=1.0), min_size=20))
def test_indicator_never_negative(prices):
    result = indicator.transform(np.array(prices))
    assert result.value >= 0
```

### Why are some tests slow?

Some tests are marked as "slow" because they:
- Use large datasets
- Run multiple iterations
- Test performance

Skip slow tests during development:
```bash
pytest tests/ -m "not slow"
```

### What is the coverage goal?

Target: **98% code coverage**

Current coverage is visible in CI and can be generated locally:
```bash
pytest tests/ \
  --cov=core --cov=backtest --cov=execution \
  --cov-config=configs/quality/critical_surface.coveragerc \
  --cov-report=html
open htmlcov/index.html
```

---

## Monitoring & Production

### How do I monitor TradePulse in production?

TradePulse provides:
- Prometheus metrics
- Structured logging
- Health checks
- Alerts

See [Monitoring Guide](monitoring.md) for setup.

### What metrics are available?

Key metrics:
- Trades executed
- Order latency
- Position values
- P&L
- Error rates
- System health

### How do I set up alerts?

Configure Prometheus AlertManager with rules for:
- High error rates
- Large drawdowns
- Service failures
- Stale data

See [Monitoring - Alerting](monitoring.md#alerting).

### Can I integrate with Grafana?

Yes! TradePulse exports Prometheus metrics that Grafana can visualize. See [Monitoring - Grafana](monitoring.md#grafana-dashboards) for dashboard templates.

---

## Security

### How do I secure API keys?

Never commit API keys to git. Use:
- Environment variables
- `.env` files (gitignored)
- Secrets managers (AWS Secrets Manager, HashiCorp Vault)

See [SECURITY.md](../SECURITY.md) for best practices.

### Is TradePulse secure for production?

TradePulse follows security best practices, but you must:
- Secure your API keys
- Use HTTPS/TLS
- Implement authentication
- Keep dependencies updated
- Follow [SECURITY.md](../SECURITY.md)

### How do I report security vulnerabilities?

Email: security@tradepulse.local

Do not report security issues publicly. See [SECURITY.md](../SECURITY.md) for disclosure process.

---

## Troubleshooting

### My strategy isn't profitable in backtesting

Common issues:
- Overfitting to training data
- Look-ahead bias
- Unrealistic assumptions (no slippage, instant fills)
- Insufficient testing period
- Survivorship bias in data

### Indicators return NaN or inf

Check:
- Sufficient data points
- No division by zero
- Valid input ranges
- Data quality

### Orders aren't executing

Verify:
- Exchange connection
- API credentials
- Sufficient balance
- Order parameters
- Exchange status

See [Troubleshooting Guide](troubleshooting.md) for more solutions.

---

## Architecture

### What is FPM-A?

Fractal Modular Architecture (FPM-A) is TradePulse's architectural pattern:
- **Fractal**: Self-similar structure at different scales
- **Modular**: Clean separation of concerns
- **Ports & Adapters**: Interface-based design

See [ARCHITECTURE.md](ARCHITECTURE.md) for details.

### Why use Protocol Buffers?

Protocol Buffers (protobuf) provide:
- Type safety
- Version compatibility
- Language interoperability
- Efficient serialization

This enables TradePulse's polyglot architecture (Python + Go + TypeScript).

### Can I use TradePulse without Go services?

Yes! The Go services (VPIN, orderbook analysis) are optional. The core Python framework is fully functional standalone.

---

## Data & Formats

### What data format does TradePulse use?

For CSV data:
- Timestamp column (ISO 8601 or Unix timestamp)
- OHLCV columns (open, high, low, close, volume)
- Additional columns optional

Example:
```csv
timestamp,open,high,low,close,volume
2024-01-01 00:00:00,50000,50100,49900,50050,100.5
2024-01-01 00:01:00,50050,50200,50000,50150,150.2
```

### How does the feature pipeline handle constant volume windows?

`SignalFeaturePipeline` masks zero rolling variance in the `volume_z` normaliser and
returns a z-score of `0.0` for constant-volume windows once the warmup period
finishes. This keeps the feature finite so downstream models can continue to use
the observations without additional guards.

### Can I use 1-minute, hourly, or daily data?

Yes! TradePulse is timeframe-agnostic. Specify your timeframe in analysis:

```python
# 1-minute bars
analyzer = MarketAnalyzer(timeframe="1m")

# Hourly bars
analyzer = MarketAnalyzer(timeframe="1h")

# Daily bars
analyzer = MarketAnalyzer(timeframe="1d")
```

### Where can I get market data?

Free sources:
- Binance API
- Coinbase Pro API
- Yahoo Finance
- Alpha Vantage

Paid sources:
- IEX Cloud
- Polygon.io
- Quandl

---

## Performance Metrics

### What metrics does TradePulse calculate?

- **Return metrics**: Total return, annualized return
- **Risk metrics**: Sharpe ratio, Sortino ratio, max drawdown
- **Trade metrics**: Win rate, profit factor, average win/loss
- **Statistical**: Skewness, kurtosis, VaR, CVaR

### How is Sharpe ratio calculated?

```python
sharpe = (mean_return - risk_free_rate) / std_return * sqrt(periods_per_year)
```

Where:
- `mean_return`: Average period return
- `risk_free_rate`: Risk-free rate (annualized)
- `std_return`: Standard deviation of returns
- `periods_per_year`: Trading periods (252 for daily, 252*6.5 for hourly, etc.)

---

## Bilingual Support / Підтримка двох мов

### Does TradePulse support Ukrainian?

TradePulse documentation is primarily in English, with Ukrainian translations in key areas:
- Main README (bilingual)
- Contributing guidelines (bilingual)
- Code comments (English)

### Чи можу я використовувати TradePulse українською?

Так! Основна документація англійською, але ключові документи мають переклад:
- README.md
- CONTRIBUTING.md

Ви можете писати Issues та Discussions українською мовою.

---

## Still have questions?

- Check [Documentation](index.md)
- Search [GitHub Issues](https://github.com/neuron7x/TradePulse/issues)
- Read [Troubleshooting](troubleshooting.md)
- Open a new issue

---

**Last Updated**: 2025-01-01

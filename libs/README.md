# Libs Module

## Overview

The `libs` module contains shared libraries, utilities, and helper functions used across TradePulse modules.

## Purpose

- **Shared Utilities**: Common utility functions
- **Helper Libraries**: Reusable components
- **Type Definitions**: Shared type definitions
- **Constants**: Platform-wide constants

## Key Features

- 🔧 **Utilities**: Math, string, date/time utilities
- 📐 **Mathematical Functions**: Financial calculations
- 🔄 **Converters**: Data format conversions
- 📊 **Validators**: Input validation functions

## Usage Examples

```python
from libs.math import calculate_sharpe_ratio, calculate_volatility
from libs.time import to_utc, parse_datetime
from libs.validation import validate_symbol, validate_quantity

# Calculate metrics
sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.02)
vol = calculate_volatility(returns, annualization_factor=252)

# Time utilities
utc_time = to_utc(local_time, timezone="US/Eastern")
dt = parse_datetime("2023-01-15T10:30:00Z")

# Validation
if validate_symbol("BTC/USDT"):
    print("Valid symbol")
```

## Related Modules

All modules depend on `libs` for shared functionality.

## License

See [LICENSE](../LICENSE) for licensing information.

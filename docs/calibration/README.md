# TradePulse Calibration System

## Overview

The TradePulse Calibration System provides tools and workflows for configuring accuracy, thresholds, and sensitivity parameters across all controllers and modules.

## Quick Start

```bash
make calibrate-list      # List profiles
make calibrate-validate  # Validate configs
make calibrate-balanced  # Apply balanced profile
```

## Documentation

- [Calibration Quick Start](../CALIBRATION_QUICK_START.md)
- [Complete Calibration Guide](../CALIBRATION_GUIDE.md)
- [Calibration Script](../../scripts/calibrate_controllers.py)

## Profiles

- **Conservative**: Low risk, tight thresholds
- **Balanced**: Moderate risk, standard thresholds
- **Aggressive**: High risk, loose thresholds

---

See [Complete Calibration Guide](../CALIBRATION_GUIDE.md) for full documentation.

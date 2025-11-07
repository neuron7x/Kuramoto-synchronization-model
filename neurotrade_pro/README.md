# NeuroTrade Pro — EMH-Inspired Neuroeconomic Controller (Production-Ready)

This package provides a fully formalized, validated, and runnable implementation of an extramedullary-hematopoiesis-inspired controller for trading systems:
- State-space model (SSM) with bounded states
- EKF estimation
- Basal-ganglia-like softmax action selection with Go/No-Go
- CVaR/Expected Shortfall risk gate
- Validation pipeline, CLI, and tests

## Quickstart (examples)
python -m neurotrade_pro.cli.run_validate --steps 500
python -m neurotrade_pro.cli.run_backtest --steps 500
python -m neurotrade_pro.cli.run_calibrate --data your_data.csv

## Files
- models/emh.py — SSM & trigger
- estimation/ekf.py — 3×4 EKF
- estimation/belief.py — volatility-belief filter
- policy/mpc.py — controller + allocations
- risk/cvar.py — CVaR gate
- validate/validate.py — end-to-end validation
- conf/config.yml — parameters
- cli/*.py — runners
- tests/test_all.py — invariants

All states are clamped to [0,1]. RED mode forbids increase_risk.

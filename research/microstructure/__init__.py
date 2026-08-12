"""L2/L3 microstructure validation kernels.

Substrate: real order-book depth from Binance public WebSocket depth@100ms.
Purpose: validate Forman-Ricci cross-sectional edge on genuine precursor
substrate — NOT on OHLC/hourly surrogates.

Gate: IC >= 0.08 (Spearman, 1-5min forward returns),
permutation p < 0.01, positive lead capture, orthogonality to
vol/momentum/baseline factors. Binary PASS / FAIL.
"""

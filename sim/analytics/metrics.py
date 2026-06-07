"""Pure post-run analytics on the fill tape.

All functions are NumPy-only; no matplotlib, no file I/O. The
`run_sim.py` runner wraps these to produce the Phase 2 summary
plot. Phase 6 will extend this module with effective spread,
realised volatility, and other market-microstructure metrics.
"""

from __future__ import annotations

import numpy as np

from sim.core.events import Fill


def fill_prices(fills: list[Fill]) -> np.ndarray:
    """Array of fill prices (in ticks), in chronological order."""
    if not fills:
        return np.empty(0, dtype=np.int64)
    return np.fromiter((f.price for f in fills), dtype=np.int64, count=len(fills))


def fill_quantities(fills: list[Fill]) -> np.ndarray:
    """Array of fill quantities (in lots), in chronological order."""
    if not fills:
        return np.empty(0, dtype=np.int64)
    return np.fromiter((f.qty for f in fills), dtype=np.int64, count=len(fills))


def trade_sizes(fills: list[Fill]) -> np.ndarray:
    """Alias for `fill_quantities`. Used by Phase 2 reporting."""
    return fill_quantities(fills)


def simple_returns(prices: np.ndarray) -> np.ndarray:
    """Simple returns `r[t] = (p[t] - p[t-1]) / p[t-1]`.

    Args:
        prices: Array of prices in chronological order.

    Returns:
        Float array of length `len(prices) - 1`. Returns NaN-safe
        behaviour: a single price (or empty input) returns an empty
        array.
    """
    if len(prices) < 2:
        return np.empty(0, dtype=np.float64)
    p = prices.astype(np.float64)
    return np.diff(p) / p[:-1]


def log_returns(prices: np.ndarray) -> np.ndarray:
    """Log returns `r[t] = log(p[t] / p[t-1])`. Same edge-case rules
    as `simple_returns`."""
    if len(prices) < 2:
        return np.empty(0, dtype=np.float64)
    p = prices.astype(np.float64)
    return np.log(p[1:] / p[:-1])


def autocorrelation(returns: np.ndarray, max_lag: int) -> np.ndarray:
    """Sample autocorrelation at lags 1..max_lag.

    Args:
        returns: Float array of returns (any centred series is fine).
        max_lag: Maximum lag to compute; must be >= 1.

    Returns:
        Float array of length `max_lag`. Degenerate inputs (constant
        series) return zeros.
    """
    if max_lag < 1:
        raise ValueError(f"max_lag must be >= 1, got {max_lag}")
    if len(returns) < 2:
        return np.zeros(max_lag, dtype=np.float64)
    r = returns - returns.mean()
    var = float(np.sum(r * r))
    if var == 0.0:
        return np.zeros(max_lag, dtype=np.float64)
    out = np.empty(max_lag, dtype=np.float64)
    for lag in range(1, max_lag + 1):
        out[lag - 1] = float(np.sum(r[:-lag] * r[lag:]) / var)
    return out

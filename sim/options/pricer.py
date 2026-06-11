"""Black-Scholes European option pricing and Greeks (Phase 4).

Pure functions; no state. The standard normal CDF `N(x)` comes from
`scipy.special.ndtr` and the PDF `N'(x)` from `scipy.stats.norm.pdf`
(the SciPy norm-CDF decision recorded in CLAUDE.md).

Units (CLAUDE.md Phase 4 Implementation Contracts):
- `S`, `K` are in the same unit (price ticks, D2). BS is scale-free in
  `S/K`, so the absolute unit is irrelevant as long as both share it.
- `T` is in **years** (D1 conversion happens in `chain`, not here).
- `r` is the continuously-compounded annual risk-free rate.
- `sigma` is the annualised volatility (a plain fraction, e.g. 0.20).
- Returned prices/Greeks are **floats** in `S` units (D4 — no rounding).

Greeks shipped (D5): delta, gamma, vega. Theta/rho are intentionally
omitted in Phase 4.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.special import ndtr
from scipy.stats import norm


@dataclass(frozen=True)
class Greeks:
    """First/second-order BS sensitivities of one option (D5 set).

    Args:
        delta: ∂price/∂S. Call ∈ [0, 1]; put ∈ [-1, 0]. Per one unit of
            the underlying (one "share"), not per lot — lot scaling is a
            Phase 5 hedging concern.
        gamma: ∂delta/∂S = ∂²price/∂S². Always ≥ 0; identical for a call
            and put at the same strike/expiry/vol. Peaks at-the-money.
        vega: ∂price/∂sigma, per **1.0** change in sigma (i.e. per 100
            vol points, not per 1 vol point). Always ≥ 0; identical for a
            call and put at the same strike. → 0 as T → 0.
    """

    delta: float
    gamma: float
    vega: float


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    """Black-Scholes `d1`, `d2`. Caller guarantees S>0, K>0, T>0, sigma>0."""
    vol_sqrt_t = sigma * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * sigma * sigma) * T) / vol_sqrt_t
    d2 = d1 - vol_sqrt_t
    return d1, d2


def _intrinsic(S: float, K: float, *, is_call: bool) -> float:
    """Undiscounted intrinsic value max(S-K, 0) / max(K-S, 0)."""
    return max(S - K, 0.0) if is_call else max(K - S, 0.0)


def bs_price(
    S: float, K: float, T: float, r: float, sigma: float, *, is_call: bool
) -> float:
    """Black-Scholes price of a European call or put.

    Args:
        S: Underlying spot (price units; must be > 0).
        K: Strike (same units as S; must be > 0).
        T: Time to expiry in years (≤ 0 means at/after expiry).
        r: Continuously-compounded annual risk-free rate.
        sigma: Annualised volatility (fraction). ≤ 0 means deterministic.
        is_call: True for a call, False for a put.

    Returns:
        The option value as a float in S units.

    Edge cases:
        - `T <= 0`: returns intrinsic `max(S-K,0)` / `max(K-S,0)` (no
          discounting — the payoff is realised now).
        - `sigma <= 0`: deterministic underlying; returns the discounted
          intrinsic `max(S - K e^{-rT}, 0)` / `max(K e^{-rT} - S, 0)`.

    Raises:
        ValueError: If `S <= 0` or `K <= 0`.
    """
    if S <= 0:
        raise ValueError(f"S must be positive, got {S}")
    if K <= 0:
        raise ValueError(f"K must be positive, got {K}")

    if T <= 0:
        return _intrinsic(S, K, is_call=is_call)
    if sigma <= 0:
        disc_k = K * math.exp(-r * T)
        return max(S - disc_k, 0.0) if is_call else max(disc_k - S, 0.0)

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    disc_k = K * math.exp(-r * T)
    if is_call:
        return S * ndtr(d1) - disc_k * ndtr(d2)
    return disc_k * ndtr(-d2) - S * ndtr(-d1)


def bs_greeks(
    S: float, K: float, T: float, r: float, sigma: float, *, is_call: bool
) -> Greeks:
    """Delta, gamma, vega of a European call or put (D5 set).

    Args:
        S, K, T, r, sigma, is_call: As `bs_price`.

    Returns:
        A frozen `Greeks(delta, gamma, vega)`. See `Greeks` for units
        (vega is per 1.0 change in sigma).

    Edge cases:
        - `T <= 0` (at/after expiry): gamma = vega = 0. Delta is the step
          payoff slope — 1.0 (call) / -1.0 (put) when in-the-money, 0.0
          otherwise. Exactly at-the-money (S == K) delta is 0.0.
        - `sigma <= 0`: degenerate (no diffusion); gamma = vega = 0 and
          delta is the discounted-forward step (1/-1 ITM vs the forward,
          else 0).

    Raises:
        ValueError: If `S <= 0` or `K <= 0`.
    """
    if S <= 0:
        raise ValueError(f"S must be positive, got {S}")
    if K <= 0:
        raise ValueError(f"K must be positive, got {K}")

    if T <= 0 or sigma <= 0:
        # Threshold the spot against the relevant boundary: the raw strike
        # at expiry, or the discounted strike for the deterministic case.
        boundary = K if T <= 0 else K * math.exp(-r * T)
        if is_call:
            delta = 1.0 if S > boundary else 0.0
        else:
            delta = -1.0 if S < boundary else 0.0
        return Greeks(delta=delta, gamma=0.0, vega=0.0)

    d1, d2 = _d1_d2(S, K, T, r, sigma)
    sqrt_t = math.sqrt(T)
    pdf_d1 = float(norm.pdf(d1))

    delta = float(ndtr(d1)) if is_call else float(ndtr(d1)) - 1.0
    gamma = pdf_d1 / (S * sigma * sqrt_t)
    vega = S * pdf_d1 * sqrt_t
    return Greeks(delta=delta, gamma=gamma, vega=vega)

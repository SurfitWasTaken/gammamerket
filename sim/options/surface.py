"""Implied-volatility surface (Phase 4).

A volatility surface maps `(strike, expiry)` to an annualised σ. Phase 4
ships only the **flat** surface (constant σ for every point), but it lives
behind a tiny `VolSurface` protocol so a dynamic surface (smile/skew/term
structure) can drop in later without touching callers — the Phase 5 dealer
and the chain only ever call `vol(strike, expiry)`.

σ here is a plain annualised fraction (e.g. 0.20), feeding `pricer.bs_price`
directly. Strikes are in price units (ticks, D2); expiry is whatever key a
caller indexes by — the flat surface ignores both arguments.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class VolSurface(Protocol):
    """The stable interface every surface implements.

    A single method so callers (chain, Phase 5 dealer) never branch on the
    surface kind. `strike` is in price units; `expiry` may be expiry-minutes,
    a series, or years — the contract only fixes that some (strike, expiry)
    pair goes in and an annualised σ comes out.
    """

    def vol(self, strike: float, expiry: float) -> float:
        """Return the annualised volatility for this (strike, expiry)."""
        ...


class FlatVolSurface:
    """Constant-σ surface: returns the same vol for every (strike, expiry).

    The Phase 4 default. Construct from config
    `agents.options_mm.vol_estimate` (or an `options.vol`).

    Args:
        sigma: The constant annualised volatility (fraction, > 0).

    Raises:
        ValueError: If `sigma <= 0`.
    """

    def __init__(self, sigma: float) -> None:
        if sigma <= 0:
            raise ValueError(f"sigma must be positive, got {sigma}")
        self._sigma: float = float(sigma)

    @property
    def sigma(self) -> float:
        """The constant volatility this surface returns."""
        return self._sigma

    def vol(self, strike: float, expiry: float) -> float:
        """Return the constant σ, ignoring `strike` and `expiry`."""
        return self._sigma

    def __repr__(self) -> str:
        return f"FlatVolSurface(sigma={self._sigma})"

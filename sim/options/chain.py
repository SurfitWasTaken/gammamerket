"""Options chain construction + the frozen unit-conversion sites (Phase 4).

This module owns the two conversions that every downstream Greek and Phase 5
hedge depends on (CLAUDE.md Phase 4 Implementation Contracts):

- **D1 — sim-time → years:** `time_to_expiry_years(...)` is the *single* place
  expiry-minutes are turned into BS `T` (years). Never inline that division.
- **D2 — integer-tick spot → BS S:** `spot_from_book(...)` is the *single*
  place the book mid (ticks) becomes the float spot `S`. Callers never multiply
  by `tick_size` themselves.

It also implements **D3** — strikes are generated from moneyness offsets around
an anchor spot and snapped to tick multiples; the chain is built **once** at the
anchor mid and strikes stay fixed for Phase 4 (re-striking is a Phase 5/6
decision).
"""

from __future__ import annotations

from dataclasses import dataclass

_MINUTES_PER_DAY: int = 24 * 60


@dataclass(frozen=True)
class OptionSeries:
    """One tradable option line: a (strike, expiry, call/put) triple.

    Args:
        strike: Strike price in integer ticks (snapped to a tick multiple).
        expiry_minutes: Absolute expiry time on the clock's minute axis
            (i.e. comparable to `MarketState.timestamp` / `Clock.now`).
        is_call: True for a call, False for a put.
    """

    strike: int
    expiry_minutes: float
    is_call: bool


# --- D2: integer-tick book mid → BS spot ------------------------------------


def spot_from_book(mid: float, tick_size: int) -> float:
    """Convert a book mid in ticks to a BS spot `S` (D2 — single site).

    With `tick_size == 1` this is exact (1 tick = 1 price unit). If
    `tick_size` ever differs, this is the one function that changes; callers
    must never multiply by `tick_size` themselves.

    Args:
        mid: Book mid in ticks (e.g. `MarketState.mid`). Must be > 0.
        tick_size: The book's tick size in price units.

    Returns:
        The float spot `S` in price units.

    Raises:
        ValueError: If `mid <= 0` or `tick_size <= 0`.
    """
    if mid <= 0:
        raise ValueError(f"mid must be positive, got {mid}")
    if tick_size <= 0:
        raise ValueError(f"tick_size must be positive, got {tick_size}")
    return float(mid) * float(tick_size)


# --- D1: expiry-minutes → BS T in years -------------------------------------


def time_to_expiry_years(
    series: OptionSeries, now_minutes: float, minutes_per_year: float
) -> float:
    """Convert a series' expiry to BS `T` in years (D1 — single site).

    Args:
        series: The option series whose expiry to measure.
        now_minutes: Current clock time in minutes.
        minutes_per_year: Calendar constant (continuous convention =
            525_600). From `market.minutes_per_year`.

    Returns:
        `max(expiry_minutes - now_minutes, 0) / minutes_per_year`, clamped
        at 0 at/after expiry (never negative).

    Raises:
        ValueError: If `minutes_per_year <= 0`.
    """
    if minutes_per_year <= 0:
        raise ValueError(f"minutes_per_year must be positive, got {minutes_per_year}")
    remaining = max(series.expiry_minutes - now_minutes, 0.0)
    return remaining / minutes_per_year


# --- D3: moneyness → integer strikes ----------------------------------------


def _snap_to_tick(price: float, tick_size: int) -> int:
    """Round `price` to the nearest tick multiple, floored at one tick."""
    snapped = round(price / tick_size) * tick_size
    return max(int(snapped), tick_size)


def strikes_from_moneyness(
    anchor_spot: float, strikes_pct: list[float], tick_size: int
) -> list[int]:
    """Generate integer strikes from moneyness offsets around an anchor (D3).

    `K = round(anchor_spot * (1 + pct))` snapped to a tick multiple. At anchor
    10_000 and the default pcts → `[9500, 9750, 10000, 10250, 10500]`.

    Args:
        anchor_spot: The anchor spot in ticks (the book mid at construction).
        strikes_pct: Moneyness offsets (e.g. `[-0.05, 0.0, 0.05]`).
        tick_size: The book's tick size.

    Returns:
        Sorted, de-duplicated integer strikes (ascending).

    Raises:
        ValueError: If `anchor_spot <= 0` or `tick_size <= 0`.
    """
    if anchor_spot <= 0:
        raise ValueError(f"anchor_spot must be positive, got {anchor_spot}")
    if tick_size <= 0:
        raise ValueError(f"tick_size must be positive, got {tick_size}")
    strikes = {_snap_to_tick(anchor_spot * (1.0 + pct), tick_size) for pct in strikes_pct}
    return sorted(strikes)


def build_chain(
    anchor_spot: float,
    now_minutes: float,
    *,
    strikes_pct: list[float],
    expiries_days: list[float],
    tick_size: int = 1,
) -> list[OptionSeries]:
    """Build the strikes × expiries × {call, put} grid anchored to the book.

    The chain is constructed **once** at the anchor mid (D3); strikes are
    fixed thereafter for Phase 4. Expiries are absolute clock-minute times
    `now_minutes + days * 1440`.

    Args:
        anchor_spot: Anchor spot in ticks (the live book mid at construction).
        now_minutes: Current clock time in minutes (the strike clock origin).
        strikes_pct: Moneyness offsets (D3).
        expiries_days: Expiries in calendar days from now.
        tick_size: The book's tick size (default 1).

    Returns:
        A list of `OptionSeries`, ordered by (expiry, strike, call-before-put),
        of length `len(unique strikes) × len(expiries) × 2`.

    Raises:
        ValueError: If `strikes_pct` or `expiries_days` is empty, or via the
            underlying `strikes_from_moneyness` validation.
    """
    if not strikes_pct:
        raise ValueError("strikes_pct must be non-empty")
    if not expiries_days:
        raise ValueError("expiries_days must be non-empty")

    strikes = strikes_from_moneyness(anchor_spot, strikes_pct, tick_size)
    chain: list[OptionSeries] = []
    for days in expiries_days:
        expiry_minutes = now_minutes + float(days) * _MINUTES_PER_DAY
        for strike in strikes:
            for is_call in (True, False):
                chain.append(
                    OptionSeries(
                        strike=strike,
                        expiry_minutes=expiry_minutes,
                        is_call=is_call,
                    )
                )
    return chain


def find_series(
    chain: list[OptionSeries],
    strike: int,
    expiry_minutes: float,
    is_call: bool,
) -> OptionSeries:
    """Look up the unique series matching (strike, expiry, call/put).

    Args:
        chain: A chain from `build_chain`.
        strike: Strike in ticks.
        expiry_minutes: Absolute expiry on the clock-minute axis.
        is_call: True for a call, False for a put.

    Returns:
        The matching `OptionSeries`.

    Raises:
        KeyError: If no series matches.
    """
    for series in chain:
        if (
            series.strike == strike
            and series.expiry_minutes == expiry_minutes
            and series.is_call is is_call
        ):
            return series
    raise KeyError(
        f"no series strike={strike} expiry_minutes={expiry_minutes} is_call={is_call}"
    )

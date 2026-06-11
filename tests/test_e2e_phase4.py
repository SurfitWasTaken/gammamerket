"""Phase 4 end-to-end: the options library composes with the live sim.

Proves the `sim/options/` package builds a chain off a *real* `run()` result's
book mid and prices every series with finite values + put-call parity holding
across the whole chain — without wiring any new agent (Phase 4 ships a library,
not market behaviour).
"""

from __future__ import annotations

import math

import pytest

from run_sim import run
from sim.config.loader import load_config
from sim.options.chain import (
    build_chain,
    find_series,
    spot_from_book,
    time_to_expiry_years,
)
from sim.options.pricer import bs_greeks, bs_price
from sim.options.surface import FlatVolSurface


@pytest.fixture(scope="module")
def sim_result():
    return run(load_config())


def _anchor_mid(result) -> float:
    """Live mid from the run's book, falling back to the last fill price."""
    book = result["book"]
    mid = book.mid()
    if mid is None:
        mid = result["tape"].last_fill_price()
    assert mid is not None and mid > 0, "sim produced no usable price anchor"
    return float(mid)


def test_chain_builds_off_live_book_mid(sim_result):
    cfg = sim_result["cfg"]
    now = float(sim_result["clock"].now)
    anchor = spot_from_book(_anchor_mid(sim_result), int(cfg["market"]["tick_size"]))
    chain = build_chain(
        anchor,
        now,
        strikes_pct=cfg["options"]["strikes_pct"],
        expiries_days=cfg["options"]["expiries_days"],
        tick_size=int(cfg["market"]["tick_size"]),
    )
    n_strikes = len(cfg["options"]["strikes_pct"])
    n_expiries = len(cfg["options"]["expiries_days"])
    assert len(chain) == n_strikes * n_expiries * 2
    # All expiries are strictly in the future relative to the live clock.
    for s in chain:
        assert s.expiry_minutes > now


def test_every_series_prices_finite_and_greeks_finite(sim_result):
    cfg = sim_result["cfg"]
    now = float(sim_result["clock"].now)
    tick = int(cfg["market"]["tick_size"])
    r = float(cfg["options"]["risk_free_rate"])
    mpy = float(cfg["market"]["minutes_per_year"])
    surface = FlatVolSurface(float(cfg["agents"]["options_mm"]["vol_estimate"]))

    S = spot_from_book(_anchor_mid(sim_result), tick)
    chain = build_chain(
        S,
        now,
        strikes_pct=cfg["options"]["strikes_pct"],
        expiries_days=cfg["options"]["expiries_days"],
        tick_size=tick,
    )

    for series in chain:
        T = time_to_expiry_years(series, now, mpy)
        sigma = surface.vol(series.strike, series.expiry_minutes)
        price = bs_price(S, float(series.strike), T, r, sigma, is_call=series.is_call)
        g = bs_greeks(S, float(series.strike), T, r, sigma, is_call=series.is_call)
        assert math.isfinite(price) and price >= 0.0
        assert math.isfinite(g.delta)
        assert math.isfinite(g.gamma) and g.gamma >= 0.0
        assert math.isfinite(g.vega) and g.vega >= 0.0


def test_put_call_parity_holds_across_the_chain(sim_result):
    cfg = sim_result["cfg"]
    now = float(sim_result["clock"].now)
    tick = int(cfg["market"]["tick_size"])
    r = float(cfg["options"]["risk_free_rate"])
    mpy = float(cfg["market"]["minutes_per_year"])
    sigma = float(cfg["agents"]["options_mm"]["vol_estimate"])

    S = spot_from_book(_anchor_mid(sim_result), tick)
    chain = build_chain(
        S,
        now,
        strikes_pct=cfg["options"]["strikes_pct"],
        expiries_days=cfg["options"]["expiries_days"],
        tick_size=tick,
    )

    # For each (strike, expiry), C - P must equal S - K e^{-rT}.
    seen: set[tuple[int, float]] = set()
    for series in chain:
        key = (series.strike, series.expiry_minutes)
        if key in seen:
            continue
        seen.add(key)
        call = find_series(chain, series.strike, series.expiry_minutes, is_call=True)
        put = find_series(chain, series.strike, series.expiry_minutes, is_call=False)
        T = time_to_expiry_years(call, now, mpy)
        c = bs_price(S, float(call.strike), T, r, sigma, is_call=True)
        p = bs_price(S, float(put.strike), T, r, sigma, is_call=False)
        expected = S - float(series.strike) * math.exp(-r * T)
        assert (c - p) == pytest.approx(expected, abs=1e-6)

    # Sanity: we actually exercised the full strike × expiry grid.
    assert len(seen) == len(cfg["options"]["strikes_pct"]) * len(
        cfg["options"]["expiries_days"]
    )

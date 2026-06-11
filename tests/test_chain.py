"""Tests for sim/options/chain.py — chain build + D1/D2/D3 conversions."""

from __future__ import annotations

import pytest

from sim.options.chain import (
    OptionSeries,
    build_chain,
    find_series,
    spot_from_book,
    strikes_from_moneyness,
    time_to_expiry_years,
)

STRIKES_PCT = [-0.05, -0.025, 0.0, 0.025, 0.05]
EXPIRIES_DAYS = [7, 14, 30]
MINUTES_PER_YEAR = 525_600
MINUTES_PER_DAY = 24 * 60


# --- D2: spot_from_book -----------------------------------------------------


def test_spot_from_book_identity_at_tick_one():
    assert spot_from_book(10000, 1) == 10000.0


def test_spot_from_book_scales_by_tick_size():
    assert spot_from_book(10000, 5) == 50000.0


@pytest.mark.parametrize("bad_mid", [0, -1])
def test_spot_from_book_rejects_nonpositive_mid(bad_mid):
    with pytest.raises(ValueError):
        spot_from_book(bad_mid, 1)


def test_spot_from_book_rejects_nonpositive_tick():
    with pytest.raises(ValueError):
        spot_from_book(10000, 0)


# --- D1: time_to_expiry_years -----------------------------------------------


def test_time_to_expiry_years_basic():
    s = OptionSeries(strike=10000, expiry_minutes=30 * MINUTES_PER_DAY, is_call=True)
    T = time_to_expiry_years(s, now_minutes=0.0, minutes_per_year=MINUTES_PER_YEAR)
    assert T == pytest.approx(30 / 365, abs=1e-9)


def test_time_to_expiry_years_decreases_as_now_advances():
    s = OptionSeries(strike=10000, expiry_minutes=14 * MINUTES_PER_DAY, is_call=True)
    earlier = time_to_expiry_years(s, 0.0, MINUTES_PER_YEAR)
    later = time_to_expiry_years(s, 7 * MINUTES_PER_DAY, MINUTES_PER_YEAR)
    assert later < earlier
    assert later == pytest.approx(7 / 365, abs=1e-9)


def test_time_to_expiry_years_clamps_at_zero_past_expiry():
    s = OptionSeries(strike=10000, expiry_minutes=7 * MINUTES_PER_DAY, is_call=True)
    assert time_to_expiry_years(s, 8 * MINUTES_PER_DAY, MINUTES_PER_YEAR) == 0.0


def test_time_to_expiry_years_rejects_nonpositive_calendar():
    s = OptionSeries(strike=10000, expiry_minutes=1000.0, is_call=True)
    with pytest.raises(ValueError):
        time_to_expiry_years(s, 0.0, 0.0)


# --- D3: strikes_from_moneyness ---------------------------------------------


def test_strikes_match_d3_rule_at_anchor_10000():
    strikes = strikes_from_moneyness(10000, STRIKES_PCT, tick_size=1)
    assert strikes == [9500, 9750, 10000, 10250, 10500]


def test_strikes_snapped_to_tick_multiples():
    strikes = strikes_from_moneyness(10000, STRIKES_PCT, tick_size=25)
    assert all(k % 25 == 0 for k in strikes)


def test_strikes_sorted_and_deduplicated():
    # Two pcts that snap to the same strike collapse to one.
    strikes = strikes_from_moneyness(10000, [0.0, 0.00001], tick_size=1)
    assert strikes == [10000]


def test_strikes_reject_nonpositive_anchor():
    with pytest.raises(ValueError):
        strikes_from_moneyness(0, STRIKES_PCT, tick_size=1)


# --- build_chain ------------------------------------------------------------


def test_chain_has_correct_cardinality():
    chain = build_chain(
        10000, 0.0, strikes_pct=STRIKES_PCT, expiries_days=EXPIRIES_DAYS
    )
    # 5 strikes × 3 expiries × {call, put}
    assert len(chain) == 5 * 3 * 2


def test_chain_strikes_and_expiries_are_correct():
    chain = build_chain(
        10000, 100.0, strikes_pct=STRIKES_PCT, expiries_days=EXPIRIES_DAYS
    )
    strikes = sorted({s.strike for s in chain})
    assert strikes == [9500, 9750, 10000, 10250, 10500]
    expiries = sorted({s.expiry_minutes for s in chain})
    assert expiries == [
        100.0 + 7 * MINUTES_PER_DAY,
        100.0 + 14 * MINUTES_PER_DAY,
        100.0 + 30 * MINUTES_PER_DAY,
    ]


def test_chain_has_both_call_and_put_per_strike_expiry():
    chain = build_chain(
        10000, 0.0, strikes_pct=[0.0], expiries_days=[30]
    )
    assert len(chain) == 2
    assert {s.is_call for s in chain} == {True, False}
    assert {s.strike for s in chain} == {10000}


def test_chain_rejects_empty_inputs():
    with pytest.raises(ValueError):
        build_chain(10000, 0.0, strikes_pct=[], expiries_days=[30])
    with pytest.raises(ValueError):
        build_chain(10000, 0.0, strikes_pct=[0.0], expiries_days=[])


# --- find_series ------------------------------------------------------------


def test_find_series_returns_matching_line():
    chain = build_chain(
        10000, 0.0, strikes_pct=STRIKES_PCT, expiries_days=EXPIRIES_DAYS
    )
    expiry = 30 * MINUTES_PER_DAY
    s = find_series(chain, strike=10250, expiry_minutes=expiry, is_call=False)
    assert s.strike == 10250
    assert s.expiry_minutes == expiry
    assert s.is_call is False


def test_find_series_raises_on_miss():
    chain = build_chain(10000, 0.0, strikes_pct=[0.0], expiries_days=[30])
    with pytest.raises(KeyError):
        find_series(chain, strike=99999, expiry_minutes=0.0, is_call=True)


def test_option_series_is_frozen():
    s = OptionSeries(strike=10000, expiry_minutes=1000.0, is_call=True)
    with pytest.raises(Exception):
        s.strike = 9999  # type: ignore[misc]

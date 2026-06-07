"""Tests for the analytics metrics module."""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from sim.analytics.metrics import (
    autocorrelation,
    fill_prices,
    fill_quantities,
    log_returns,
    simple_returns,
    trade_sizes,
)
from sim.core.events import Fill, Side


def _fill(price: int, qty: int = 1, ts: float = 1.0) -> Fill:
    return Fill(
        taker_order_id=uuid.uuid4(),
        maker_order_id=uuid.uuid4(),
        taker_agent_id="t",
        maker_agent_id="m",
        aggressor_side=Side.BUY,
        price=price,
        qty=qty,
        timestamp=ts,
    )


def test_fill_prices_returns_int_array_in_order() -> None:
    fills = [_fill(100), _fill(101), _fill(99)]
    arr = fill_prices(fills)
    assert arr.dtype == np.int64
    assert arr.tolist() == [100, 101, 99]


def test_fill_prices_empty() -> None:
    assert fill_prices([]).shape == (0,)


def test_fill_quantities_returns_int_array() -> None:
    fills = [_fill(100, qty=1), _fill(101, qty=3), _fill(99, qty=2)]
    arr = fill_quantities(fills)
    assert arr.dtype == np.int64
    assert arr.tolist() == [1, 3, 2]


def test_trade_sizes_alias_matches_quantities() -> None:
    fills = [_fill(100, qty=2), _fill(101, qty=4)]
    assert np.array_equal(trade_sizes(fills), fill_quantities(fills))


def test_simple_returns_basic() -> None:
    prices = np.array([100, 110, 99], dtype=np.int64)
    r = simple_returns(prices)
    assert r.shape == (2,)
    assert r[0] == pytest.approx(0.10)
    assert r[1] == pytest.approx(-0.10)


def test_simple_returns_constant_price() -> None:
    prices = np.array([100, 100, 100], dtype=np.int64)
    r = simple_returns(prices)
    assert np.all(r == 0.0)


def test_simple_returns_short_input() -> None:
    assert simple_returns(np.array([100], dtype=np.int64)).shape == (0,)
    assert simple_returns(np.array([], dtype=np.int64)).shape == (0,)


def test_log_returns_basic() -> None:
    prices = np.array([100, 110, 99], dtype=np.int64)
    r = log_returns(prices)
    assert r.shape == (2,)
    assert r[0] == pytest.approx(np.log(1.1))
    assert r[1] == pytest.approx(np.log(99 / 110))


def test_autocorrelation_white_noise_near_zero() -> None:
    rng = np.random.default_rng(42)
    r = rng.standard_normal(20_000)
    acf = autocorrelation(r, max_lag=5)
    assert acf.shape == (5,)
    assert abs(acf[0]) < 0.02
    assert np.all(np.abs(acf) < 0.05)


def test_autocorrelation_positive_for_ar1() -> None:
    rng = np.random.default_rng(0)
    n = 50_000
    eps = rng.standard_normal(n)
    r = np.empty(n)
    r[0] = eps[0]
    for i in range(1, n):
        r[i] = 0.7 * r[i - 1] + eps[i]
    acf = autocorrelation(r, max_lag=3)
    assert acf[0] == pytest.approx(0.7, abs=0.02)
    assert acf[1] == pytest.approx(0.49, abs=0.02)


def test_autocorrelation_constant_returns_returns_zeros() -> None:
    r = np.ones(100)
    acf = autocorrelation(r, max_lag=4)
    assert np.all(acf == 0.0)


def test_autocorrelation_short_input() -> None:
    acf = autocorrelation(np.array([1.0]), max_lag=3)
    assert np.array_equal(acf, np.zeros(3))


def test_autocorrelation_rejects_zero_max_lag() -> None:
    with pytest.raises(ValueError, match="max_lag must be >= 1"):
        autocorrelation(np.array([1.0, 2.0, 3.0]), max_lag=0)

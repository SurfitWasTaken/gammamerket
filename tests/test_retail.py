"""Tests for the retail noise-trader agent."""

from __future__ import annotations

import numpy as np
import pytest

from sim.agents.base import MarketState
from sim.agents.retail import Retail
from sim.core.events import Side


def _state() -> MarketState:
    return MarketState(
        best_bid=99,
        best_ask=101,
        mid=100.0,
        last_fill_price=100,
        own_position=0,
        timestamp=1.0,
    )


def test_retail_emits_exactly_one_order_per_step() -> None:
    a = Retail("r0", order_size_mean=1.0, direction_bias=0.0, rng=np.random.default_rng(0))
    for _ in range(50):
        orders = a.step(_state())
        assert len(orders) == 1


def test_retail_submits_only_market_orders() -> None:
    a = Retail("r0", order_size_mean=1.0, direction_bias=0.0, rng=np.random.default_rng(1))
    for _ in range(1000):
        orders = a.step(_state())
        for o in orders:
            assert o.price == 0, f"expected market order, got price={o.price}"


def test_retail_order_qty_is_positive_integer() -> None:
    a = Retail("r0", order_size_mean=1.0, direction_bias=0.0, rng=np.random.default_rng(2))
    for _ in range(500):
        o = a.step(_state())[0]
        assert o.qty >= 1
        assert isinstance(o.qty, int)


def test_retail_direction_is_50_50_over_1000_samples() -> None:
    rng = np.random.default_rng(7)
    a = Retail("r0", order_size_mean=1.0, direction_bias=0.0, rng=rng)
    buys = 0
    n = 1000
    for _ in range(n):
        o = a.step(_state())[0]
        if o.side is Side.BUY:
            buys += 1
    assert 400 <= buys <= 600, f"got {buys} buys out of {n}"


def test_retail_qty_geometric_mean_matches_order_size_mean() -> None:
    rng = np.random.default_rng(11)
    target_mean = 3.0
    a = Retail("r0", order_size_mean=target_mean, direction_bias=0.0, rng=rng)
    qtys = [a.step(_state())[0].qty for _ in range(20_000)]
    empirical = float(np.mean(qtys))
    assert abs(empirical - target_mean) < 0.1 * target_mean, (
        f"empirical mean {empirical:.3f} vs target {target_mean}"
    )


def test_retail_direction_bias_shifts_buy_probability() -> None:
    rng = np.random.default_rng(13)
    a = Retail("r0", order_size_mean=1.0, direction_bias=0.3, rng=rng)
    buys = 0
    n = 2000
    for _ in range(n):
        if a.step(_state())[0].side is Side.BUY:
            buys += 1
    assert 1500 < buys < 1700, f"got {buys}/{n} buys with bias=0.3"


def test_retail_validates_order_size_mean() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="order_size_mean must be positive"):
        Retail("r0", order_size_mean=0.0, direction_bias=0.0, rng=rng)
    with pytest.raises(ValueError, match="order_size_mean must be positive"):
        Retail("r0", order_size_mean=-1.0, direction_bias=0.0, rng=rng)


def test_retail_validates_direction_bias() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="direction_bias must be in"):
        Retail("r0", order_size_mean=1.0, direction_bias=0.6, rng=rng)
    with pytest.raises(ValueError, match="direction_bias must be in"):
        Retail("r0", order_size_mean=1.0, direction_bias=-0.6, rng=rng)


def test_retail_order_id_is_unique_per_step() -> None:
    a = Retail("r0", order_size_mean=1.0, direction_bias=0.0, rng=np.random.default_rng(0))
    ids = {a.step(_state())[0].order_id for _ in range(100)}
    assert len(ids) == 100


def test_retail_order_carries_agent_id() -> None:
    a = Retail("retail_007", order_size_mean=1.0, direction_bias=0.0, rng=np.random.default_rng(0))
    o = a.step(_state())[0]
    assert o.agent_id == "retail_007"

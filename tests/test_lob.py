"""Test suite for the limit order book (Phase 1)."""

from __future__ import annotations

import uuid

import pytest

from sim.core.events import Order, Side
from sim.core.lob import LimitOrderBook


class OrderFactory:
    """Build Orders with deterministic IDs and monotonic timestamps."""

    def __init__(self) -> None:
        self._t = 0

    def _next_ts(self) -> float:
        self._t += 1
        return float(self._t)

    def limit(
        self,
        side: Side,
        price: int,
        qty: int = 1,
        agent: str = "A",
    ) -> Order:
        return Order(
            order_id=uuid.uuid4(),
            agent_id=agent,
            side=side,
            price=price,
            qty=qty,
            timestamp=self._next_ts(),
        )

    def market(self, side: Side, qty: int = 1, agent: str = "A") -> Order:
        return Order(
            order_id=uuid.uuid4(),
            agent_id=agent,
            side=side,
            price=0,
            qty=qty,
            timestamp=self._next_ts(),
        )


@pytest.fixture
def book() -> LimitOrderBook:
    return LimitOrderBook(tick_size=1)


@pytest.fixture
def make() -> OrderFactory:
    return OrderFactory()


def test_market_order_fully_fills_in_price_time_order(book, make) -> None:
    book.submit_limit(make.limit(Side.BUY, 100, qty=1, agent="b1"))
    book.submit_limit(make.limit(Side.BUY, 99, qty=1, agent="b2"))
    book.submit_limit(make.limit(Side.BUY, 98, qty=1, agent="b3"))

    fills = book.submit_market(make.market(Side.SELL, qty=3))

    assert len(fills) == 3
    assert [f.price for f in fills] == [100, 99, 98]
    assert [f.qty for f in fills] == [1, 1, 1]
    assert all(f.aggressor_side is Side.SELL for f in fills)
    assert book.best_bid() is None
    assert book.best_ask() is None
    assert len(book) == 0


def test_partial_fill_reduces_resting_qty_and_rests_surplus(book, make) -> None:
    bid_id = make.limit(Side.BUY, 100, qty=3, agent="b1").order_id
    bid = Order(
        order_id=bid_id,
        agent_id="b1",
        side=Side.BUY,
        price=100,
        qty=3,
        timestamp=0.5,
    )
    book.submit_limit(bid)

    fills = book.submit_market(make.market(Side.SELL, qty=5))

    assert len(fills) == 1
    assert fills[0].price == 100
    assert fills[0].qty == 3
    assert book.best_bid() is None
    assert book.best_ask() == 100
    assert book.depth(Side.SELL, 100) == 2
    assert len(book) == 1


def test_price_time_priority_same_price(book, make) -> None:
    first = make.limit(Side.BUY, 100, qty=1, agent="b1")
    second = make.limit(Side.BUY, 100, qty=1, agent="b2")
    book.submit_limit(first)
    book.submit_limit(second)

    fills = book.submit_market(make.market(Side.SELL, qty=1))

    assert len(fills) == 1
    assert fills[0].maker_order_id == first.order_id
    assert book.best_bid() == 100
    assert book.depth(Side.BUY, 100) == 1


def test_cancel_removes_order_subsequent_market_skips(book, make) -> None:
    victim = make.limit(Side.BUY, 100, qty=1, agent="b1")
    survivor = make.limit(Side.BUY, 99, qty=1, agent="b2")
    book.submit_limit(victim)
    book.submit_limit(survivor)

    assert book.cancel(victim.order_id) is True

    fills = book.submit_market(make.market(Side.SELL, qty=1))

    assert len(fills) == 1
    assert fills[0].price == 99
    assert fills[0].maker_order_id == survivor.order_id


def test_cancel_returns_false_for_unknown_or_filled(book, make) -> None:
    assert book.cancel(uuid.uuid4()) is False

    o = make.limit(Side.BUY, 100, qty=1)
    book.submit_limit(o)
    assert book.cancel(o.order_id) is True
    assert book.cancel(o.order_id) is False

    p = make.limit(Side.BUY, 99, qty=1)
    book.submit_limit(p)
    m = make.market(Side.SELL, qty=1)
    fills = book.submit_market(m)
    assert len(fills) == 1
    assert fills[0].maker_order_id == p.order_id
    assert book.cancel(m.order_id) is False
    assert book.cancel(p.order_id) is False
    assert book.cancel(o.order_id) is False


def test_empty_book_market_returns_no_fills_and_no_resting(book, make) -> None:
    fills = book.submit_market(make.market(Side.BUY, qty=5))
    assert fills == []
    assert book.best_bid() is None
    assert book.best_ask() is None
    assert len(book) == 0


def test_market_order_rests_remainder_at_last_touched_price(book, make) -> None:
    book.submit_limit(make.limit(Side.SELL, 100, qty=1, agent="s1"))
    book.submit_limit(make.limit(Side.SELL, 101, qty=5, agent="s2"))

    fills = book.submit_market(make.market(Side.BUY, qty=7))

    assert [(f.price, f.qty) for f in fills] == [(100, 1), (101, 5)]
    assert book.best_bid() == 101
    assert book.best_ask() is None
    assert book.depth(Side.BUY, 101) == 1
    assert len(book) == 1


def test_spread_at_least_one_tick_when_two_sided(book, make) -> None:
    book.submit_limit(make.limit(Side.BUY, 100, qty=1))
    book.submit_limit(make.limit(Side.SELL, 101, qty=1))

    assert book.spread() == 1
    assert book.mid() == 100.5

    book.submit_limit(make.limit(Side.BUY, 99, qty=1))
    assert book.best_bid() == 100
    assert book.spread() == 1

    book.submit_limit(make.limit(Side.SELL, 102, qty=1))
    assert book.best_ask() == 101
    assert book.spread() == 1

    book.submit_limit(make.limit(Side.BUY, 95, qty=1))
    book.submit_limit(make.limit(Side.SELL, 105, qty=1))
    fills = book.submit_market(make.market(Side.SELL, qty=1))
    assert fills[0].price == 100
    assert book.best_bid() == 99
    assert book.best_ask() == 101
    assert book.spread() == 2


def test_best_bid_best_ask_mid_none_when_one_sided(book, make) -> None:
    book.submit_limit(make.limit(Side.BUY, 100, qty=1))
    assert book.best_bid() == 100
    assert book.best_ask() is None
    assert book.mid() is None
    assert book.spread() is None

    book.submit_limit(make.limit(Side.SELL, 105, qty=1))
    assert book.best_bid() == 100
    assert book.best_ask() == 105
    assert book.mid() == 102.5


def test_limit_marketable_order_sweeps_then_rests_remainder(book, make) -> None:
    book.submit_limit(make.limit(Side.SELL, 100, qty=2, agent="s1"))
    book.submit_limit(make.limit(Side.SELL, 101, qty=2, agent="s2"))

    fills = book.submit_limit(make.limit(Side.BUY, 102, qty=5))

    assert [(f.price, f.qty) for f in fills] == [(100, 2), (101, 2)]
    assert book.best_bid() == 102
    assert book.best_ask() is None
    assert book.depth(Side.BUY, 102) == 1
    assert len(book) == 1


def test_off_tick_price_rejected() -> None:
    book = LimitOrderBook(tick_size=2)
    bad = Order(
        order_id=uuid.uuid4(),
        agent_id="A",
        side=Side.BUY,
        price=101,
        qty=1,
        timestamp=1.0,
    )
    with pytest.raises(ValueError, match="multiple of tick_size"):
        book.submit_limit(bad)


def test_invalid_qty_or_price_rejected(book, make) -> None:
    bad_qty = Order(
        order_id=uuid.uuid4(),
        agent_id="A",
        side=Side.BUY,
        price=100,
        qty=0,
        timestamp=1.0,
    )
    with pytest.raises(ValueError, match="qty must be positive"):
        book.submit_limit(bad_qty)

    bad_price = Order(
        order_id=uuid.uuid4(),
        agent_id="A",
        side=Side.BUY,
        price=0,
        qty=1,
        timestamp=1.0,
    )
    with pytest.raises(ValueError, match="price must be positive"):
        book.submit_limit(bad_price)

    with pytest.raises(ValueError, match="qty must be positive"):
        book.submit_market(make.market(Side.BUY, qty=0))

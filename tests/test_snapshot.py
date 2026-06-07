"""Tests for the snapshot serializer."""

from __future__ import annotations

import json

import pytest

from sim.core.events import Order, Side
from sim.core.lob import LimitOrderBook
from sim.snapshot import book_snapshot


def _order(side: Side, price: int, qty: int = 1, ts: float = 1.0) -> Order:
    import uuid
    return Order(uuid.uuid4(), "A", side, price, qty, ts)


def test_snapshot_empty_book_is_json_serializable() -> None:
    book = LimitOrderBook(tick_size=1)
    snap = book_snapshot(book, [], timestamp=0.0)
    encoded = json.dumps(snap)
    decoded = json.loads(encoded)
    assert decoded == snap


def test_snapshot_fields_present_when_empty() -> None:
    book = LimitOrderBook(tick_size=1)
    snap = book_snapshot(book, [], timestamp=3.5)
    assert snap["timestamp"] == 3.5
    assert snap["best_bid"] is None
    assert snap["best_ask"] is None
    assert snap["spread"] is None
    assert snap["mid"] is None
    assert snap["n_orders"] == 0
    assert snap["bids"] == {}
    assert snap["asks"] == {}
    assert snap["fills"] == []


def test_snapshot_reflects_resting_depth() -> None:
    book = LimitOrderBook(tick_size=1)
    book.submit_limit(_order(Side.BUY, 100, qty=3, ts=1.0))
    book.submit_limit(_order(Side.BUY, 99, qty=5, ts=2.0))
    book.submit_limit(_order(Side.SELL, 101, qty=2, ts=3.0))
    book.submit_limit(_order(Side.SELL, 102, qty=7, ts=4.0))

    snap = book_snapshot(book, [], timestamp=5.0)

    assert snap["best_bid"] == 100
    assert snap["best_ask"] == 101
    assert snap["spread"] == 1
    assert snap["mid"] == 100.5
    assert snap["n_orders"] == 4
    assert snap["bids"] == {"100": 3, "99": 5}
    assert snap["asks"] == {"101": 2, "102": 7}


def test_snapshot_market_surplus_rests_at_last_touched() -> None:
    book = LimitOrderBook(tick_size=1)
    book.submit_limit(_order(Side.BUY, 100, qty=1, ts=1.0))
    book.submit_market(_order(Side.SELL, 0, qty=3, ts=2.0))

    snap = book_snapshot(book, [], timestamp=2.0)

    assert snap["bids"] == {}
    assert snap["asks"] == {"100": 2}
    assert snap["best_bid"] is None
    assert snap["best_ask"] == 100


def test_snapshot_includes_fills_history() -> None:
    book = LimitOrderBook(tick_size=1)
    book.submit_limit(_order(Side.SELL, 100, qty=1, ts=1.0))
    book.submit_market(_order(Side.BUY, 1, ts=2.0))

    fills = [
        {"ts": 2.0, "side": "BUY", "price": 100, "qty": 1},
    ]
    snap = book_snapshot(book, fills, timestamp=2.0)

    assert snap["fills"] == fills
    encoded = json.dumps(snap)
    assert "BUY" in encoded
    assert "100" in encoded


def test_snapshot_roundtrips_through_json() -> None:
    book = LimitOrderBook(tick_size=1)
    book.submit_limit(_order(Side.BUY, 99, qty=4, ts=1.0))
    book.submit_limit(_order(Side.SELL, 100, qty=2, ts=2.0))

    snap = book_snapshot(
        book,
        [{"ts": 3.0, "side": "BUY", "price": 100, "qty": 1}],
        timestamp=3.0,
    )
    payload = json.loads(json.dumps(snap))
    assert payload["best_bid"] == 99
    assert payload["best_ask"] == 100
    assert payload["spread"] == 1
    assert payload["mid"] == 99.5
    assert payload["bids"] == {"99": 4}
    assert payload["asks"] == {"100": 2}
    assert payload["fills"] == [{"ts": 3.0, "side": "BUY", "price": 100, "qty": 1}]

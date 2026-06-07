"""Tests for the central fill tape."""

from __future__ import annotations

import uuid

import numpy as np

from sim.core.events import Fill, Side
from sim.core.tape import Tape


def _fill(price: int, qty: int = 1, ts: float = 1.0) -> Fill:
    return Fill(
        taker_order_id=uuid.uuid4(),
        maker_order_id=uuid.uuid4(),
        taker_agent_id="taker",
        maker_agent_id="maker",
        aggressor_side=Side.BUY,
        price=price,
        qty=qty,
        timestamp=ts,
    )


def test_tape_starts_empty() -> None:
    t = Tape()
    assert len(t) == 0
    assert list(t) == []
    assert t.last_fill_price() is None
    assert t.prices().shape == (0,)


def test_tape_records_fills_in_order() -> None:
    t = Tape()
    f1 = _fill(100, ts=1.0)
    f2 = _fill(101, ts=2.0)
    f3 = _fill(99, ts=3.0)
    t.append(f1)
    t.append(f2)
    t.append(f3)
    assert [f.price for f in t] == [100, 101, 99]
    assert len(t) == 3


def test_tape_last_fill_price_returns_most_recent() -> None:
    t = Tape()
    t.append(_fill(100))
    assert t.last_fill_price() == 100
    t.append(_fill(105))
    assert t.last_fill_price() == 105


def test_tape_last_fill_price_none_when_empty() -> None:
    assert Tape().last_fill_price() is None


def test_tape_prices_returns_int_array_in_order() -> None:
    t = Tape()
    t.append(_fill(100))
    t.append(_fill(101))
    t.append(_fill(99))
    arr = t.prices()
    assert arr.dtype == np.int64
    assert arr.tolist() == [100, 101, 99]


def test_tape_prices_empty_when_no_fills() -> None:
    assert Tape().prices().shape == (0,)

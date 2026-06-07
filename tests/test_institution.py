"""Tests for the institutional speculator."""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from sim.agents.base import MarketState
from sim.agents.institution import Institution
from sim.core.events import Cancel, Fill, Order, Side


def _state(
    mid: float | None = 100.0,
    bid: int | None = 99,
    ask: int | None = 101,
    timestamp: float = 1.0,
) -> MarketState:
    return MarketState(
        best_bid=bid,
        best_ask=ask,
        mid=mid,
        last_fill_price=100,
        own_position=0,
        timestamp=timestamp,
    )


def _buy_fill(order_id: uuid.UUID, qty: int, price: int = 99, maker_agent_id: str = "inst0") -> Fill:
    return Fill(
        taker_order_id=uuid.uuid4(),
        maker_order_id=order_id,
        taker_agent_id="other",
        maker_agent_id=maker_agent_id,
        aggressor_side=Side.SELL,
        price=price,
        qty=qty,
        timestamp=1.0,
    )


def _institution(**overrides) -> Institution:
    kwargs = dict(
        agent_id="inst0",
        signal_halflife=30.0,
        signal_sigma=1.0,
        threshold=0.5,
        position_limit=500,
        quote_offset_ticks=1,
        scale=100,
        signal_price_scale=0,
        initial_price=100,
        rng=np.random.default_rng(0),
    )
    kwargs.update(overrides)
    return Institution(**kwargs)


def test_institution_no_order_when_signal_within_threshold() -> None:
    inst = _institution()
    inst.signal = 0.0
    actions = inst.step(_state())
    assert all(isinstance(a, Order) for a in actions)
    assert len(actions) == 0

    inst.signal = 0.3
    actions = inst.step(_state())
    assert len(actions) == 0


def test_institution_places_order_using_initial_price_when_mid_is_none() -> None:
    """When the book is one-sided the institution falls back to the
    initial price as the mid reference so it can still quote."""
    inst = _institution(initial_price=100)
    inst.signal = 1.0
    actions = inst.step(_state(mid=None, bid=None, ask=None))
    assert len(actions) == 1
    order = actions[0]
    assert isinstance(order, Order)
    assert order.side is Side.BUY
    assert order.price == 101


def test_institution_buy_limit_above_mid_when_signal_positive() -> None:
    inst = _institution()
    inst.signal = 1.0
    actions = inst.step(_state(mid=100.0))
    assert len(actions) == 1
    order = actions[0]
    assert isinstance(order, Order)
    assert order.side is Side.BUY
    assert order.price > 100, f"expected price > mid, got {order.price}"


def test_institution_sell_limit_below_mid_when_signal_negative() -> None:
    inst = _institution()
    inst.signal = -1.0
    actions = inst.step(_state(mid=100.0))
    assert len(actions) == 1
    order = actions[0]
    assert isinstance(order, Order)
    assert order.side is Side.SELL
    assert order.price < 100, f"expected price < mid, got {order.price}"


def test_institution_buy_price_offset_is_quote_offset_ticks() -> None:
    inst = _institution(quote_offset_ticks=3, initial_price=100)
    inst.signal = 1.0
    actions = inst.step(_state(mid=100.0))
    order = actions[0]
    assert isinstance(order, Order)
    assert order.price == 103


def test_institution_sell_price_offset_is_quote_offset_ticks() -> None:
    inst = _institution(quote_offset_ticks=2, initial_price=100)
    inst.signal = -1.0
    actions = inst.step(_state(mid=100.0))
    order = actions[0]
    assert isinstance(order, Order)
    assert order.price == 98


def test_institution_signal_price_scale_offsets_buy() -> None:
    inst = _institution(signal_price_scale=5, quote_offset_ticks=1, initial_price=100)
    inst.signal = 2.0
    actions = inst.step(_state(mid=100.0))
    order = actions[0]
    assert isinstance(order, Order)
    assert order.side is Side.BUY
    assert order.price == 111


def test_institution_signal_price_scale_offsets_sell() -> None:
    inst = _institution(signal_price_scale=5, quote_offset_ticks=1, initial_price=100)
    inst.signal = -2.0
    actions = inst.step(_state(mid=100.0))
    order = actions[0]
    assert isinstance(order, Order)
    assert order.side is Side.SELL
    assert order.price == 89


def test_institution_uses_initial_price_not_state_mid() -> None:
    """Posting must be anchored to the configured initial price, not
    the current mid — using the current mid would create a
    self-referencing loop and pin the price at the seed BBO."""
    inst = _institution(signal_price_scale=0, quote_offset_ticks=1, initial_price=100)
    inst.signal = 1.0
    actions = inst.step(_state(mid=150.0))
    order = actions[0]
    assert isinstance(order, Order)
    assert order.price == 101, (
        f"expected price anchored to initial_price=100, got {order.price}"
    )


def test_institution_qty_scales_with_signal_and_scale() -> None:
    inst = _institution(scale=100)
    inst.signal = 1.5
    actions = inst.step(_state())
    order = actions[0]
    assert isinstance(order, Order)
    assert order.qty == 150


def test_institution_target_clipped_to_position_limit() -> None:
    inst = _institution(scale=1000, position_limit=200)
    inst.signal = 5.0
    actions = inst.step(_state())
    order = actions[0]
    assert isinstance(order, Order)
    assert order.qty == 200


def test_institution_qty_capped_by_position_limit_after_partial_fill() -> None:
    inst = _institution(position_limit=100, scale=10)
    inst.signal = 10.0
    inst.position = 80
    actions = inst.step(_state())
    order = actions[0]
    assert isinstance(order, Order)
    assert order.qty == 20


def test_institution_no_buy_when_already_at_target() -> None:
    inst = _institution(scale=10)
    inst.signal = 5.0
    inst.position = 50
    actions = inst.step(_state())
    assert all(isinstance(a, Order) for a in actions)
    assert len(actions) == 0


def test_institution_keeps_resting_order_when_partially_filled() -> None:
    """A partially filled resting order must NOT be cancelled and
    replaced on the next step — that would discard the resting
    surplus and pin the price at the seed BBO."""
    inst = _institution()
    inst.signal = 1.0
    first = inst.step(_state())
    first_order = [a for a in first if isinstance(a, Order)][0]
    assert inst.resting_order_id == first_order.order_id

    inst.on_fills([_buy_fill(first_order.order_id, qty=10)])

    inst.signal = -1.0
    second = inst.step(_state())
    assert not any(isinstance(a, Cancel) for a in second)
    assert not any(isinstance(a, Order) for a in second)
    assert inst.resting_order_id == first_order.order_id


def test_institution_replaces_order_only_after_full_fill() -> None:
    inst = _institution()
    inst.signal = 1.0
    first = inst.step(_state())
    first_order = [a for a in first if isinstance(a, Order)][0]
    inst.on_fills([_buy_fill(first_order.order_id, qty=first_order.qty)])

    inst.signal = -1.0
    second = inst.step(_state())
    assert not any(isinstance(a, Cancel) for a in second)
    order_actions = [a for a in second if isinstance(a, Order)]
    assert len(order_actions) == 1
    assert order_actions[0].side is Side.SELL
    assert inst.resting_order_id == order_actions[0].order_id


def test_institution_no_cancel_when_no_prior_order() -> None:
    inst = _institution()
    inst.signal = 1.0
    actions = inst.step(_state())
    assert not any(isinstance(a, Cancel) for a in actions)
    assert len([a for a in actions if isinstance(a, Order)]) == 1


def test_institution_keeps_resting_id_after_partial_fill() -> None:
    inst = _institution()
    inst.signal = 1.0
    actions = inst.step(_state())
    order = [a for a in actions if isinstance(a, Order)][0]
    assert inst.resting_order_id == order.order_id

    inst.on_fills([_buy_fill(order.order_id, qty=10)])

    assert inst.position == 10
    assert inst.resting_order_id == order.order_id


def test_institution_clears_resting_id_after_full_fill() -> None:
    inst = _institution()
    inst.signal = 1.0
    actions = inst.step(_state())
    order = [a for a in actions if isinstance(a, Order)][0]
    inst.on_fills([_buy_fill(order.order_id, qty=order.qty)])

    assert inst.resting_order_id is None


def test_institution_ou_signal_mean_reverts_toward_zero() -> None:
    rng = np.random.default_rng(7)
    inst = _institution(signal_halflife=10.0, signal_sigma=0.5, rng=rng)
    inst.signal = 10.0
    for t in range(1, 5001):
        inst.step(_state(timestamp=float(t)))
    assert abs(inst.signal) < 5.0, f"signal did not mean-revert: {inst.signal}"


def test_institution_validates_inputs() -> None:
    rng = np.random.default_rng(0)
    with pytest.raises(ValueError, match="signal_halflife"):
        Institution("i", signal_halflife=0, signal_sigma=1, threshold=0.5,
                    position_limit=100, quote_offset_ticks=1, scale=10,
                    signal_price_scale=0, initial_price=100, rng=rng)
    with pytest.raises(ValueError, match="signal_sigma"):
        Institution("i", signal_halflife=10, signal_sigma=-1, threshold=0.5,
                    position_limit=100, quote_offset_ticks=1, scale=10,
                    signal_price_scale=0, initial_price=100, rng=rng)
    with pytest.raises(ValueError, match="threshold"):
        Institution("i", signal_halflife=10, signal_sigma=1, threshold=-1,
                    position_limit=100, quote_offset_ticks=1, scale=10,
                    signal_price_scale=0, initial_price=100, rng=rng)
    with pytest.raises(ValueError, match="position_limit"):
        Institution("i", signal_halflife=10, signal_sigma=1, threshold=0.5,
                    position_limit=0, quote_offset_ticks=1, scale=10,
                    signal_price_scale=0, initial_price=100, rng=rng)
    with pytest.raises(ValueError, match="quote_offset_ticks"):
        Institution("i", signal_halflife=10, signal_sigma=1, threshold=0.5,
                    position_limit=100, quote_offset_ticks=0, scale=10,
                    signal_price_scale=0, initial_price=100, rng=rng)
    with pytest.raises(ValueError, match="scale"):
        Institution("i", signal_halflife=10, signal_sigma=1, threshold=0.5,
                    position_limit=100, quote_offset_ticks=1, scale=0,
                    signal_price_scale=0, initial_price=100, rng=rng)
    with pytest.raises(ValueError, match="signal_price_scale"):
        Institution("i", signal_halflife=10, signal_sigma=1, threshold=0.5,
                    position_limit=100, quote_offset_ticks=1, scale=10,
                    signal_price_scale=-1, initial_price=100, rng=rng)
    with pytest.raises(ValueError, match="initial_price"):
        Institution("i", signal_halflife=10, signal_sigma=1, threshold=0.5,
                    position_limit=100, quote_offset_ticks=1, scale=10,
                    signal_price_scale=0, initial_price=0, rng=rng)


def test_institution_position_increments_on_buy_fill() -> None:
    inst = _institution()
    inst.signal = 1.0
    actions = inst.step(_state())
    order = [a for a in actions if isinstance(a, Order)][0]
    fill = Fill(
        taker_order_id=uuid.uuid4(),
        maker_order_id=order.order_id,
        taker_agent_id="other",
        maker_agent_id="inst0",
        aggressor_side=Side.SELL,
        price=order.price,
        qty=order.qty,
        timestamp=1.0,
    )
    inst.on_fills([fill])
    assert inst.position > 0
    assert inst.resting_order_id is None


def test_institution_position_decrements_on_sell_fill() -> None:
    inst = _institution()
    inst.signal = -1.0
    actions = inst.step(_state())
    order = [a for a in actions if isinstance(a, Order)][0]
    fill = Fill(
        taker_order_id=uuid.uuid4(),
        maker_order_id=order.order_id,
        taker_agent_id="other",
        maker_agent_id="inst0",
        aggressor_side=Side.BUY,
        price=order.price,
        qty=order.qty,
        timestamp=1.0,
    )
    inst.on_fills([fill])
    assert inst.position < 0

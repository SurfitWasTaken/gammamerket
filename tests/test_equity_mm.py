"""Tests for the equity market maker agent (Phase 3)."""

from __future__ import annotations

import numpy as np
import pytest

from sim.agents.equity_mm import EquityMarketMaker, EquityMMConfig
from sim.agents.base import MarketState
from sim.core.events import Fill, Side, Order
import uuid


def make_config(**overrides):
    defaults = dict(
        arrival_rate=20.0,
        spread_target=4,
        inventory_limit=2000,
        risk_aversion=0.1,
        quote_size=5,
        max_orders_per_side=1,
    )
    defaults.update(overrides)
    return EquityMMConfig(**defaults)


def make_state(
    best_bid=9998,
    best_ask=10002,
    last_fill_price=10000,
    own_position=0,
    timestamp=10.0,
):
    mid = (best_bid + best_ask) / 2.0 if best_bid is not None and best_ask is not None else None
    return MarketState(
        best_bid=best_bid,
        best_ask=best_ask,
        mid=mid,
        last_fill_price=last_fill_price,
        own_position=own_position,
        timestamp=timestamp,
    )


class TestEquityMarketMaker:
    def test_basic_initialization(self):
        rng = np.random.default_rng(42)
        cfg = make_config()
        mm = EquityMarketMaker("mm1", cfg, rng)
        assert mm.agent_id == "mm1"
        assert mm.position == 0
        assert mm._resting_bid_id is None
        assert mm._resting_ask_id is None

    def test_schedule_next_returns_finite_time(self):
        rng = np.random.default_rng(42)
        cfg = make_config(arrival_rate=20.0)
        mm = EquityMarketMaker("mm1", cfg, rng)
        next_t = mm.schedule_next(0.0)
        assert 0 < next_t < float("inf")

    def test_schedule_next_zero_rate_returns_inf(self):
        rng = np.random.default_rng(42)
        cfg = make_config(arrival_rate=0.0)
        mm = EquityMarketMaker("mm1", cfg, rng)
        next_t = mm.schedule_next(0.0)
        assert next_t == float("inf")

    def test_step_places_two_sided_quotes_when_within_inventory(self):
        rng = np.random.default_rng(42)
        cfg = make_config()
        mm = EquityMarketMaker("mm1", cfg, rng)
        state = make_state()

        actions = mm.step(state)

        assert len(actions) == 2
        assert all(isinstance(a, Order) for a in actions)
        sides = {a.side for a in actions}
        assert sides == {Side.BUY, Side.SELL}
        assert actions[0].agent_id == "mm1"
        assert actions[1].agent_id == "mm1"
        assert actions[0].qty == cfg.quote_size
        assert actions[1].qty == cfg.quote_size
        assert actions[0].price < actions[1].price

    def test_step_cancels_existing_before_placing_new(self):
        rng = np.random.default_rng(42)
        cfg = make_config()
        mm = EquityMarketMaker("mm1", cfg, rng)
        state = make_state()

        actions1 = mm.step(state)
        bid_id_1 = actions1[0].order_id
        ask_id_1 = actions1[1].order_id

        state2 = make_state(timestamp=11.0)
        actions2 = mm.step(state2)

        assert len(actions2) == 4
        cancels = [a for a in actions2 if hasattr(a, "order_id") and not hasattr(a, "qty")]
        assert len(cancels) == 2
        cancel_ids = {c.order_id for c in cancels}
        assert cancel_ids == {bid_id_1, ask_id_1}

    def test_spread_target_respected(self):
        rng = np.random.default_rng(42)
        cfg = make_config(spread_target=10)
        mm = EquityMarketMaker("mm1", cfg, rng)
        state = make_state(best_bid=9995, best_ask=10005)

        actions = mm.step(state)

        bid = next(a for a in actions if a.side is Side.BUY)
        ask = next(a for a in actions if a.side is Side.SELL)
        assert ask.price - bid.price == cfg.spread_target

    def test_inventory_skew_moves_quotes(self):
        rng = np.random.default_rng(42)
        cfg = make_config(risk_aversion=0.5, spread_target=4)
        mm = EquityMarketMaker("mm1", cfg, rng)
        mm.position = 100

        state_long = make_state(own_position=100)
        actions_long = mm.step(state_long)

        mm2 = EquityMarketMaker("mm2", cfg, rng)
        mm2.position = -100
        state_short = make_state(own_position=-100)
        actions_short = mm2.step(state_short)

        bid_long = next(a for a in actions_long if a.side is Side.BUY)
        bid_short = next(a for a in actions_short if a.side is Side.BUY)
        assert bid_short.price > bid_long.price

    def test_stops_quoting_at_inventory_limit(self):
        rng = np.random.default_rng(42)
        cfg = make_config(inventory_limit=10, quote_size=5)
        mm = EquityMarketMaker("mm1", cfg, rng)
        mm.position = 10

        state = make_state()
        actions = mm.step(state)

        assert len(actions) == 0

    def test_cancels_existing_when_hitting_inventory_limit(self):
        rng = np.random.default_rng(42)
        cfg = make_config(inventory_limit=10, quote_size=5)
        mm = EquityMarketMaker("mm1", cfg, rng)
        state = make_state()
        actions1 = mm.step(state)

        mm.position = 10
        state2 = make_state(timestamp=11.0)
        actions2 = mm.step(state2)

        from sim.core.events import Cancel
        cancels = [a for a in actions2 if isinstance(a, Cancel)]
        assert len(cancels) == 2

    def test_on_fills_clears_resting_ids(self):
        rng = np.random.default_rng(42)
        cfg = make_config()
        mm = EquityMarketMaker("mm1", cfg, rng)
        state = make_state()
        actions = mm.step(state)

        bid_order = next(a for a in actions if a.side is Side.BUY)
        ask_order = next(a for a in actions if a.side is Side.SELL)

        fill_bid = Fill(
            taker_order_id=uuid.uuid4(),
            maker_order_id=bid_order.order_id,
            taker_agent_id="taker",
            maker_agent_id="mm1",
            aggressor_side=Side.SELL,
            price=bid_order.price,
            qty=5,
            timestamp=state.timestamp,
        )

        mm.on_fills([fill_bid])
        assert mm._resting_bid_id is None
        assert mm._resting_ask_id == ask_order.order_id

        fill_ask = Fill(
            taker_order_id=uuid.uuid4(),
            maker_order_id=ask_order.order_id,
            taker_agent_id="taker",
            maker_agent_id="mm1",
            aggressor_side=Side.BUY,
            price=ask_order.price,
            qty=5,
            timestamp=state.timestamp,
        )

        mm.on_fills([fill_ask])
        assert mm._resting_bid_id is None
        assert mm._resting_ask_id is None

    def test_fallback_to_last_fill_when_one_sided_book(self):
        rng = np.random.default_rng(42)
        cfg = make_config(spread_target=4)
        mm = EquityMarketMaker("mm1", cfg, rng)

        state = make_state(best_bid=None, best_ask=10002, last_fill_price=10000)
        actions = mm.step(state)

        bid = next(a for a in actions if a.side is Side.BUY)
        ask = next(a for a in actions if a.side is Side.SELL)
        assert bid.price < ask.price
        assert ask.price - bid.price == cfg.spread_target

    def test_bid_ask_never_cross(self):
        rng = np.random.default_rng(42)
        cfg = make_config(spread_target=1, risk_aversion=10.0)
        mm = EquityMarketMaker("mm1", cfg, rng)
        state = make_state(own_position=5000)

        actions = mm.step(state)

        bid = next(a for a in actions if a.side is Side.BUY)
        ask = next(a for a in actions if a.side is Side.SELL)
        assert bid.price < ask.price

    def test_quote_size_respected(self):
        rng = np.random.default_rng(42)
        cfg = make_config(quote_size=10)
        mm = EquityMarketMaker("mm1", cfg, rng)
        state = make_state()

        actions = mm.step(state)

        for a in actions:
            assert a.qty == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
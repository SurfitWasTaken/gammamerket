"""Tests for the options-demand flow agent (Phase 5, E1).

Covers: deterministic trade sequences under a seeded rng, trades only
against chain series, max_lots respected, no-reference-price gating,
dealer ownership of returned hedge orders, and the Clock owner-routing
extension that credits those hedges to the dealer.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from sim.agents.base import MarketState
from sim.agents.options_flow import OptionsFlow, OptionsFlowConfig
from sim.agents.options_mm import OptionsMarketMaker, OptionsMMConfig
from sim.core.clock import Clock
from sim.core.events import Order, Side
from sim.core.lob import LimitOrderBook
from sim.core.tape import Tape
from sim.options.chain import build_chain
from sim.options.surface import FlatVolSurface

SPOT = 10_000.0
MINUTES_PER_YEAR = 525_600.0


def make_dealer(seed=7, gamma_limit=500.0):
    chain = build_chain(
        SPOT, 0.0,
        strikes_pct=[-0.05, 0.0, 0.05],
        expiries_days=[7, 30],
        tick_size=1,
    )
    config = OptionsMMConfig(
        arrival_rate=20.0,
        vol_estimate=0.20,
        spread_vols=2.0,
        delta_hedge_threshold=0.05,
        gamma_limit=gamma_limit,
        option_tick=1,
    )
    return OptionsMarketMaker(
        "dealer", config, np.random.default_rng(seed),
        chain=chain,
        surface=FlatVolSurface(0.20),
        risk_free_rate=0.05,
        minutes_per_year=MINUTES_PER_YEAR,
        tick_size=1,
    )


def make_flow(dealer, seed=11, max_lots=3, arrival_rate=5.0):
    config = OptionsFlowConfig(arrival_rate=arrival_rate, max_lots=max_lots)
    return OptionsFlow("flow", config, np.random.default_rng(seed), dealer)


def make_state(mid=SPOT, last_fill_price=None, timestamp=1.0):
    bid = int(mid - 1) if mid is not None else None
    ask = int(mid + 1) if mid is not None else None
    return MarketState(
        best_bid=bid,
        best_ask=ask,
        mid=mid,
        last_fill_price=last_fill_price,
        own_position=0,
        timestamp=timestamp,
    )


class TestOptionsFlow:
    def test_deterministic_under_seeded_rng(self):
        log_a = self._run_trades(seed=11)
        log_b = self._run_trades(seed=11)
        assert log_a == log_b
        assert log_a != self._run_trades(seed=12)

    @staticmethod
    def _run_trades(seed):
        dealer = make_dealer()
        flow = make_flow(dealer, seed=seed)
        for i in range(20):
            flow.step(make_state(timestamp=float(i)))
        return [(t.series, t.side, t.qty) for t in dealer.trade_log]

    def test_trades_only_against_existing_series(self):
        dealer = make_dealer()
        flow = make_flow(dealer)
        for i in range(50):
            flow.step(make_state(timestamp=float(i)))
        chain = set(dealer.chain)
        assert dealer.trade_log
        assert all(t.series in chain for t in dealer.trade_log)

    def test_respects_max_lots(self):
        dealer = make_dealer()
        flow = make_flow(dealer, max_lots=2)
        for i in range(50):
            flow.step(make_state(timestamp=float(i)))
        assert all(1 <= t.qty <= 2 for t in dealer.trade_log)

    def test_no_reference_price_no_trade(self):
        dealer = make_dealer()
        flow = make_flow(dealer)
        state = make_state(mid=None, last_fill_price=None)
        assert flow.step(state) == []
        assert dealer.trade_log == []

    def test_falls_back_to_last_fill_price(self):
        dealer = make_dealer()
        flow = make_flow(dealer)
        flow.step(make_state(mid=None, last_fill_price=10_000))
        assert len(dealer.trade_log) == 1

    def test_returned_orders_are_dealer_owned(self):
        dealer = make_dealer()
        flow = make_flow(dealer)
        orders = []
        for i in range(20):
            orders.extend(flow.step(make_state(timestamp=float(i))))
        assert orders, "20 trades should produce at least one hedge"
        assert all(o.agent_id == "dealer" for o in orders)
        assert all(o.is_market for o in orders)
        assert flow.position == 0

    def test_rejects_max_lots_below_one(self):
        dealer = make_dealer()
        with pytest.raises(ValueError):
            make_flow(dealer, max_lots=0)


class TestClockOwnerRouting:
    """The E1 contract: hedge orders carried by the flow agent are
    credited — open_order_ids and fills — to the dealer, their owner."""

    def _run_clock(self, steps=60):
        tape = Tape()
        book = LimitOrderBook(tick_size=1, on_fill=tape.append)
        # Deep static liquidity so hedges always fill.
        book.submit_limit(Order(uuid.uuid4(), "liq", Side.BUY, 9_999, 10_000, 0.0))
        book.submit_limit(Order(uuid.uuid4(), "liq", Side.SELL, 10_001, 10_000, 0.0))
        dealer = make_dealer()
        flow = make_flow(dealer, arrival_rate=10.0)
        clock = Clock(book, tape, np.random.default_rng(3))
        clock.register(dealer, dealer.config.arrival_rate)
        clock.register(flow, flow.config.arrival_rate)
        clock.run(steps)
        return dealer, flow, tape

    def test_dealer_position_updates_from_flow_carried_hedges(self):
        dealer, flow, tape = self._run_clock()
        assert dealer.trade_log, "flow must have traded options"
        assert dealer.hedge_log, "hedges must have been emitted"
        assert tape.fills, "hedges must have hit the equity book"
        # Every equity fill's taker is the dealer (the hedge orders),
        # even though the flow agent submitted them via its step.
        assert all(f.taker_agent_id == "dealer" for f in tape.fills)
        assert flow.position == 0
        filled = sum(r.filled_qty_lots for r in dealer.hedge_log)
        assert dealer.position == filled
        assert dealer.position != 0

    def test_post_hedge_delta_within_quantisation_bound(self):
        dealer, _, _ = self._run_clock()
        # Fully-filled hedge cycles must land within the E2 bound.
        bound = max(dealer.config.delta_hedge_threshold, 0.5)
        full = [r for r in dealer.hedge_log if r.filled_qty_lots == r.intended_qty_lots]
        assert full, "deep book: hedges should fill completely"
        for record in full:
            assert abs(record.pre_delta_lots + record.filled_qty_lots) <= bound

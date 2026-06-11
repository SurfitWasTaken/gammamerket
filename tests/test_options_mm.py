"""Tests for the options dealer agent (Phase 5).

Pins the E1–E6 contracts from CLAUDE.md: contract→lot delta arithmetic
(E2 single site), hedge gating + quantisation (E3/E2), quote pricing and
rounding (E4), the gamma cap (E5), and the Phase 5 post-hedge contract
`abs(net_delta_lots) <= max(delta_hedge_threshold, 0.5)`.
"""

from __future__ import annotations

import uuid

import numpy as np
import pytest

from sim.agents.base import MarketState
from sim.agents.options_mm import (
    HedgeRecord,
    OptionsMarketMaker,
    OptionsMMConfig,
    OptionTrade,
)
from sim.core.events import Order, Side
from sim.core.lob import LimitOrderBook
from sim.options.chain import OptionSeries, build_chain, time_to_expiry_years
from sim.options.pricer import bs_greeks, bs_price
from sim.options.surface import FlatVolSurface

SPOT = 10_000.0
MINUTES_PER_YEAR = 525_600.0
RISK_FREE = 0.05
SIGMA = 0.20
WEEK_MINUTES = 7 * 24 * 60.0

ATM_CALL = OptionSeries(strike=10_000, expiry_minutes=WEEK_MINUTES, is_call=True)
ATM_PUT = OptionSeries(strike=10_000, expiry_minutes=WEEK_MINUTES, is_call=False)
OTM_CALL = OptionSeries(strike=10_500, expiry_minutes=WEEK_MINUTES, is_call=True)


def make_config(**overrides):
    defaults = dict(
        arrival_rate=20.0,
        vol_estimate=SIGMA,
        spread_vols=2.0,
        delta_hedge_threshold=0.05,
        gamma_limit=500.0,
        option_tick=1,
    )
    defaults.update(overrides)
    return OptionsMMConfig(**defaults)


def make_dealer(config=None, chain=None):
    return OptionsMarketMaker(
        "dealer",
        config or make_config(),
        np.random.default_rng(7),
        chain=chain if chain is not None else [ATM_CALL, ATM_PUT, OTM_CALL],
        surface=FlatVolSurface(SIGMA),
        risk_free_rate=RISK_FREE,
        minutes_per_year=MINUTES_PER_YEAR,
        tick_size=1,
    )


def series_greeks(series, spot=SPOT, now=0.0):
    T = time_to_expiry_years(series, now, MINUTES_PER_YEAR)
    return bs_greeks(spot, series.strike, T, RISK_FREE, SIGMA, is_call=series.is_call)


def make_state(mid=SPOT, last_fill_price=None, timestamp=0.0):
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


def make_deep_book():
    """An equity book with plenty of resting liquidity on both sides."""
    book = LimitOrderBook(tick_size=1)
    book.submit_limit(Order(uuid.uuid4(), "liq", Side.BUY, 9_999, 500, 0.0))
    book.submit_limit(Order(uuid.uuid4(), "liq", Side.SELL, 10_001, 500, 0.0))
    return book


def apply_hedges(dealer, book, orders):
    """Submit hedge orders to the book and route fills back (clock stand-in)."""
    for order in orders:
        fills = book.submit_market(order)
        if fills:
            dealer.on_fills(fills)


class TestDeltaArithmetic:
    def test_net_delta_matches_hand_computation(self):
        dealer = make_dealer()
        dealer.on_option_trade(ATM_CALL, Side.BUY, 10, SPOT, 0.0)
        # Taker bought 10 calls -> dealer short 10 contracts; no equity yet.
        assert dealer.option_positions == {ATM_CALL: -10}
        expected = -10 * series_greeks(ATM_CALL).delta
        assert dealer.net_delta_lots(SPOT, 0.0) == pytest.approx(expected)

    def test_equity_position_carries_unit_delta(self):
        dealer = make_dealer()
        dealer.position = 7
        assert dealer.net_delta_lots(SPOT, 0.0) == pytest.approx(7.0)

    def test_portfolio_gamma_matches_hand_computation(self):
        dealer = make_dealer()
        dealer.on_option_trade(ATM_CALL, Side.SELL, 4, SPOT, 0.0)
        expected = 4 * series_greeks(ATM_CALL).gamma
        assert dealer.portfolio_gamma(SPOT, 0.0) == pytest.approx(expected)

    def test_offsetting_trade_clears_position_book(self):
        dealer = make_dealer()
        dealer.on_option_trade(ATM_CALL, Side.BUY, 5, SPOT, 0.0)
        dealer.on_option_trade(ATM_CALL, Side.SELL, 5, SPOT, 0.0)
        assert dealer.option_positions == {}


class TestHedging:
    def test_phase5_contract_post_hedge_delta_within_bound(self):
        dealer = make_dealer()
        book = make_deep_book()
        orders = dealer.on_option_trade(ATM_CALL, Side.BUY, 10, SPOT, 0.0)
        assert orders, "a 10-contract ATM trade must trigger a hedge"
        apply_hedges(dealer, book, orders)
        bound = max(dealer.config.delta_hedge_threshold, 0.5)
        assert abs(dealer.net_delta_lots(SPOT, 0.0)) <= bound

    def test_long_call_position_emits_sell_hedge(self):
        dealer = make_dealer()
        # Taker SELL -> dealer long calls -> positive delta -> sell equity.
        orders = dealer.on_option_trade(ATM_CALL, Side.SELL, 10, SPOT, 0.0)
        assert len(orders) == 1
        assert orders[0].side is Side.SELL
        assert orders[0].is_market
        assert orders[0].qty == round(10 * series_greeks(ATM_CALL).delta)

    def test_long_put_position_emits_buy_hedge(self):
        dealer = make_dealer()
        orders = dealer.on_option_trade(ATM_PUT, Side.SELL, 10, SPOT, 0.0)
        assert len(orders) == 1
        assert orders[0].side is Side.BUY

    def test_threshold_gates_hedge(self):
        dealer = make_dealer(make_config(delta_hedge_threshold=100.0))
        orders = dealer.on_option_trade(ATM_CALL, Side.BUY, 10, SPOT, 0.0)
        assert orders == []
        assert dealer.hedge_log == []

    def test_sub_half_lot_delta_rounds_to_no_order(self):
        dealer = make_dealer()
        # Two OTM calls: |delta| well under 0.5 but over the 0.05 threshold.
        delta = 2 * series_greeks(OTM_CALL).delta
        assert 0.05 < abs(delta) < 0.5
        orders = dealer.on_option_trade(OTM_CALL, Side.BUY, 2, SPOT, 0.0)
        assert orders == []

    def test_step_rehedges_on_drift(self):
        dealer = make_dealer()
        dealer.on_option_trade(ATM_CALL, Side.SELL, 10, SPOT, 0.0)
        # Hedge never applied; the next step must still try to flatten.
        actions = dealer.step(make_state(mid=SPOT, timestamp=5.0))
        assert len(actions) == 1
        assert actions[0].side is Side.SELL
        assert actions[0].is_market

    def test_step_without_reference_price_emits_nothing(self):
        dealer = make_dealer()
        dealer.on_option_trade(ATM_CALL, Side.SELL, 10, SPOT, 0.0)
        state = make_state(mid=None, last_fill_price=None)
        assert dealer.step(state) == []

    def test_step_falls_back_to_last_fill_price(self):
        dealer = make_dealer()
        dealer.on_option_trade(ATM_CALL, Side.SELL, 10, SPOT, 0.0)
        state = make_state(mid=None, last_fill_price=10_000)
        assert len(dealer.step(state)) == 1

    def test_hedge_log_records_fills(self):
        dealer = make_dealer()
        book = make_deep_book()
        orders = dealer.on_option_trade(ATM_CALL, Side.BUY, 10, SPOT, 0.0)
        apply_hedges(dealer, book, orders)
        assert len(dealer.hedge_log) == 1
        record = dealer.hedge_log[0]
        assert record.intended_qty_lots == round(-dealer.hedge_log[0].pre_delta_lots)
        assert record.filled_qty_lots == record.intended_qty_lots
        assert dealer.position == record.filled_qty_lots

    def test_expired_series_prices_intrinsic_without_nan(self):
        expired = OptionSeries(strike=9_500, expiry_minutes=0.0, is_call=True)
        dealer = make_dealer(chain=[expired])
        now = 10.0  # past expiry -> T == 0
        orders = dealer.on_option_trade(expired, Side.SELL, 2, SPOT, now)
        # ITM expired call has step delta 1.0 -> dealer long 2 -> sell 2.
        assert dealer.net_delta_lots(SPOT, now) == pytest.approx(2.0)
        assert len(orders) == 1
        assert orders[0].side is Side.SELL
        assert orders[0].qty == 2


class TestQuoting:
    def test_quote_straddles_theoretical_value(self):
        dealer = make_dealer()
        T = time_to_expiry_years(ATM_CALL, 0.0, MINUTES_PER_YEAR)
        theo = bs_price(SPOT, ATM_CALL.strike, T, RISK_FREE, SIGMA, is_call=True)
        bid, ask = dealer.quote(ATM_CALL, SPOT, 0.0)
        assert bid <= theo <= ask
        assert bid < ask

    def test_quote_snaps_to_option_tick_grid(self):
        dealer = make_dealer(make_config(option_tick=5))
        bid, ask = dealer.quote(ATM_CALL, SPOT, 0.0)
        assert bid % 5 == 0
        assert ask % 5 == 0
        assert ask >= bid + 5

    def test_quote_bid_floored_at_zero(self):
        # Deep OTM, near expiry: theoretical value far below one tick.
        tiny = OptionSeries(strike=15_000, expiry_minutes=10.0, is_call=True)
        dealer = make_dealer(chain=[tiny])
        bid, ask = dealer.quote(tiny, SPOT, 0.0)
        assert bid == 0
        assert ask >= 1

    def test_trade_executes_at_quote_and_tracks_cash_flow(self):
        dealer = make_dealer()
        bid, ask = dealer.quote(ATM_CALL, SPOT, 0.0)
        dealer.on_option_trade(ATM_CALL, Side.BUY, 3, SPOT, 0.0)
        assert dealer.trade_log[-1].price == ask
        assert dealer.option_cash_flow == pytest.approx(ask * 3)
        dealer.on_option_trade(ATM_CALL, Side.SELL, 2, SPOT, 0.0)
        assert dealer.trade_log[-1].price == bid
        assert dealer.option_cash_flow == pytest.approx(ask * 3 - bid * 2)


class TestGammaLimit:
    def test_trade_past_gamma_limit_is_refused(self):
        gamma = series_greeks(ATM_CALL).gamma
        dealer = make_dealer(make_config(gamma_limit=gamma * 5))
        orders = dealer.on_option_trade(ATM_CALL, Side.SELL, 6, SPOT, 0.0)
        assert orders == []
        assert dealer.option_positions == {}
        assert dealer.trade_log == []
        assert dealer.gamma_rejections == 1

    def test_gamma_reducing_trade_always_accepted(self):
        gamma = series_greeks(ATM_CALL).gamma
        dealer = make_dealer(make_config(gamma_limit=gamma * 5))
        dealer.on_option_trade(ATM_CALL, Side.SELL, 4, SPOT, 0.0)  # +4 contracts
        # +4 more would breach the cap...
        assert dealer.on_option_trade(ATM_CALL, Side.SELL, 4, SPOT, 0.0) == []
        assert dealer.gamma_rejections == 1
        # ...but unwinding toward zero gamma is always allowed.
        dealer.on_option_trade(ATM_CALL, Side.BUY, 4, SPOT, 0.0)
        assert dealer.option_positions == {}
        assert dealer.gamma_rejections == 1


class TestValidation:
    def test_rejects_non_positive_qty(self):
        dealer = make_dealer()
        with pytest.raises(ValueError):
            dealer.on_option_trade(ATM_CALL, Side.BUY, 0, SPOT, 0.0)

    def test_rejects_empty_chain(self):
        with pytest.raises(ValueError):
            make_dealer(chain=[])

    def test_chain_builder_integration(self):
        chain = build_chain(
            SPOT, 0.0,
            strikes_pct=[-0.05, 0.0, 0.05],
            expiries_days=[7],
            tick_size=1,
        )
        dealer = make_dealer(chain=chain)
        assert len(dealer.chain) == 6

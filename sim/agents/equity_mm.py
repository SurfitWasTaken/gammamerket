"""Equity market maker agent (Phase 3).

Provides continuous two-sided liquidity with a target spread and
inventory-aware quote skew. Places limit orders on both sides of the book
centered around the mid price (or last fill price when one-sided).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

import numpy as np

from sim.agents.base import Agent, MarketState
from sim.core.events import Cancel, Order, Side


@dataclass(frozen=True)
class EquityMMConfig:
    """Configuration for the equity market maker."""

    arrival_rate: float
    spread_target: int
    inventory_limit: int
    risk_aversion: float
    quote_size: int
    max_orders_per_side: int


class EquityMarketMaker(Agent):
    """A simple symmetric market maker with inventory skew.

    On each step, cancels existing quotes and places fresh limit orders
    on both sides with:
      - mid_price = (best_bid + best_ask) / 2  (or last_fill_price if one-sided)
      - half_spread = spread_target / 2
      - skew = risk_aversion * position
      - bid_price = round(mid_price - half_spread - skew)
      - ask_price = round(mid_price + half_spread - skew)

    Only places orders if position is within inventory_limit.
    """

    def __init__(
        self,
        agent_id: str,
        config: EquityMMConfig,
        rng: np.random.Generator,
    ) -> None:
        super().__init__(agent_id)
        self.config = config
        self.rng = rng
        self._next_event_time: float = 0.0
        self._resting_bid_id: Optional[uuid.UUID] = None
        self._resting_ask_id: Optional[uuid.UUID] = None

    def schedule_next(self, current_time: float) -> float:
        """Schedule the next step time using Poisson inter-arrival."""
        if self.config.arrival_rate <= 0:
            return float("inf")
        dt = self.rng.exponential(1.0 / self.config.arrival_rate)
        self._next_event_time = current_time + dt
        return self._next_event_time

    def next_event_time(self) -> float:
        return self._next_event_time

    def step(self, state: MarketState) -> list[Order | Cancel]:
        actions: list[Order | Cancel] = []

        if abs(self.position) >= self.config.inventory_limit:
            if self._resting_bid_id:
                actions.append(Cancel(self._resting_bid_id, self.agent_id, state.timestamp))
                self._resting_bid_id = None
            if self._resting_ask_id:
                actions.append(Cancel(self._resting_ask_id, self.agent_id, state.timestamp))
                self._resting_ask_id = None
            return actions

        mid = state.mid
        if mid is None:
            mid = float(state.last_fill_price) if state.last_fill_price is not None else 0.0

        half_spread = self.config.spread_target / 2.0
        skew = self.config.risk_aversion * self.position

        bid_price = int(round(mid - half_spread - skew))
        ask_price = int(round(mid + half_spread - skew))

        if bid_price >= ask_price:
            bid_price = ask_price - 1

        if self._resting_bid_id:
            actions.append(Cancel(self._resting_bid_id, self.agent_id, state.timestamp))
        if self._resting_ask_id:
            actions.append(Cancel(self._resting_ask_id, self.agent_id, state.timestamp))

        bid_order = Order(
            order_id=uuid.uuid4(),
            agent_id=self.agent_id,
            side=Side.BUY,
            price=bid_price,
            qty=self.config.quote_size,
            timestamp=state.timestamp,
        )
        ask_order = Order(
            order_id=uuid.uuid4(),
            agent_id=self.agent_id,
            side=Side.SELL,
            price=ask_price,
            qty=self.config.quote_size,
            timestamp=state.timestamp,
        )

        self._resting_bid_id = bid_order.order_id
        self._resting_ask_id = ask_order.order_id

        actions.append(bid_order)
        actions.append(ask_order)

        self.open_order_ids.add(bid_order.order_id)
        self.open_order_ids.add(ask_order.order_id)

        return actions

    def on_fills(self, fills: list) -> None:
        super().on_fills(fills)
        for fill in fills:
            if fill.maker_agent_id == self.agent_id:
                if fill.maker_order_id == self._resting_bid_id:
                    self._resting_bid_id = None
                elif fill.maker_order_id == self._resting_ask_id:
                    self._resting_ask_id = None
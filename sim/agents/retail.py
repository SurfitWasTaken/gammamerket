"""Retail noise-trader agent.

Poisson-arriving at `arrival_rate` orders per minute (the rate is
registered with the clock; the agent itself does not schedule). Each
arrival submits a single market order with:
  * random side (50/50 by default; configurable `direction_bias`)
  * random size from a geometric distribution with
    `p = 1 / order_size_mean`, so `E[qty] = order_size_mean`.

Retail agents do not manage inventory, do not place resting orders, and
do not interact with the book state directly — they only consume
liquidity.
"""

from __future__ import annotations

import uuid
from typing import Optional

import numpy as np

from sim.agents.base import Agent, MarketState
from sim.core.events import Order, Side


class Retail(Agent):
    """Poisson-arriving market-order noise trader.

    Args:
        agent_id: Stable identifier used in events, fills, and the LOB.
        order_size_mean: Mean order size in lots. Must be > 0. The
            geometric distribution's support is {1, 2, ...} so the mean
            cannot be < 1.
        direction_bias: Shift to the buy probability in [-0.5, 0.5].
            `p_buy = 0.5 + direction_bias`. Defaults to 0.0 (50/50).
        rng: NumPy `Generator` for drawing direction and size.
    """

    def __init__(
        self,
        agent_id: str,
        order_size_mean: float,
        direction_bias: float,
        rng: np.random.Generator,
    ) -> None:
        super().__init__(agent_id)
        if order_size_mean <= 0:
            raise ValueError(f"order_size_mean must be positive, got {order_size_mean}")
        if not -0.5 <= direction_bias <= 0.5:
            raise ValueError(f"direction_bias must be in [-0.5, 0.5], got {direction_bias}")
        self.order_size_mean: float = order_size_mean
        self.direction_bias: float = direction_bias
        self.rng: np.random.Generator = rng
        self._p: float = 1.0 / order_size_mean
        self._p_buy: float = 0.5 + direction_bias

    def step(self, state: MarketState) -> list[Order]:
        buy = self.rng.random() < self._p_buy
        side = Side.BUY if buy else Side.SELL
        qty = int(self.rng.geometric(self._p))
        return [
            Order(
                order_id=uuid.uuid4(),
                agent_id=self.agent_id,
                side=side,
                price=0,
                qty=qty,
                timestamp=state.timestamp,
            )
        ]

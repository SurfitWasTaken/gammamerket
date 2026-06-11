"""Options-demand flow agent (Phase 5, E1 trigger surface).

A Poisson-arriving taker process for the quote-driven options market:
on each clock event it picks a random series from the dealer's chain, a
random side, and a random contract count, and trades directly against
the dealer via `dealer.on_option_trade(...)` — there is no options LOB.
The dealer's returned equity hedge orders are passed through this
agent's `step()` to the Clock, which routes their fills back to the
dealer by owner (`Order.agent_id`, the E1 owner-routing contract).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from sim.agents.base import Agent, MarketState
from sim.agents.options_mm import OptionsMarketMaker
from sim.core.events import Order, Side
from sim.options.chain import spot_from_book


@dataclass(frozen=True)
class OptionsFlowConfig:
    """Configuration for the options-demand flow.

    Args:
        arrival_rate: Poisson trade arrivals per minute (clock rate).
        max_lots: Maximum contracts per trade; qty is uniform on
            `[1, max_lots]`. Must be >= 1.
    """

    arrival_rate: float
    max_lots: int


class OptionsFlow(Agent):
    """Poisson taker that lifts/hits the dealer's option quotes.

    The flow never holds positions or resting orders of its own — every
    order it returns is a dealer-owned hedge (its `position` stays 0).

    Args:
        agent_id: Stable identifier (events/diagnostics only).
        config: Frozen `OptionsFlowConfig`.
        rng: NumPy `Generator` for series/side/qty draws; seeding it
            makes the trade sequence deterministic.
        dealer: The options dealer whose chain is traded and whose
            `on_option_trade` is invoked.
    """

    def __init__(
        self,
        agent_id: str,
        config: OptionsFlowConfig,
        rng: np.random.Generator,
        dealer: OptionsMarketMaker,
    ) -> None:
        super().__init__(agent_id)
        if config.max_lots < 1:
            raise ValueError(f"max_lots must be >= 1, got {config.max_lots}")
        self.config = config
        self.rng = rng
        self.dealer = dealer

    def step(self, state: MarketState) -> list[Order]:
        """Trade one random series against the dealer; return its hedges.

        With no reference price (mid and last fill both None) there is
        no spot to price against, so no trade happens (P1-5 mirror).
        """
        mid: Optional[float] = state.mid
        if mid is None:
            if state.last_fill_price is None:
                return []
            mid = float(state.last_fill_price)
        spot = spot_from_book(mid, self.dealer.tick_size)

        chain = self.dealer.chain
        series = chain[int(self.rng.integers(len(chain)))]
        side = Side.BUY if self.rng.random() < 0.5 else Side.SELL
        qty = int(self.rng.integers(1, self.config.max_lots + 1))
        return self.dealer.on_option_trade(series, side, qty, spot, state.timestamp)

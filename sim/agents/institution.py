"""Institutional speculator agent.

Maintains a mean-reverting signal (Ornstein–Uhlenbeck process anchored
at zero) and a target position proportional to that signal. When the
target differs from the current position, the agent posts a single
limit order — anchored to its OU signal around the *initial* price —
to trade toward the target. The order is only cancelled once it is
fully filled; partial fills just decrement the tracked remaining
quantity so the resting surplus is preserved.

Signal dynamics use the exact OU discretisation so behaviour is stable
even at low Poisson rates:

    s(t+dt) = s(t) * exp(-lambda * dt) + sigma * sqrt((1 - exp(-2*lambda*dt)) / (2*lambda)) * N(0,1)

where `lambda = ln(2) / halflife`.

Posting price:

    base  = initial_price + int(signal * signal_price_scale)
    BUY   = base + quote_offset_ticks
    SELL  = base - quote_offset_ticks

Anchoring to `initial_price` (not the current mid) breaks the
self-referencing loop where the institution would otherwise always
quote relative to its own resting order and pin the price at the
seed BBO. The signal-dependent offset is what lets the mid drift
away from the initial price over time.
"""

from __future__ import annotations

import uuid
from typing import Optional, Union

import numpy as np

from sim.agents.base import Agent, MarketState
from sim.core.events import Cancel, Fill, Order, Side


class Institution(Agent):
    """Mean-reverting limit-order speculator.

    Args:
        agent_id: Stable identifier.
        signal_halflife: Half-life of the signal's mean reversion, in
            minutes. Must be positive.
        signal_sigma: Diffusion coefficient of the signal (unitless
            scale). Must be non-negative.
        threshold: Action threshold on `|signal|`. If the signal
            magnitude is at or below the threshold, the agent does not
            act this step. Must be non-negative.
        position_limit: Maximum absolute position in lots. Must be
            positive. The agent's resting-order quantity is capped to
            stay within this bound.
        quote_offset_ticks: Distance (in ticks) from the signal-anchored
            base price at which resting limits are posted.
        scale: Multiplier converting the (unitless) signal to a target
            position in lots: `target = int(signal * scale)`. Must be
            positive.
        signal_price_scale: Multiplier converting the (unitless) signal
            to a price offset in ticks. `price_offset = int(signal *
            signal_price_scale)`. Must be non-negative.
        initial_price: Anchor price (in ticks) used as the mid reference
            before the first observation. Must be positive.
        rng: NumPy `Generator` for drawing the OU innovation.
    """

    def __init__(
        self,
        agent_id: str,
        signal_halflife: float,
        signal_sigma: float,
        threshold: float,
        position_limit: int,
        quote_offset_ticks: int,
        scale: float,
        signal_price_scale: float,
        initial_price: int,
        rng: np.random.Generator,
    ) -> None:
        super().__init__(agent_id)
        if signal_halflife <= 0:
            raise ValueError(f"signal_halflife must be positive, got {signal_halflife}")
        if signal_sigma < 0:
            raise ValueError(f"signal_sigma must be non-negative, got {signal_sigma}")
        if threshold < 0:
            raise ValueError(f"threshold must be non-negative, got {threshold}")
        if position_limit <= 0:
            raise ValueError(f"position_limit must be positive, got {position_limit}")
        if quote_offset_ticks < 1:
            raise ValueError(f"quote_offset_ticks must be >= 1, got {quote_offset_ticks}")
        if scale <= 0:
            raise ValueError(f"scale must be positive, got {scale}")
        if signal_price_scale < 0:
            raise ValueError(f"signal_price_scale must be non-negative, got {signal_price_scale}")
        if initial_price <= 0:
            raise ValueError(f"initial_price must be positive, got {initial_price}")
        self.signal_halflife: float = signal_halflife
        self.signal_sigma: float = signal_sigma
        self.threshold: float = threshold
        self.position_limit: int = position_limit
        self.quote_offset_ticks: int = quote_offset_ticks
        self.scale: float = scale
        self.signal_price_scale: float = signal_price_scale
        self.initial_price: int = initial_price
        self.rng: np.random.Generator = rng
        self.signal: float = 0.0
        self._last_step_time: Optional[float] = None
        self.resting_order_id: Optional[uuid.UUID] = None
        self._resting_remaining_qty: int = 0
        self._lam: float = float(np.log(2.0) / signal_halflife)

    def _step_signal(self, dt: float) -> None:
        """Advance the signal by `dt` minutes using exact OU
        discretisation. `dt <= 0` is a no-op."""
        if dt <= 0.0:
            return
        decay = float(np.exp(-self._lam * dt))
        var_factor = (1.0 - float(np.exp(-2.0 * self._lam * dt))) / (2.0 * self._lam)
        noise_scale = self.signal_sigma * float(np.sqrt(var_factor))
        self.signal = self.signal * decay + noise_scale * float(self.rng.standard_normal())

    def step(self, state: MarketState) -> list[Union[Order, Cancel]]:
        actions: list[Union[Order, Cancel]] = []

        if self._last_step_time is None:
            dt = 0.0
        else:
            dt = max(0.0, state.timestamp - self._last_step_time)
        self._last_step_time = state.timestamp
        self._step_signal(dt)

        if self.resting_order_id is not None and self._resting_remaining_qty > 0:
            return actions

        if self.resting_order_id is not None:
            actions.append(
                Cancel(
                    order_id=self.resting_order_id,
                    agent_id=self.agent_id,
                    timestamp=state.timestamp,
                )
            )
            self.resting_order_id = None
            self._resting_remaining_qty = 0

        target = int(self.signal * self.scale)
        if target > self.position_limit:
            target = self.position_limit
        elif target < -self.position_limit:
            target = -self.position_limit
        diff = target - self.position

        if diff == 0:
            return actions
        if abs(self.signal) <= self.threshold:
            return actions

        if self.position + diff > self.position_limit:
            diff = self.position_limit - self.position
        elif self.position + diff < -self.position_limit:
            diff = -self.position_limit - self.position
        qty = abs(diff)
        if qty == 0:
            return actions

        signal_offset = int(round(self.signal * self.signal_price_scale))
        base = self.initial_price + signal_offset
        if diff > 0:
            side = Side.BUY
            price = base + self.quote_offset_ticks
        else:
            side = Side.SELL
            price = base - self.quote_offset_ticks
        if price <= 0:
            return actions

        order = Order(
            order_id=uuid.uuid4(),
            agent_id=self.agent_id,
            side=side,
            price=price,
            qty=qty,
            timestamp=state.timestamp,
        )
        actions.append(order)
        self.resting_order_id = order.order_id
        self._resting_remaining_qty = qty
        return actions

    def on_fills(self, fills: list[Fill]) -> None:
        super().on_fills(fills)
        for fill in fills:
            if (
                fill.maker_order_id == self.resting_order_id
                or fill.taker_order_id == self.resting_order_id
            ):
                self._resting_remaining_qty -= fill.qty
                if self._resting_remaining_qty <= 0:
                    self.resting_order_id = None
                    self._resting_remaining_qty = 0

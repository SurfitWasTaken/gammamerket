"""Discrete event scheduler for the market simulation.

Uses a `heapq` priority queue. Each event records `(timestamp, seq)`
so ties are broken deterministically by insertion order. Agents
register with a Poisson arrival rate; the clock draws a fresh
exponential inter-arrival time when the agent's current event fires
and pushes a new event at `now + dt`.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

import numpy as np

from sim.agents.base import Agent, MarketState
from sim.core.lob import LimitOrderBook
from sim.core.tape import Tape


@dataclass(order=True)
class _Event:
    """A scheduled agent step. Comparison is by (time, seq); `agent_id`
    is a lookup key only and is excluded from comparison."""

    time: float
    seq: int
    agent_id: str = field(compare=False)


class Clock:
    """Discrete event scheduler.

    Args:
        book: The LOB to submit orders into. `on_fill` on the book (if
            set) is the source of the fill log; the clock does not
            re-invoke the tape.
        tape: The fill log; used to look up `last_fill_price` for the
            `MarketState` snapshot.
        rng: NumPy `Generator` for drawing exponential inter-arrival
            times. Passing a seeded generator makes the schedule
            deterministic.
    """

    def __init__(
        self,
        book: LimitOrderBook,
        tape: Tape,
        rng: np.random.Generator,
    ) -> None:
        self.book: LimitOrderBook = book
        self.tape: Tape = tape
        self.rng: np.random.Generator = rng
        self.agents: dict[str, Agent] = {}
        self.rates: dict[str, float] = {}
        self._heap: list[_Event] = []
        self._seq: int = 0
        self.now: float = 0.0
        self.step_count: int = 0

    def register(self, agent: Agent, rate_per_min: float) -> None:
        """Register `agent` with a Poisson arrival rate of `rate_per_min`
        events per minute. The first event is scheduled at
        `t = Exp(rate_per_min)` minutes from `self.now`."""
        if rate_per_min <= 0:
            raise ValueError(f"rate_per_min must be positive, got {rate_per_min}")
        if agent.agent_id in self.agents:
            raise KeyError(f"agent_id {agent.agent_id!r} already registered")
        self.agents[agent.agent_id] = agent
        self.rates[agent.agent_id] = rate_per_min
        dt = self.rng.exponential(1.0 / rate_per_min)
        self._schedule_next(agent, dt=dt)

    def step(self) -> float:
        """Pop the next event, run the agent, route fills, and
        reschedule. Returns the new simulation time (the event's
        timestamp). Raises `StopIteration` when the heap is empty."""
        if not self._heap:
            raise StopIteration("event heap is empty")
        event = heapq.heappop(self._heap)
        self.now = event.time
        self.step_count += 1
        agent = self.agents[event.agent_id]
        state = self._build_state(agent)
        orders = agent.step(state)
        for order in orders:
            agent.open_order_ids.add(order.order_id)
            if order.price == 0:
                fills = self.book.submit_market(order)
            else:
                fills = self.book.submit_limit(order)
            if not fills:
                continue
            agent.on_fills(fills)
            for fill in fills:
                if fill.maker_agent_id == fill.taker_agent_id:
                    continue
                maker_agent = self.agents.get(fill.maker_agent_id)
                if maker_agent is not None and maker_agent is not agent:
                    maker_agent.on_fills([fill])
        rate = self.rates[event.agent_id]
        self._schedule_next(agent, dt=self.rng.exponential(1.0 / rate))
        return self.now

    def run(self, max_steps: int) -> float:
        """Run up to `max_steps` events. Returns the final `self.now`."""
        for _ in range(max_steps):
            self.step()
        return self.now

    def _schedule_next(self, agent: Agent, *, dt: float) -> None:
        self._seq += 1
        heapq.heappush(
            self._heap,
            _Event(time=self.now + dt, seq=self._seq, agent_id=agent.agent_id),
        )

    def _build_state(self, agent: Agent) -> MarketState:
        return MarketState(
            best_bid=self.book.best_bid(),
            best_ask=self.book.best_ask(),
            mid=self.book.mid(),
            last_fill_price=self.tape.last_fill_price(),
            own_position=agent.position,
            timestamp=self.now,
        )

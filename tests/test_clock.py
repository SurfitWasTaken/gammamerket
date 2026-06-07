"""Tests for the discrete event clock."""

from __future__ import annotations

import numpy as np
import pytest

from sim.agents.base import Agent, MarketState
from sim.core.clock import Clock, _Event
from sim.core.events import Order
from sim.core.lob import LimitOrderBook
from sim.core.tape import Tape


class _SilentAgent(Agent):
    """Agent that never returns orders. Used to exercise the scheduler
    in isolation from agent logic."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(agent_id)

    def step(self, state: MarketState) -> list[Order]:
        return []


def _make_clock(seed: int = 0) -> tuple[Clock, LimitOrderBook, Tape]:
    book = LimitOrderBook(tick_size=1)
    tape = Tape()
    rng = np.random.default_rng(seed)
    return Clock(book, tape, rng), book, tape


def test_event_orders_by_time_then_seq() -> None:
    e1 = _Event(time=1.0, seq=1, agent_id="a")
    e2 = _Event(time=1.0, seq=2, agent_id="b")
    e3 = _Event(time=2.0, seq=3, agent_id="a")
    assert e1 < e2
    assert e2 < e3
    assert e1 < e3
    assert e2 > e1


def test_clock_starts_empty_and_step_raises() -> None:
    clock, _, _ = _make_clock()
    assert len(clock._heap) == 0
    with pytest.raises(StopIteration):
        clock.step()


def test_register_schedules_first_event_in_future() -> None:
    clock, _, _ = _make_clock()
    a = _SilentAgent("a")
    clock.register(a, rate_per_min=1.0)
    assert len(clock._heap) == 1
    e = clock._heap[0]
    assert e.time > 0.0
    assert e.agent_id == "a"


def test_register_rejects_non_positive_rate() -> None:
    clock, _, _ = _make_clock()
    a = _SilentAgent("a")
    with pytest.raises(ValueError, match="rate_per_min must be positive"):
        clock.register(a, rate_per_min=0.0)
    with pytest.raises(ValueError, match="rate_per_min must be positive"):
        clock.register(a, rate_per_min=-1.0)


def test_register_rejects_duplicate_agent() -> None:
    clock, _, _ = _make_clock()
    a = _SilentAgent("a")
    clock.register(a, rate_per_min=1.0)
    with pytest.raises(KeyError):
        clock.register(a, rate_per_min=2.0)


def test_three_agents_rates_1_2_5_inter_arrival_means_match_rates() -> None:
    """Statistical test: with 10k samples per agent the empirical mean
    inter-arrival should be within 5% of 1/rate."""
    clock, _, _ = _make_clock(seed=42)
    rates = [1.0, 2.0, 5.0]
    agents = []
    for i, r in enumerate(rates):
        a = _SilentAgent(f"a{i}")
        agents.append(a)
        clock.register(a, rate_per_min=r)

    last_time = {a.agent_id: 0.0 for a in agents}
    deltas: dict[str, list[float]] = {a.agent_id: [] for a in agents}

    n_steps = 30_000
    for _ in range(n_steps):
        e = clock._heap[0]
        deltas[e.agent_id].append(e.time - last_time[e.agent_id])
        last_time[e.agent_id] = e.time
        clock.step()

    for i, r in enumerate(rates):
        agent_id = f"a{i}"
        mean_delta = float(np.mean(deltas[agent_id]))
        expected = 1.0 / r
        assert abs(mean_delta - expected) < 0.05 * expected, (
            f"agent {agent_id}: mean delta {mean_delta:.4f} vs "
            f"expected {expected:.4f} (rate {r})"
        )


def test_run_advances_clock_through_n_steps() -> None:
    clock, _, _ = _make_clock(seed=0)
    a = _SilentAgent("a")
    clock.register(a, rate_per_min=10.0)
    final = clock.run(max_steps=50)
    assert clock.step_count == 50
    assert final == clock.now
    assert clock.now > 0.0


def test_clock_advances_time_monotonically() -> None:
    clock, _, _ = _make_clock(seed=0)
    a = _SilentAgent("a")
    b = _SilentAgent("b")
    clock.register(a, rate_per_min=2.0)
    clock.register(b, rate_per_min=3.0)
    times = [clock.step() for _ in range(200)]
    assert times == sorted(times)
    assert times[-1] > times[0]

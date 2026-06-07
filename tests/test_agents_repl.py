"""Tests for the agent-driven REPL building blocks.

The interactive REPL session itself isn't testable, but the
`_setup_sim`, `step`, `run`, and `_on_fill` plumbing is.

Note: module-level globals in `sim.agents_repl` (book, tape, clock)
are rebound by `_setup_sim`. We access them via the module so we
always see the current value, not the value at import time.
"""

from __future__ import annotations

import uuid

import sim.agents_repl as repl
from sim.agents.institution import Institution
from sim.agents.retail import Retail
from sim.config.loader import load_config
from sim.core.events import Fill, Side


def _cfg() -> dict:
    return load_config()


def test_setup_sim_seeds_bbo() -> None:
    repl._setup_sim(_cfg())
    assert repl.book.best_bid() is not None
    assert repl.book.best_ask() is not None
    assert repl.book.spread() == 2 * int(_cfg()["market"]["tick_size"])


def test_setup_sim_populates_10_retail_and_1_institution() -> None:
    repl._setup_sim(_cfg())
    assert repl.clock is not None
    n_retail = sum(1 for a in repl.clock.agents.values() if isinstance(a, Retail))
    n_inst = sum(1 for a in repl.clock.agents.values() if isinstance(a, Institution))
    assert n_retail == 10
    assert n_inst == 1


def test_setup_sim_clears_state_on_repeat() -> None:
    repl._setup_sim(_cfg())
    for _ in range(5):
        repl.step()
    n_before = len(repl.clock.agents)
    repl._setup_sim(_cfg())
    assert len(repl.clock.agents) == n_before
    assert len(repl.tape) == 0
    assert len(repl._fills_view) == 0


def test_step_advances_clock_and_increments_step_count() -> None:
    repl._setup_sim(_cfg())
    t0 = repl.clock.now
    s0 = repl.clock.step_count
    repl.step()
    assert repl.clock.now >= t0
    assert repl.clock.step_count == s0 + 1


def test_run_advances_n_steps() -> None:
    repl._setup_sim(_cfg())
    s0 = repl.clock.step_count
    repl.run(20)
    assert repl.clock.step_count == s0 + 20


def test_run_with_zero_is_noop() -> None:
    repl._setup_sim(_cfg())
    s0 = repl.clock.step_count
    repl.run(0)
    assert repl.clock.step_count == s0


def test_on_fill_appends_to_tape_and_fills_view() -> None:
    repl._setup_sim(_cfg())
    tape_len_before = len(repl.tape)
    view_len_before = len(repl._fills_view)
    f = Fill(
        taker_order_id=uuid.uuid4(),
        maker_order_id=uuid.uuid4(),
        taker_agent_id="t",
        maker_agent_id="m",
        aggressor_side=Side.BUY,
        price=100,
        qty=5,
        timestamp=1.0,
    )
    repl._on_fill(f)
    assert len(repl.tape) == tape_len_before + 1
    assert len(repl._fills_view) == view_len_before + 1
    assert repl._fills_view[-1]["price"] == 100
    assert repl._fills_view[-1]["qty"] == 5


def test_state_prints_summary(capsys) -> None:
    repl._setup_sim(_cfg())
    repl.run(5)
    repl.state()
    out = capsys.readouterr().out
    assert "fills=" in out
    assert "t=" in out


def test_tape_is_populated_by_agent_activity() -> None:
    repl._setup_sim(_cfg())
    repl.run(20)
    assert len(repl.tape) > 0
    for fill in repl.tape:
        assert fill.price > 0
        assert fill.qty > 0


def test_reset_with_new_seed_changes_subsequent_runs() -> None:
    repl._setup_sim(_cfg())
    repl.run(30)
    n_fills_a = len(repl.tape)

    repl.reset(seed=999)
    repl.run(30)
    n_fills_b = len(repl.tape)

    assert n_fills_a > 0
    assert n_fills_b > 0
    assert repl.cfg["market"]["seed"] == 999


def test_manual_order_after_setup_does_not_crash() -> None:
    repl._setup_sim(_cfg())
    seed_bid = repl.book.best_bid()
    seed_ask = repl.book.best_ask()
    new_bid = seed_bid - 50
    o = repl.blimit(new_bid, 3)
    assert o.price == new_bid
    assert o.qty == 3
    assert repl.book.best_bid() == seed_bid
    new_ask = seed_ask + 50
    repl.slimit(new_ask, 2)
    assert repl.book.best_ask() == seed_ask

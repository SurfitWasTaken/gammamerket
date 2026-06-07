"""Agent-driven live REPL.

Drives the discrete-event clock with retail + institution agents and
streams updates to the matplotlib live view (the same `sim.viz`
subprocess used by `sim.repl`). Manual orders can still be submitted
alongside the agents.

Usage:
    python -m sim.agents_repl [--viz] [--config path/to/params.yaml]
    python -m sim.agents_repl --viz --config sim/config/params.yaml

Inside the REPL:
    step()               run one sim event
    run(n=10)            run n events
    auto([delay=0.02])   run continuously; Ctrl-C to stop
    state()              print clock time, fill count, book, inst state
    reset()              rebuild the sim from `cfg` (or reload config)
    viz_on() / viz_off() start/stop the matplotlib view
    blimit / slimit / bmarket / smarket   manual orders
    cancel(order)        cancel a manual order
    show()               print full LOB depth
    book, tape, clock, agents, cfg, fills  inspect sim pieces
"""

from __future__ import annotations

import argparse
import atexit
import code
import json
import subprocess
import sys
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Any, Optional

if __package__ in (None, ""):
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import numpy as np

from sim.agents.institution import Institution
from sim.agents.retail import Retail
from sim.config.loader import load_config
from sim.core.clock import Clock
from sim.core.events import Order, Side
from sim.core.lob import LimitOrderBook
from sim.core.tape import Tape
from sim.snapshot import book_snapshot


SNAPSHOT_PATH: Path = Path("/tmp/gammarket_snapshot.json")
_RECENT_FILLS_MAX: int = 500


_fills_view: deque = deque(maxlen=_RECENT_FILLS_MAX)


def _on_fill(fill) -> None:
    """Bound to the LOB. Records every fill in the central tape and
    in the bounded `fills_view` deque used by the snapshot writer."""
    tape.append(fill)
    _fills_view.append(
        {
            "ts": float(fill.timestamp),
            "side": fill.aggressor_side.value,
            "price": int(fill.price),
            "qty": int(fill.qty),
        }
    )


book: LimitOrderBook = LimitOrderBook(tick_size=1, on_fill=_on_fill)
tape: Tape = Tape()
clock: Optional[Clock] = None
agents: list = []
cfg: dict = {}
viz_process: Optional[subprocess.Popen] = None
_manual_ts: list[float] = [0.0]


def _now() -> float:
    if clock is not None:
        return float(clock.now)
    _manual_ts[0] += 1.0
    return _manual_ts[0]


def _write_snapshot() -> None:
    if viz_process is None:
        return
    try:
        payload = json.dumps(book_snapshot(book, _fills_view, _now()))
    except (TypeError, ValueError):
        return
    try:
        tmp = SNAPSHOT_PATH.with_suffix(SNAPSHOT_PATH.suffix + ".tmp")
        tmp.write_text(payload)
        tmp.replace(SNAPSHOT_PATH)
    except OSError:
        pass


def _setup_sim(config: dict) -> None:
    """(Re)build the sim from `config`. Idempotent."""
    global clock, agents, cfg
    market = config["market"]
    rng = np.random.default_rng(int(market["seed"]))

    book.clear()
    tape.fills.clear()
    _fills_view.clear()
    agents = []
    cfg = dict(config)

    initial_price = int(market["initial_price"])
    tick = int(market["tick_size"])
    bid_qty = int(market["initial_bid_size"])
    ask_qty = int(market["initial_ask_size"])
    book.submit_limit(
        Order(uuid.uuid4(), "seed", Side.BUY, initial_price - tick, bid_qty, _now())
    )
    book.submit_limit(
        Order(uuid.uuid4(), "seed", Side.SELL, initial_price + tick, ask_qty, _now())
    )

    retail_cfg = config["agents"]["retail"]
    for i in range(int(retail_cfg["n_agents"])):
        agents.append(
            Retail(
                agent_id=f"retail_{i}",
                order_size_mean=float(retail_cfg["order_size_mean"]),
                direction_bias=float(retail_cfg["direction_bias"]),
                rng=rng,
            )
        )
    inst_cfg = config["agents"]["institution"]
    agents.append(
        Institution(
            agent_id="inst0",
            signal_halflife=float(inst_cfg["signal_halflife"]),
            signal_sigma=float(inst_cfg["signal_sigma"]),
            threshold=float(inst_cfg["threshold"]),
            position_limit=int(inst_cfg["position_limit"]),
            quote_offset_ticks=int(inst_cfg["quote_offset_ticks"]),
            scale=float(inst_cfg["scale"]),
            signal_price_scale=float(inst_cfg["signal_price_scale"]),
            initial_price=initial_price,
            rng=rng,
        )
    )

    clock = Clock(book, tape, rng)
    for a in agents:
        if isinstance(a, Retail):
            clock.register(a, float(retail_cfg["arrival_rate"]))
        elif isinstance(a, Institution):
            clock.register(a, float(inst_cfg["arrival_rate"]))

    _write_snapshot()


def _emit(fills: list) -> None:
    for f in fills:
        side = f.aggressor_side.value
        print(f"  FILL {f.qty:>4} @ {f.price:<6} ({side})")
    _write_snapshot()


def blimit(price: int, qty: int = 1, agent: str = "you") -> Order:
    o = Order(uuid.uuid4(), agent, Side.BUY, int(price), int(qty), _now())
    _emit(book.submit_limit(o))
    return o


def slimit(price: int, qty: int = 1, agent: str = "you") -> Order:
    o = Order(uuid.uuid4(), agent, Side.SELL, int(price), int(qty), _now())
    _emit(book.submit_limit(o))
    return o


def bmarket(qty: int = 1, agent: str = "you") -> Order:
    o = Order(uuid.uuid4(), agent, Side.BUY, 0, int(qty), _now())
    _emit(book.submit_market(o))
    return o


def smarket(qty: int = 1, agent: str = "you") -> Order:
    o = Order(uuid.uuid4(), agent, Side.SELL, 0, int(qty), _now())
    _emit(book.submit_market(o))
    return o


def cancel(order) -> bool:
    ok = book.cancel(order.order_id)
    _write_snapshot()
    return ok


def show() -> None:
    """Print the LOB depth (best, full book)."""
    print("--- LOB ---")
    print(
        f"  best_bid={book.best_bid()}  best_ask={book.best_ask()}  "
        f"spread={book.spread()}  mid={book.mid()}"
    )
    print(f"  resting orders: {len(book)}")
    if book.asks:
        print("  asks (worst -> best):")
        for p in reversed(book.asks.keys()):
            print(f"    ASK {p:>6}  qty={book.depth(Side.SELL, p)}")
    if book.bids:
        print("  bids (best -> worst):")
        for p in reversed(book.bids.keys()):
            print(f"    BID {p:>6}  qty={book.depth(Side.BUY, p)}")


def step() -> float:
    """Run one sim event. Returns the new clock time."""
    if clock is None:
        print("(no sim running; call reset())")
        return 0.0
    try:
        t = clock.step()
    except StopIteration:
        print("(event heap empty)")
        return float(clock.now)
    _write_snapshot()
    return t


def run(n: int = 10) -> float:
    """Run n sim events. Returns the final clock time."""
    if clock is None:
        print("(no sim running; call reset())")
        return 0.0
    for _ in range(max(0, n)):
        try:
            clock.step()
        except StopIteration:
            print("(event heap empty)")
            break
    _write_snapshot()
    state()
    return float(clock.now)


def auto(delay: float = 0.02) -> None:
    """Run continuously; Ctrl-C to stop. Writes a snapshot at each
    step so the matplotlib viz updates in real time."""
    if clock is None:
        print("(no sim running; call reset())")
        return
    print(f"  auto-running  delay={delay}s/step  Ctrl-C to stop")
    try:
        while True:
            try:
                clock.step()
            except StopIteration:
                print("(event heap empty)")
                return
            _write_snapshot()
            time.sleep(delay)
    except KeyboardInterrupt:
        print("\n  (auto stopped)")


def state() -> None:
    """Print clock time, fill count, book summary, and institution state."""
    if clock is None:
        print("(no sim running)")
        return
    print(
        f"  t={clock.now:8.4f} min   step={clock.step_count:5d}   "
        f"fills={len(tape):4d}"
    )
    print(f"  {book()}")
    inst = next((a for a in agents if isinstance(a, Institution)), None)
    if inst is not None:
        resting = "none" if inst.resting_order_id is None else "yes"
        print(
            f"  inst: signal={inst.signal:+7.3f}  pos={inst.position:+5d}  "
            f"resting={resting}"
        )


def reset(seed: Optional[int] = None) -> None:
    """Rebuild the sim. If `seed` is given, override `cfg.market.seed`
    before rebuilding."""
    if not cfg:
        cfg.update(load_config())
    if seed is not None:
        cfg["market"]["seed"] = int(seed)
    _setup_sim(cfg)
    print(f"  (sim reset: {len(agents)} agents, BBO seeded, seed={cfg['market']['seed']})")


def viz_on() -> None:
    """Spawn the matplotlib live view as a subprocess."""
    global viz_process
    if viz_process is not None and viz_process.poll() is None:
        print("  (viz already running)")
        return
    _write_snapshot()
    viz_process = subprocess.Popen(
        [sys.executable, "-m", "sim.viz", "--snapshot", str(SNAPSHOT_PATH)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(
        f"  (viz started, pid={viz_process.pid}, snapshot={SNAPSHOT_PATH})"
    )


def viz_off() -> None:
    """Terminate the matplotlib live view subprocess."""
    global viz_process
    if viz_process is None or viz_process.poll() is not None:
        viz_process = None
        print("  (viz not running)")
        return
    viz_process.terminate()
    try:
        viz_process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        viz_process.kill()
    viz_process = None
    print("  (viz stopped)")


atexit.register(viz_off)


_BANNER = """
gammarket agents REPL  (Phase 2)

  Start: python -m sim.agents_repl [--viz] [--config path/to/params.yaml]

  step()              run one event
  run(n=10)           run n events
  auto([delay=0.02])  run continuously, Ctrl-C to stop
  state()             show clock time, fill count, book, inst state
  reset([seed])       rebuild sim (optionally override seed)
  viz_on() / viz_off()  start/stop the matplotlib live view

  blimit / slimit / bmarket / smarket   manual orders
  cancel(order)       cancel a manual order
  show()              print full LOB depth

  book, tape, clock, agents, cfg, fills  inspect sim pieces
  Side, Order, Institution, Retail      types

Tip: viz_on(); auto();   <-- watch the depth + fills animate
"""


def help() -> None:
    print(_BANNER)


def main() -> None:
    parser = argparse.ArgumentParser(description="gammarket agents REPL")
    parser.add_argument(
        "--viz", action="store_true", help="open matplotlib live view on launch"
    )
    parser.add_argument(
        "--config", type=str, default=None, help="path to config yaml"
    )
    parser.add_argument(
        "--seed", type=int, default=None, help="override the seed from the config"
    )
    args = parser.parse_args()

    if args.config is not None:
        loaded = load_config(args.config)
    else:
        loaded = load_config()
    if args.seed is not None:
        loaded["market"]["seed"] = int(args.seed)
    _setup_sim(loaded)

    print(_BANNER)
    print(
        f"  loaded: n_retail={int(loaded['agents']['retail']['n_agents'])}, "
        f"1 institution, max_steps={loaded['market']['max_steps']}, "
        f"seed={loaded['market']['seed']}"
    )
    if args.viz:
        viz_on()

    namespace = {
        "book": book,
        "tape": tape,
        "clock": clock,
        "agents": agents,
        "cfg": loaded,
        "fills": _fills_view,
        "step": step,
        "run": run,
        "auto": auto,
        "state": state,
        "reset": reset,
        "viz_on": viz_on,
        "viz_off": viz_off,
        "blimit": blimit,
        "slimit": slimit,
        "bmarket": bmarket,
        "smarket": smarket,
        "cancel": cancel,
        "show": show,
        "help": help,
        "Side": Side,
        "Order": Order,
        "Institution": Institution,
        "Retail": Retail,
    }
    code.interact(banner="", local=namespace, exitmsg="bye")


if __name__ == "__main__":
    main()

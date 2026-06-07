"""Interactive REPL for poking at the LOB.

Run with: `python -m sim.repl`

Direct invocation `python sim/repl.py` also works (path bootstrap
below ensures `sim` is importable even when run by file path).

Once inside, type `help()` for a command list. The `book` global is a
fresh `LimitOrderBook` ready for orders.
"""

from __future__ import annotations

import argparse
import atexit
import json
import subprocess
import sys
import uuid
from pathlib import Path

if __package__ in (None, ""):
    _root = Path(__file__).resolve().parent.parent
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import code

from sim.core.events import Order, Side
from sim.core.lob import LimitOrderBook
from sim.snapshot import book_snapshot


SNAPSHOT_PATH: Path = Path("/tmp/gammarket_snapshot.json")
_FILL_HISTORY_MAX: int = 200

book: LimitOrderBook = LimitOrderBook(tick_size=1)
_clock: list[int] = [0]
_fill_history: list[dict] = []
_viz_process: subprocess.Popen | None = None


def _ts() -> float:
    _clock[0] += 1
    return float(_clock[0])


def _record_fill(fill) -> None:
    _fill_history.append(
        {
            "ts": float(fill.timestamp),
            "side": fill.aggressor_side.value,
            "price": int(fill.price),
            "qty": int(fill.qty),
        }
    )
    if len(_fill_history) > _FILL_HISTORY_MAX:
        del _fill_history[: len(_fill_history) - _FILL_HISTORY_MAX]


def _write_snapshot() -> None:
    if _viz_process is None:
        return
    try:
        SNAPSHOT_PATH.write_text(
            json.dumps(book_snapshot(book, _fill_history, float(_clock[0])))
        )
    except OSError:
        pass


def _emit(fills: list) -> None:
    for f in fills:
        side = f.aggressor_side.value
        print(f"  FILL {f.qty:>4} @ {f.price:<6} ({side})")
        _record_fill(f)
    _write_snapshot()


def blimit(price: int, qty: int = 1, agent: str = "you") -> Order:
    """Submit a BUY limit order. Returns the Order."""
    o = Order(uuid.uuid4(), agent, Side.BUY, int(price), int(qty), _ts())
    _emit(book.submit_limit(o))
    return o


def slimit(price: int, qty: int = 1, agent: str = "you") -> Order:
    """Submit a SELL limit order. Returns the Order."""
    o = Order(uuid.uuid4(), agent, Side.SELL, int(price), int(qty), _ts())
    _emit(book.submit_limit(o))
    return o


def bmarket(qty: int = 1, agent: str = "you") -> Order:
    """Submit a BUY market order. Returns the Order."""
    o = Order(uuid.uuid4(), agent, Side.BUY, 0, int(qty), _ts())
    _emit(book.submit_market(o))
    return o


def smarket(qty: int = 1, agent: str = "you") -> Order:
    """Submit a SELL market order. Returns the Order."""
    o = Order(uuid.uuid4(), agent, Side.SELL, 0, int(qty), _ts())
    _emit(book.submit_market(o))
    return o


def cancel(order) -> bool:
    """Cancel an order by passing the Order object. Returns True if removed."""
    ok = book.cancel(order.order_id)
    _write_snapshot()
    return ok


def reset() -> None:
    """Drop all resting orders, fill history, and reset the clock."""
    global book
    book = LimitOrderBook(tick_size=1)
    _clock[0] = 0
    _fill_history.clear()
    _write_snapshot()
    print("  (book reset)")


def show() -> None:
    """Print a snapshot of book state: best bid/ask, mid, spread, full depth."""
    print("--- LOB ---")
    print(f"  best_bid={book.best_bid()}  best_ask={book.best_ask()}  "
          f"spread={book.spread()}  mid={book.mid()}")
    print(f"  resting orders: {len(book)}")
    if book.asks:
        print("  asks (worst -> best):")
        for p in reversed(book.asks.keys()):
            print(f"    ASK {p:>6}  qty={book.depth(Side.SELL, p)}")
    if book.bids:
        print("  bids (best -> worst):")
        for p in reversed(book.bids.keys()):
            print(f"    BID {p:>6}  qty={book.depth(Side.BUY, p)}")


def viz_on() -> None:
    """Spawn the matplotlib live view as a subprocess."""
    global _viz_process
    if _viz_process is not None and _viz_process.poll() is None:
        print("  (viz already running)")
        return
    _write_snapshot()
    _viz_process = subprocess.Popen(
        [sys.executable, "-m", "sim.viz", "--snapshot", str(SNAPSHOT_PATH)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"  (viz started, pid={_viz_process.pid}, snapshot={SNAPSHOT_PATH})")


def viz_off() -> None:
    """Terminate the matplotlib live view subprocess."""
    global _viz_process
    if _viz_process is None or _viz_process.poll() is not None:
        _viz_process = None
        print("  (viz not running)")
        return
    _viz_process.terminate()
    try:
        _viz_process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        _viz_process.kill()
    _viz_process = None
    print("  (viz stopped)")


atexit.register(viz_off)


def help() -> None:
    print(_BANNER)


_BANNER = """
gammarket LOB REPL  (Phase 1)

  Start: python -m sim.repl [--viz]

  blimit(price, qty=1)    submit BUY limit, returns the Order
  slimit(price, qty=1)    submit SELL limit, returns the Order
  bmarket(qty=1)          submit BUY market
  smarket(qty=1)         submit SELL market
  cancel(order)           cancel a resting Order
  show()                  print full book state
  reset()                 wipe the book and start over
  viz_on()                open matplotlib live view (separate window)
  viz_off()               close the live view
  book                    the LimitOrderBook instance
  Side, Order             event types

Tip: o = blimit(100); cancel(o)
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="gammarket LOB REPL")
    parser.add_argument(
        "--viz",
        action="store_true",
        help="open matplotlib live view in a separate window on launch",
    )
    args = parser.parse_args()

    print(_BANNER)
    if args.viz:
        viz_on()

    namespace = {
        "book": book,
        "blimit": blimit,
        "slimit": slimit,
        "bmarket": bmarket,
        "smarket": smarket,
        "cancel": cancel,
        "show": show,
        "reset": reset,
        "viz_on": viz_on,
        "viz_off": viz_off,
        "help": help,
        "Side": Side,
        "Order": Order,
    }
    code.interact(banner="", local=namespace, exitmsg="bye")


if __name__ == "__main__":
    main()

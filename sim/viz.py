"""Live matplotlib visualisation of the LOB.

Runs as a subprocess spawned by `sim.repl` or `sim.agents_repl` when
the `--viz` flag is given. Polls a JSON snapshot file written by the
REPL and renders:

    * A horizontal depth bar chart (bids green, asks red, mid dashed).
    * A scatter/line of recent fills coloured by aggressor side.

The window is a native macOS window (matplotlib `macosx` backend);
TkAgg is the cross-platform fallback. If neither backend is available
the script prints a clear error and exits non-zero.

Run standalone:  python -m sim.viz --snapshot /tmp/gammarket_snapshot.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from matplotlib.ticker import FuncFormatter


def _select_backend() -> None:
    """Pick a usable matplotlib backend. Called from `run_viz`, not at
    import time, so tests can import this module under the headless
    `Agg` backend without it being clobbered."""
    try:
        import matplotlib
        matplotlib.use("macosx")
        return
    except Exception:
        pass
    try:
        import matplotlib
        matplotlib.use("TkAgg")
        return
    except Exception:
        pass
    sys.stderr.write(
        "sim.viz: no usable matplotlib backend (need 'macosx' or 'TkAgg')\n"
    )
    sys.exit(1)


def _format_price_axis(ax) -> None:
    """Render the y-axis as integer prices with no offset notation.

    Matplotlib auto-enables an offset (e.g. `+1e4`) when the price
    magnitude dominates the spread — which makes a 2-tick range look
    like it spans -10000 to +10000. We force plain integer labels
    so the user sees the actual fill prices.
    """
    ax.ticklabel_format(useOffset=False, axis="y", style="plain")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{int(round(v))}"))


def _load_snapshot(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _render(ax_depth, ax_fills, snap: dict) -> None:
    bids = snap.get("bids", {})
    asks = snap.get("asks", {})
    fills = snap.get("fills", [])

    ax_depth.clear()
    ax_fills.clear()

    if not bids and not asks and not fills:
        ax_depth.set_title("Depth  (empty book)")
        ax_depth.text(
            0.5, 0.5,
            "No orders or fills yet.\n\n"
            "  sim.repl          blimit / slimit / bmarket / smarket\n"
            "  sim.agents_repl   run with --viz to watch the live market",
            ha="center", va="center",
            transform=ax_depth.transAxes,
            fontsize=10, color="dimgray",
        )
        ax_depth.set_xticks([])
        ax_depth.set_yticks([])
        ax_fills.set_title("Recent fills  (0)")
        ax_fills.set_xticks([])
        ax_fills.set_yticks([])
        return
    if bids:
        bp = sorted(int(p) for p in bids)
        bq = [bids[str(p)] for p in bp]
        ax_depth.barh(bp, bq, color="#2ca02c", alpha=0.7, label="bids")
    if asks:
        ap = sorted(int(p) for p in asks)
        aq = [asks[str(p)] for p in ap]
        ax_depth.barh(ap, aq, color="#d62728", alpha=0.7, label="asks")
    mid = snap.get("mid")
    if mid is not None:
        ax_depth.axhline(mid, color="black", linestyle="--", alpha=0.5, label=f"mid={mid}")
    ax_depth.set_xlabel("qty")
    ax_depth.set_ylabel("price")
    bb, ba = snap.get("best_bid"), snap.get("best_ask")
    spread = snap.get("spread")
    ax_depth.set_title(f"Depth  bid={bb}  ask={ba}  spread={spread}")
    if bids or asks:
        ax_depth.legend(loc="best", fontsize=8)
    ax_depth.grid(True, alpha=0.2)
    _format_price_axis(ax_depth)

    if fills:
        ts = [f["ts"] for f in fills]
        px = [f["price"] for f in fills]
        colors = ["#2ca02c" if f["side"] == "BUY" else "#d62728" for f in fills]
        ax_fills.plot(ts, px, "k-", alpha=0.3, linewidth=1)
        ax_fills.scatter(ts, px, c=colors, s=22, alpha=0.85, edgecolors="none")
    ax_fills.set_xlabel("time")
    ax_fills.set_ylabel("fill price")
    ax_fills.set_title(f"Recent fills  ({len(fills)})")
    ax_fills.grid(True, alpha=0.2)
    _format_price_axis(ax_fills)


def run_viz(snapshot_path: os.PathLike, refresh_hz: float = 5.0) -> None:
    """Block and render until killed. Subprocess entry point."""
    _select_backend()
    import matplotlib.pyplot as plt  # noqa: E402  (after backend select)

    path = Path(snapshot_path)
    sleep_s = 1.0 / refresh_hz

    plt.ion()
    fig, (ax_depth, ax_fills) = plt.subplots(1, 2, figsize=(12, 6))
    fig.suptitle("gammarket LOB — live")

    last_mtime = 0.0
    stale = 0
    try:
        while True:
            try:
                mtime = path.stat().st_mtime if path.exists() else 0.0
            except OSError:
                mtime = 0.0
            if mtime != last_mtime:
                snap = _load_snapshot(path)
                if snap is not None:
                    _render(ax_depth, ax_fills, snap)
                    fig.tight_layout()
                    fig.canvas.draw()
                    fig.canvas.flush_events()
                    last_mtime = mtime
                    stale = 0
                else:
                    last_mtime = mtime
            if path.exists() and last_mtime == 0:
                stale += 1
                if stale > 50:
                    ax_depth.set_title("(waiting for first snapshot...)")
                    fig.canvas.draw()
                    fig.canvas.flush_events()
            plt.pause(sleep_s)
    except KeyboardInterrupt:
        pass
    finally:
        plt.ioff()
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="gammarket LOB live viz")
    parser.add_argument(
        "--snapshot",
        default="/tmp/gammarket_snapshot.json",
        help="path to the JSON snapshot written by sim.repl or sim.agents_repl",
    )
    parser.add_argument(
        "--refresh-hz",
        type=float,
        default=5.0,
        help="redraw frequency in Hz",
    )
    args = parser.parse_args()
    run_viz(args.snapshot, refresh_hz=args.refresh_hz)


if __name__ == "__main__":
    main()

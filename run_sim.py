"""Phase 2 simulation runner.

Builds a market with N retail noise-traders + 1 institutional
speculator, seeds a tight BBO, drives the discrete-event clock, and
produces a 3-panel summary plot (price series, return
autocorrelation, trade-size distribution).

Usage:
    python run_sim.py            # uses sim/config/params.yaml
    python run_sim.py --no-plot  # skip the matplotlib summary
"""

from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from typing import Any

import numpy as np

from sim.agents.equity_mm import EquityMarketMaker, EquityMMConfig
from sim.agents.institution import Institution
from sim.agents.retail import Retail
from sim.analytics.metrics import (
    autocorrelation,
    fill_prices,
    simple_returns,
    trade_sizes,
)
from sim.config.loader import load_config
from sim.core.clock import Clock
from sim.core.events import Order, Side
from sim.core.lob import LimitOrderBook
from sim.core.tape import Tape


def _build_book_and_tape(cfg_market: dict) -> tuple[LimitOrderBook, Tape]:
    tape = Tape()
    book = LimitOrderBook(
        tick_size=cfg_market["tick_size"], on_fill=tape.append
    )
    return book, tape


def _seed_bbo(book: LimitOrderBook, cfg_market: dict) -> None:
    initial_price = int(cfg_market["initial_price"])
    tick = int(cfg_market["tick_size"])
    bid_price = initial_price - tick
    ask_price = initial_price + tick
    bid_qty = int(cfg_market["initial_bid_size"])
    ask_qty = int(cfg_market["initial_ask_size"])
    now = 0.0
    book.submit_limit(
        Order(uuid.uuid4(), "seed", Side.BUY, bid_price, bid_qty, now)
    )
    book.submit_limit(
        Order(uuid.uuid4(), "seed", Side.SELL, ask_price, ask_qty, now)
    )


def _build_agents(cfg: dict, rng: np.random.Generator) -> list:
    retail_cfg = cfg["agents"]["retail"]
    agents: list = []
    for i in range(int(retail_cfg["n_agents"])):
        agents.append(
            Retail(
                agent_id=f"retail_{i}",
                order_size_mean=float(retail_cfg["order_size_mean"]),
                direction_bias=float(retail_cfg["direction_bias"]),
                rng=rng,
            )
        )
    inst_cfg = cfg["agents"]["institution"]
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
            initial_price=int(cfg["market"]["initial_price"]),
            rng=rng,
        )
    )
    mm_cfg = cfg["agents"]["equity_mm"]
    agents.append(
        EquityMarketMaker(
            agent_id="mm0",
            config=EquityMMConfig(
                arrival_rate=float(mm_cfg["arrival_rate"]),
                spread_target=int(mm_cfg["spread_target"]),
                inventory_limit=int(mm_cfg["inventory_limit"]),
                risk_aversion=float(mm_cfg["risk_aversion"]),
                quote_size=int(mm_cfg["quote_size"]),
                max_orders_per_side=int(mm_cfg["max_orders_per_side"]),
            ),
            rng=rng,
        )
    )
    return agents


def _register(clock: Clock, agents: list, cfg: dict) -> None:
    retail_rate = float(cfg["agents"]["retail"]["arrival_rate"])
    inst_rate = float(cfg["agents"]["institution"]["arrival_rate"])
    mm_rate = float(cfg["agents"]["equity_mm"]["arrival_rate"])
    for a in agents:
        if isinstance(a, Retail):
            clock.register(a, retail_rate)
        elif isinstance(a, Institution):
            clock.register(a, inst_rate)
        elif isinstance(a, EquityMarketMaker):
            clock.register(a, mm_rate)


def run(cfg: dict) -> dict[str, Any]:
    """Build the sim from `cfg`, run to completion, return diagnostics.

    The returned dict has keys `tape`, `book`, `clock`, `agents`, `cfg`.
    The function is pure of file I/O: the same `cfg` always yields the
    same outcome (modulo numpy seeding, which is honoured).
    """
    market = cfg["market"]
    rng = np.random.default_rng(int(market["seed"]))
    book, tape = _build_book_and_tape(market)
    _seed_bbo(book, market)
    agents = _build_agents(cfg, rng)
    clock = Clock(book, tape, rng)
    _register(clock, agents, cfg)
    clock.run(int(market["max_steps"]))
    return {
        "tape": tape,
        "book": book,
        "clock": clock,
        "agents": agents,
        "cfg": cfg,
    }


def _summary(result: dict) -> dict[str, Any]:
    tape: Tape = result["tape"]
    fills = tape.fills
    prices = fill_prices(fills)
    sizes = trade_sizes(fills)
    out: dict[str, Any] = {
        "n_fills": len(fills),
        "n_steps": result["clock"].step_count,
        "final_clock_time": float(result["clock"].now),
    }
    if len(prices) > 0:
        out["first_fill_price"] = int(prices[0])
        out["last_fill_price"] = int(prices[-1])
        out["mean_trade_size"] = float(sizes.mean())
    if len(prices) > 2:
        r = simple_returns(prices)
        out["return_std"] = float(r.std())
        acf = autocorrelation(r, max_lag=5)
        out["autocorr_lag_1"] = float(acf[0])
    return out


def _plot(result: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter

    tape: Tape = result["tape"]
    fills = tape.fills
    fig, axes = plt.subplots(1, 3, figsize=(15, 4))

    prices = fill_prices(fills)
    if len(prices) > 0:
        axes[0].plot(prices, linewidth=0.7, color="#1f77b4")
        pad = max(1, (int(prices.max()) - int(prices.min())) // 10 + 1)
        axes[0].set_ylim(int(prices.min()) - pad, int(prices.max()) + pad)
        axes[0].yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{int(x):,}"))
        axes[0].set_title("Fill price series")
        axes[0].set_xlabel("fill #")
        axes[0].set_ylabel("price (ticks)")
        axes[0].grid(True, alpha=0.3)
    else:
        axes[0].text(0.5, 0.5, "(no fills)", ha="center", va="center",
                     transform=axes[0].transAxes)

    if len(prices) > 2:
        r = simple_returns(prices)
        acf = autocorrelation(r, max_lag=min(20, len(r) - 1))
        axes[1].bar(range(1, len(acf) + 1), acf, color="#1f77b4")
        axes[1].axhline(0.0, color="black", linewidth=0.5)
        axes[1].set_title("Return autocorrelation")
        axes[1].set_xlabel("lag")
        axes[1].set_ylabel("acf")
        axes[1].grid(True, alpha=0.3)
    else:
        axes[1].text(0.5, 0.5, "(not enough fills)", ha="center", va="center",
                     transform=axes[1].transAxes)

    sizes = trade_sizes(fills)
    if len(sizes) > 0:
        n_bins = int(min(20, max(1, sizes.max())))
        axes[2].hist(sizes, bins=n_bins, edgecolor="black", color="#2ca02c")
        axes[2].set_title("Trade size distribution")
        axes[2].set_xlabel("quantity (lots)")
        axes[2].set_ylabel("count")
        axes[2].grid(True, alpha=0.3)
    else:
        axes[2].text(0.5, 0.5, "(no fills)", ha="center", va="center",
                     transform=axes[2].transAxes)

    fig.suptitle("gammarket Phase 3 — run summary")
    fig.tight_layout()
    fig.savefig(path, dpi=100)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="gammarket Phase 2 runner")
    parser.add_argument(
        "--no-plot",
        action="store_true",
        help="skip the matplotlib summary plot",
    )
    parser.add_argument(
        "--plot-path",
        type=Path,
        default=Path("results/phase2.png"),
        help="output path for the summary plot (default: results/phase2.png)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="path to config yaml (default: sim/config/params.yaml)",
    )
    args = parser.parse_args()

    cfg_path = args.config if args.config is not None else None
    cfg = load_config(cfg_path) if cfg_path is not None else load_config()

    result = run(cfg)
    summary = _summary(result)

    for k, v in summary.items():
        print(f"  {k}: {v}")

    if not args.no_plot:
        plot_path: Path = args.plot_path
        plot_path.parent.mkdir(parents=True, exist_ok=True)
        _plot(result, plot_path)
        print(f"  plot: {plot_path}")


if __name__ == "__main__":
    main()

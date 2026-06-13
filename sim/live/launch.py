"""Multi-terminal dashboard launcher (macOS Terminal.app).

Reads `params.yaml` to discover agents, then spawns:
  - One Terminal window per agent dashboard (Rich TUI)
  - One Terminal window for the sim runner
  - One matplotlib 3D options surface window

Usage:
    python -m sim.live.launch
    python -m sim.live.launch --config path/to/params.yaml
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

from sim.config.loader import load_config

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _python() -> str:
    return sys.executable


def _terminal(cmd: str, title: str = "") -> None:
    """Open a new macOS Terminal.app window running `cmd`."""
    if title:
        full = f"echo -n $'\\033]0;{title}\\007'; {cmd}"
    else:
        full = cmd
    script = f'tell application "Terminal" to do script {shlex.quote(full)}'
    subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _background(cmd: str) -> None:
    """Launch a background process (no terminal window)."""
    subprocess.Popen(
        cmd, shell=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="gammarket live dashboard launcher")
    parser.add_argument("--config", type=str, default=None, help="path to config yaml")
    parser.add_argument("--no-surface", action="store_true", help="skip 3D surface viz")
    parser.add_argument(
        "--step-delay", type=float, default=0.0,
        help="delay between sim steps (seconds)",
    )
    args = parser.parse_args()

    cfg = load_config(args.config) if args.config else load_config()
    py = _python()
    root = _PROJECT_ROOT
    state_path = "/tmp/gammarket_agent_state.json"

    # Discover agents
    viewer_ids: list[tuple[str, str]] = [
        ("market", "Market Overview"),
        ("retail", "Retail Overview"),
    ]

    # Institution (if present)
    viewer_ids.append(("inst0", "Institution"))

    # Equity MMs
    mm_cfgs = cfg["agents"].get("equity_mms", [cfg["agents"].get("equity_mm")])
    for mm in mm_cfgs:
        if mm is None:
            continue
        aid = mm.get("id", "mm0")
        viewer_ids.append((aid, f"MM: {aid}"))

    # Options dealer + flow
    if "options_flow" in cfg["agents"]:
        viewer_ids.append(("options_mm", "Options MM"))
        viewer_ids.append(("options_flow", "Options Flow"))

    n_windows = len(viewer_ids) + 1  # +1 for sim runner
    n_surface = 0 if args.no_surface else 1

    print(f"  gammarket live dashboard: {n_windows} Terminal windows + {n_surface} surface viz")
    print(f"  Project root: {root}")
    print(f"  Python: {py}")
    print()

    # 1. Start the sim runner
    print(f"  [1/{n_windows + n_surface}] Launching sim runner...")
    sim_cmd = (
        f"cd {shlex.quote(str(root))} && {py} -m sim.live.sim_runner "
        f"--state-path {state_path}"
    )
    if args.step_delay > 0:
        sim_cmd += f" --step-delay {args.step_delay}"
    _terminal(sim_cmd, "gammarket sim runner")

    # 2. Launch the surface viz (background subprocess, no terminal)
    if not args.no_surface:
        print(f"  [2/{n_windows + n_surface}] Launching 3D surface viz...")
        _background(
            f"cd {shlex.quote(str(root))} && {py} -m sim.live.surface_viz "
            f"--state-path {state_path}"
        )
        time.sleep(0.5)

    # 3. Launch each agent viewer in its own Terminal window
    for i, (agent_id, label) in enumerate(viewer_ids, start=2 if not args.no_surface else 1):
        print(f"  [{i}/{n_windows + n_surface}] Launching {label}...")
        _terminal(
            f"cd {shlex.quote(str(root))} && {py} -m sim.live.agent_viewer "
            f"--id {agent_id} --state-path {state_path}",
            title=f"gammarket: {label}",
        )
        time.sleep(0.3)

    print()
    print("  All windows launched. Press Ctrl-C in any viewer to close it.")
    print("  The sim runner prints progress; viewers update at ~5 Hz.")
    print()


if __name__ == "__main__":
    main()

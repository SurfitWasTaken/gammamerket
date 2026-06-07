"""YAML config loader.

Single read site: `run_sim.py`. Tests and inline experiments pass their
own config dicts directly to agent constructors, never calling this
loader, so the loader is the only place we touch the filesystem.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Union

import yaml

DEFAULT_CONFIG_PATH: Path = Path(__file__).resolve().parent / "params.yaml"

ConfigPath = Union[str, Path]


def load_config(path: ConfigPath = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    """Read and parse a YAML config file into a nested dict.

    Args:
        path: Filesystem path to a YAML file. Defaults to
            `sim/config/params.yaml` relative to this module.

    Returns:
        A nested dict; consumers index into `cfg["agents"]["retail"]`
        etc. Schema validation is intentionally minimal — the runner is
        the only consumer and it asserts the keys it needs.

    Raises:
        FileNotFoundError: If `path` does not exist.
        ValueError: If the file is empty or unparseable.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"config file not found: {p}")
    with open(p) as f:
        cfg = yaml.safe_load(f)
    if cfg is None:
        raise ValueError(f"config file is empty: {p}")
    if not isinstance(cfg, dict):
        raise ValueError(f"config root must be a mapping, got {type(cfg).__name__}")
    return cfg

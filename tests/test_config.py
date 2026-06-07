"""Tests for the YAML config loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from sim.config.loader import DEFAULT_CONFIG_PATH, load_config


def test_default_config_file_exists_and_parses() -> None:
    cfg = load_config()
    assert isinstance(cfg, dict)
    assert "market" in cfg
    assert "agents" in cfg
    assert "retail" in cfg["agents"]
    assert "institution" in cfg["agents"]


def test_default_config_has_required_keys() -> None:
    cfg = load_config()
    market = cfg["market"]
    for k in ("tick_size", "lot_size", "initial_price", "max_steps", "seed"):
        assert k in market, f"missing market key: {k}"
    retail = cfg["agents"]["retail"]
    for k in ("n_agents", "arrival_rate", "order_size_mean", "direction_bias"):
        assert k in retail, f"missing retail key: {k}"
    inst = cfg["agents"]["institution"]
    for k in (
        "arrival_rate",
        "signal_halflife",
        "signal_sigma",
        "threshold",
        "position_limit",
        "quote_offset_ticks",
        "scale",
    ):
        assert k in inst, f"missing institution key: {k}"


def test_load_explicit_path(tmp_path: Path) -> None:
    p = tmp_path / "custom.yaml"
    p.write_text("market:\n  tick_size: 2\n  seed: 7\nagents: {}\n")
    cfg = load_config(p)
    assert cfg["market"]["tick_size"] == 2
    assert cfg["market"]["seed"] == 7


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="config file not found"):
        load_config(tmp_path / "nonexistent.yaml")


def test_load_empty_file_raises(tmp_path: Path) -> None:
    p = tmp_path / "empty.yaml"
    p.write_text("")
    with pytest.raises(ValueError, match="config file is empty"):
        load_config(p)


def test_load_non_mapping_root_raises(tmp_path: Path) -> None:
    p = tmp_path / "list.yaml"
    p.write_text("- one\n- two\n")
    with pytest.raises(ValueError, match="config root must be a mapping"):
        load_config(p)


def test_default_path_resolves_to_sim_config_params() -> None:
    assert Path(DEFAULT_CONFIG_PATH).name == "params.yaml"
    assert "sim/config" in str(DEFAULT_CONFIG_PATH)

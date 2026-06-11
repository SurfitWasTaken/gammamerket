# Market Simulator — Claude Project Context

## Project Identity
This is a **closed-loop, multi-agent artificial equity + options market simulator**.
The goal is to generate realistic price dynamics endogenously through agent interactions,
culminating in a full delta/gamma hedging feedback loop between an options dealer and
the underlying equity limit order book.

## Operating Docs — start here
This file is the **authoritative** source for architecture, coding standards, and
per-phase contracts. The **operating layer** (goals, roadmap, current workplan,
TODO) lives in **`docs/`** — start at **`docs/README.md`**:
- `docs/GOALS.md` — north star + definition of done (stylised facts)
- `docs/ROADMAP.md` — the six-phase plan and current position
- `docs/PHASE_4_WORKPLAN.md` — the immediate work: Options Pricing + Chain
- `docs/TODO.md` — the living checklist
If `docs/` and this file ever disagree, **CLAUDE.md wins** — fix one to match the
other in the same commit.

## Architecture Overview
Legend: `[x]` exists on disk today (end of Phase 3); `[ ]` planned for a later
phase and not yet created. Keep this tree in sync with reality — do not list a
module here until it is committed.

```
sim/
├── core/
│   ├── lob.py            [x] Limit order book engine (price-time priority).
│   │                         Matching lives INSIDE lob.py (_sweep); there is no
│   │                         separate matching.py.
│   ├── clock.py          [x] Discrete event scheduler + MarketState builder
│   ├── tape.py           [x] Central fill tape (callback-injected into LOB)
│   └── events.py         [x] Event types: Order, Fill, Cancel, Side
├── agents/
│   ├── base.py           [x] Agent base class + MarketState dataclass
│   ├── retail.py         [x] Noise traders (Poisson arrivals, market orders)
│   ├── institution.py    [x] Mean-reverting (OU-signal) limit speculator
│   ├── equity_mm.py      [x] Equity market maker (inventory + vol-aware quoting)
│   └── options_mm.py     [ ] Options dealer (BS pricing + delta hedging) — Phase 5
├── options/              [ ] entire package — Phase 4
│   ├── pricer.py         [ ] Black-Scholes pricing, Greeks (delta, gamma, vega)
│   ├── surface.py        [ ] Implied vol surface (flat to start, dynamic later)
│   └── chain.py          [ ] Options chain (strikes, expiries, series management)
├── analytics/
│   └── metrics.py        [x] returns, autocorrelation, trade sizes (NumPy-only).
│                             (No logger.py yet — the Tape is the fill log.
│                             Effective spread/depth/vol metrics are Phase 6.)
├── config/
│   ├── params.yaml       [x] All tunable parameters
│   └── loader.py         [x] Single YAML read site (load_config)
├── viz.py                [x] Live matplotlib LOB viz (dev tool, subprocess)
├── snapshot.py           [x] Pure LOB-state serialization for viz IPC (dev tool)
├── repl.py               [x] Interactive LOB REPL (dev tool)
├── agents_repl.py        [x] Agent-driven live REPL with viz (dev tool)
tests/                    [x] 141 passing tests (LOB, agents, clock, e2e, tooling)
run_sim.py                [x] Phase 3 entry point
CLAUDE.md                 [x] This file
```

Note: `viz.py`, `snapshot.py`, `repl.py`, `agents_repl.py` are developer tooling
that live at the `sim/` top level, NOT under `analytics/`. They are outside the
phase contracts and are not load-bearing for the simulation itself.

## Build Phases
The project is structured as six incremental phases. Each phase produces a working,
observable experiment before the next adds complexity.

| Phase | Name | Status |
|-------|------|--------|
| 1 | LOB Engine | [x] |
| 2 | Equity Agents + Basic Microstructure | [x] |
| 3 | Equity Market Maker | [x] |
| 4 | Options Pricing + Chain | [ ] |
| 5 | Options Dealer + Delta Hedging | [ ] |
| 6 | Calibration, Analytics, Full Run | [ ] |

**Current position (2026-06-10):** Phases 1–3 complete; all 141 tests pass
(`.venv/bin/python -m pytest tests/ -q`). The Phase 3 Audit backlog has been
**cleared** in a dedicated cleanup commit (see below). Phase 4 (Options Pricing +
Chain) has **not** started — no `options/` package exists yet, but the
correctness blockers that fed into it (vol baseline, MM P&L) are now resolved.

Update the Status column as phases complete.

## Phase 3 Audit (2026-06-09) — Resolved 2026-06-10
A full line-by-line review of every committed `.py` (excluding dev tooling) was
run at the close of Phase 3. Every item below has since been cleared; this
section is kept as a record of what changed and why, not an open backlog.

### Scorecard (out of 10) — post-cleanup
| Dimension | Score | One-line justification |
|-----------|:----:|------------------------|
| **Logical consistency** | **9.0** | equity_mm now matches its spec (rolling-median vol baseline, party-to-fill P&L); dead branches and the dead scheduling API are gone. |
| **Elegant / realistic solutions** | **8.5** | LOB (SortedDict+deque+callback tape), frozen events, and the OU institution remain elegant; the vol no-op round-trip and the `price==0` sentinel have been removed. |
| **Per module** | | |
| `core/lob.py` | 9.0 | Clean price-time priority, in-place partial fills, immutable `Order` + `_with_qty`. Market-order surplus-rest behavior is unusual but documented. |
| `core/events.py` | 9.0 | Frozen dataclasses, good docstrings. Market orders now carry an explicit `is_market` flag (documented), not a `price==0` convention. |
| `core/tape.py` | 9.0 | Tiny, single-purpose, exactly as specced. |
| `core/clock.py` | 9.0 | heapq scheduler + correct fill routing; vol is now computed directly in bps and routing keys on `is_market`. |
| `agents/base.py` | 8.5 | Centralised position tracking; state initialised only in `__init__` (no `dataclasses.field()` on a non-dataclass). |
| `agents/retail.py` | 8.5 | Clean Poisson/geometric noise trader; emits explicit market orders. |
| `agents/institution.py` | 8.5 | Exact OU discretisation, signal-anchored pricing, partial-fill preservation — the most realistic agent. |
| `agents/equity_mm.py` | 8.5 | Spec-aligned vol baseline, correct taker/maker P&L, no-reference-price guard, no dead scheduling API. |
| `analytics/metrics.py` | 9.0 | Pure NumPy, correct, well-edge-cased. |
| `config/loader.py` | 9.0 | Single read site, good errors. |
| `run_sim.py` | 8.0 | Clear wiring; retains the `equity_mm`/`equity_mms` dual-path (see P2-2 below). |

### Resolution log
**P0-1 — vol baseline now matches spec** (`equity_mm.py`). The MM keeps a
`_vol_history` of observed `rolling_vol_bps`; the baseline is the config seed
during warm-up and the **median of all observed readings** once `vol_window` of
them have accumulated. The 2-point `median([baseline, rolling])` blend, the
unreachable `else` branch, and `_vol_initialized` are gone. Code and the
"Vol-Adjusted Spread" contract below now agree.

**P0-2 — MM P&L counts every fill it is party to** (`equity_mm.on_fills`). Cash
flow updates for taker *and* maker fills, signed by whether the MM bought or
sold, so an inventory-skewed marketable quote no longer corrupts `total_pnl`.

**P1-1 — clock vol no-op collapsed** (`clock.py`). Returns are already fractional,
so `rolling_vol_bps = std(returns) * 1e4` directly; the `*mid … /mid` round-trip
is deleted (identical numeric output).

**P1-2 — base.py** initialises `position`/`open_order_ids` only in `__init__`;
the `dataclasses.field()` import/usage on the non-dataclass `Agent` is removed.

**P1-3 — explicit order type.** `Order` carries `is_market: bool = False`
(documented in `events.py`); the Clock routes on `action.is_market`, and Retail
sets it. The `price==0` market-order sentinel no longer drives control flow.

**P1-4 — dead scheduling API removed** (`equity_mm.py`). `schedule_next`,
`next_event_time`, and `_next_event_time` are deleted (the Clock owns
scheduling); the two unit tests that pinned them were removed.

**P1-5 — no-reference-price guard** (`equity_mm.step`). When both `mid` and
`last_fill_price` are None the MM returns `[]` instead of quoting around a 0.0
mid (which produced a negative bid and a LOB `ValueError`).

**P2-1 — Parameters Reference** block below updated to integer ticks.

**P2-2 — `equity_mm`/`equity_mms` shim intentionally retained.** The frozen
`test_e2e_phase2.py` passes config under the singular `equity_mm` key, so
`run_sim.py` still accepts it. The shim cannot be dropped without modifying a
frozen test; revisit only if that test is ever unfrozen.

**P2-3 — duplicate bookkeeping removed.** `equity_mm` no longer re-adds quote
`order_id`s to `open_order_ids`; the Clock is the sole owner.

## Coding Standards

### Language & Libraries
- **Python 3.11+** throughout
- **Core sim**: pure Python + NumPy (no Pandas in the hot path)
- **Options pricing**: SciPy for norm CDF in Black-Scholes
- **Event scheduling**: custom priority queue (heapq) — no SimPy dependency
- **Visualisation**: Matplotlib (post-run), optional Rich for terminal output
- **Testing**: pytest
- **Config**: PyYAML for params.yaml

### Performance Rules
- The LOB matching engine must run in O(log n) per order — use a `SortedDict` (sortedcontainers)
- Agent `act()` methods must never block — all actions return an event list
- No database calls, no file I/O in the simulation hot loop
- Profile before optimising — use `cProfile` on Phase 2 before considering Numba/Cython

### Code Style
- Type hints on all public functions and class methods
- Dataclasses for all data structures (Order, Fill, Quote, Greeks)
- No global mutable state — pass the simulation context explicitly
- All monetary values in integer ticks (avoid float drift in the LOB)
- Docstrings on every class and public method (one-line summary + params)

## Key Domain Concepts

### Limit Order Book (LOB)
- Price-time priority: best price wins; ties broken by arrival order
- Bid side: sorted descending (highest bid = best)
- Ask side: sorted ascending (lowest ask = best)
- A market order sweeps the book until filled or liquidity exhausted
- Partial fills are normal — track remaining quantity on resting orders
- Spread = best_ask - best_bid (must always be ≥ 1 tick)

### Agent Loop
Every simulation step, each agent runs:
1. `perceive(market_state)` → update internal belief
2. `decide()` → choose action (submit/cancel/do nothing)
3. `act()` → return list of Order events to the exchange

Agents are asynchronous — they act on their own schedules (Poisson or fixed interval).

### Black-Scholes Greeks (for options_mm.py)
```
Delta = N(d1)                          # sensitivity to underlying price
Gamma = N'(d1) / (S * σ * √T)         # delta's sensitivity to price
Vega  = S * N'(d1) * √T               # sensitivity to volatility
d1    = [ln(S/K) + (r + σ²/2)*T] / (σ*√T)
d2    = d1 - σ*√T
```

### Delta Hedging Loop (Phase 5 critical path)
After every options fill:
1. Recalculate portfolio delta across all open option positions
2. Compute hedge quantity = -net_delta * lot_size
3. Submit market order to equity LOB to flatten delta
4. This equity trade moves the underlying price
5. Which changes the theoretical option values
6. Which may trigger re-quoting on the options market
→ This feedback loop is the core experiment

## Parameters Reference (params.yaml keys)
> `sim/config/params.yaml` is the single source of truth. The Phase 3 keys below
> mirror the live file (integer ticks, `equity_mms` list). The `options_mm` /
> `options` blocks are **forward-looking** — those keys do not exist yet and land
> with Phase 4/5.
```yaml
# --- live today (Phase 1–3) ---
market:
  tick_size: 1            # integer ticks; no decimal prices in the LOB
  lot_size: 100
  initial_price: 10000    # ticks
  initial_bid_size: 200
  initial_ask_size: 200
  max_steps: 200          # event count, not trading days
  seed: 42
  vol_window: 20          # fills used for rolling-vol (clock + MM baseline)

agents:
  retail:
    n_agents: 10
    arrival_rate: 10.0     # orders per minute (Poisson lambda)
    order_size_mean: 2     # lots
    direction_bias: 0.0    # 0 = perfectly random
  institution:
    arrival_rate: 5.0
    signal_halflife: 30.0  # minutes
    signal_sigma: 1.0
    threshold: 0.0
    position_limit: 500    # lots
    quote_offset_ticks: 1
    scale: 100
    signal_price_scale: 5
  equity_mms:              # list form; each entry has an explicit id
    - id: "mm_aggressive"
      arrival_rate: 100.0
      spread_target: 3     # ticks
      inventory_limit: 2000
      risk_aversion: 0.05
      quote_size: 5
      max_orders_per_side: 1
      vol_window: 20
      vol_multiplier: 2.0
      baseline_vol_bps: 5.0
    - id: "mm_conservative"
      arrival_rate: 100.0
      spread_target: 5
      inventory_limit: 2000
      risk_aversion: 0.1
      quote_size: 5
      max_orders_per_side: 1
      vol_window: 20
      vol_multiplier: 2.0
      baseline_vol_bps: 5.0

# --- forward-looking (Phase 4/5; keys not yet present) ---
agents:
  options_mm:
    vol_estimate: 0.20     # annualised σ for BS pricing
    spread_vols: 2.0       # bid/ask quoted ± 2 vol points
    delta_hedge_threshold: 0.05  # re-hedge if |delta| > 0.05
    gamma_limit: 500

options:
  strikes: [95, 97.5, 100, 102.5, 105]  # relative to spot
  expiries_days: [7, 14, 30]
  risk_free_rate: 0.05
```

## Testing Philosophy
- Phase 1: LOB must pass an exact matching test suite before Phase 2 begins
  - Test: market order fully fills against resting limit orders
  - Test: partial fill leaves correct residual in book
  - Test: price-time priority is respected with two orders at same price
  - Test: cancellation removes order from book, does not affect price
- Phase 3: equity MM must produce a non-zero spread within 100 steps
- Phase 5: delta after hedge must be within threshold of zero

Run all tests after every session: `pytest tests/ -v`

## Session Workflow (how to work with Claude)
1. **State the phase** at the start of every session: "We are working on Phase N"
2. **Paste the failing test or specific error** — don't describe it, paste it
3. **One module at a time** — complete and test one file before moving to the next
4. **After each module**, run: `python -m pytest tests/test_<module>.py -v`
5. **Commit checkpoints** — after each passing module: `git add -A && git commit -m "Phase N: <module> complete"`

## Phase 3 Implementation Contracts

### Vol-Adjusted Spread — units and baseline
- `MarketState` carries `rolling_vol_bps: float | None` (volatility in basis-points, computed from fractional fill-to-fill returns, not raw returns)
- `rolling_vol_bps` is computed in `Clock._build_state()` (`std(returns) * 1e4`), never inside the MM agent
- `Clock.__init__` receives `tape: Tape` explicitly — no global tape access
- `baseline_vol_bps` is a config seed value used during warm-up; once `vol_window` readings have accumulated the baseline switches to the **median of the rolling-vol series so far**
  - ✅ **Resolved (Audit P0-1):** the MM keeps `_vol_history` and takes its median once `len(_vol_history) >= vol_window`; before that it uses the config `baseline_vol_bps`. Code and spec now agree.
- Effective spread formula — **canonical form (matches code + the vol-spread test below):**
  `effective_spread = max(1, int(round(spread_target * (1 + vol_multiplier * (vol_ratio - 1)))))`
  where `vol_ratio = rolling_vol_bps / baseline_vol_bps`.
  - The older `max(min_spread, round(spread_target * vol_ratio))` form (no `vol_multiplier`) is **superseded** — it contradicted the vol-spread test contract and is no longer used. Do not reintroduce it.

### MM Competition — config and IDs
- `params.yaml` key is `equity_mms` (list); each entry has an explicit `id` string field
- MMs must have different `spread_target` values (not just different `risk_aversion`) so undercutting is observable in logs
- Loop: `for mm_cfg in cfg["agents"]["equity_mms"]: agents.append(EquityMarketMaker(mm_cfg["id"], mm_cfg, rng))`
- Phase 2 e2e test (`test_e2e_phase2.py`) is **frozen** — do not modify it. Add `test_e2e_phase3.py` for Phase 3 assertions

### MM P&L — correct decomposition
Track two quantities on `EquityMarketMaker`, updated on every fill:
```
cash_flow += fill.price * fill.qty   # positive for sells, negative for buys
```
Report in summary:
```
inventory_value = position * current_mid
total_pnl = cash_flow + inventory_value
```
Do NOT compute P&L by summing fill prices without sign — that produces cash flow only, not true P&L.
- ✅ **Resolved (Audit P0-2):** `EquityMarketMaker.on_fills` updates `cash_flow` for **every fill the MM is party to** — taker or maker — signed by whether the MM bought (`-price*qty`) or sold (`+price*qty`). A marketable, inventory-skewed quote (MM as taker) is now counted, so `total_pnl` stays correct.

### Vol spread test — config-aware assertion
```python
vol_multiplier = mm_cfg["vol_multiplier"]
expected_min_ratio = 1 + (vol_multiplier - 1) * 0.5
assert new_spread / old_spread >= expected_min_ratio
```
Test must read `vol_multiplier` from the config dict, not hardcode 20%.

## Phase 2 Implementation Contracts

### BBO Bootstrap (run_sim.py, not agents)
`run_sim` places two phantom seed orders before the first agent step:
- Seed BID: `initial_price - 1 tick`, qty = 1 lot, order_id = `"SEED_BID"`
- Seed ASK: `initial_price + 1 tick`, qty = 1 lot, order_id = `"SEED_ASK"`

These are regular resting limit orders, not special-cased objects. The equity MM in Phase 3
will naturally outcompete them and they will age out. Do NOT place seed orders inside any
agent's `__init__` or `act()` — bootstrap logic belongs exclusively in the runner.

### params.yaml is required from Phase 2 onwards
Create `config/params.yaml` at the start of Phase 2. All agents and the clock take a
`config: dict` parameter in their constructors — no magic globals. Load once in `run_sim.py`:
```python
import yaml
with open("config/params.yaml") as f:
    cfg = yaml.safe_load(f)
```
Then pass `cfg["agents"]["retail"]` etc. to each agent constructor. This is the only place
params.yaml is read. Tests pass their own config dicts directly — no file I/O in tests.

### Fill Logging — Central Tape with Callback Hook
`core/tape.py` owns the chronological fill list:
```python
@dataclass
class Tape:
    fills: list[Fill] = field(default_factory=list)
    def append(self, fill: Fill) -> None:
        self.fills.append(fill)
```
`LimitOrderBook.__init__` accepts `on_fill: Callable[[Fill], None] | None = None`.
When a fill is generated during matching, call `if self.on_fill: self.on_fill(fill)`.
The runner wires this at startup: `book = LimitOrderBook(on_fill=tape.append)`.
Existing Phase 1 tests construct `LimitOrderBook()` with no callback — behaviour unchanged.
Analytics layers in Phase 6 may inject additional callbacks without touching LOB or agents.

## Known Design Decisions & Rationale
- **Integer ticks for prices**: avoids floating-point drift corrupting the LOB sort order
- **Poisson arrivals for retail**: standard in market microstructure literature (Glosten-Milgrom)
- **BBO seeded in runner, not agents**: keeps agent logic and tests isolated from bootstrap state
- **params.yaml from Phase 2**: single source of truth; agents take config dicts, never read files
- **Tape via callback, not LOB coupling**: LOB stays pure and testable; runner injects logging
- **Flat vol surface to start**: simplifies Phase 4; surface dynamics added in Phase 6
- **Single options LOB per series deferred**: Phase 4 uses quote-driven market (dealer quotes on request); full options LOB added only if Phase 5 is stable
- **No options-on-options**: scope boundary — this simulator covers equity + vanilla options only

## Stylised Facts to Validate Against
The simulation is only "working" when it reproduces:
- [ ] Positive bid-ask spread at all times
- [ ] Spread widens with volatility (Roll measure)
- [ ] Price impact: large orders move the mid more than small orders
- [ ] Autocorrelation of returns near zero (weak-form efficiency emerges)
- [ ] Volatility clustering (ARCH effects in return series)
- [ ] Fat tails in return distribution (excess kurtosis > 0)
- [ ] Delta of options_mm position near zero after each hedge cycle

## What Claude Should NOT Do
- Do not add libraries not listed above without flagging it first
- Do not refactor working modules during a feature session
- Do not skip writing tests to "save time" — tests are the checkpoint system
- Do not use Pandas DataFrames inside the simulation loop (use NumPy arrays)
- Do not implement Phase N+1 features while Phase N is incomplete
- Do not hardcode prices, rates, or agent parameters — everything goes in params.yaml

## Glossary
| Term | Meaning |
|------|---------|
| LOB | Limit Order Book |
| MM | Market Maker |
| ATM | At-the-money (option strike ≈ current price) |
| BS | Black-Scholes |
| Greeks | Delta, Gamma, Vega, Theta, Rho |
| IV / σ | Implied volatility |
| Tick | Minimum price increment |
| Lot | Standard trading unit (lot_size shares) |
| Fill | A matched trade between two orders |
| Tape | Chronological record of all fills |
| Stylised fact | Empirical regularity observed in real market data |
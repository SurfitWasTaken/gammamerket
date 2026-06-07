# Market Simulator — Claude Project Context

## Project Identity
This is a **closed-loop, multi-agent artificial equity + options market simulator**.
The goal is to generate realistic price dynamics endogenously through agent interactions,
culminating in a full delta/gamma hedging feedback loop between an options dealer and
the underlying equity limit order book.

## Architecture Overview
```
sim/
├── core/
│   ├── lob.py            # Limit order book engine (price-time priority) + inline matching
│   ├── clock.py          # Discrete event scheduler (heapq, Poisson arrivals)
│   ├── tape.py           # Central fill tape (callback-injected into LOB)
│   └── events.py         # Event types: Order, Fill, Cancel
├── agents/
│   ├── base.py           # Agent base class + MarketState snapshot
│   ├── retail.py         # Noise traders (Poisson arrivals, random direction)
│   ├── institution.py    # Mean-reverting speculator (OU signal, target position)
│   ├── equity_mm.py      # [Phase 3] Equity market maker
│   └── options_mm.py     # [Phase 5] Options dealer
├── options/
│   ├── pricer.py         # [Phase 4] Black-Scholes pricing + Greeks
│   ├── surface.py        # [Phase 4] Implied vol surface
│   └── chain.py          # [Phase 4] Options chain
├── analytics/
│   ├── metrics.py        # Pure post-run: returns, autocorrelation, trade sizes
│   ├── logger.py         # [Phase 6] Event tape logger
│   └── viz.py            # [Phase 6] Post-run visualisation
├── config/
│   ├── params.yaml       # All tunable parameters
│   └── loader.py         # YAML loader (single read site)
├── tests/                # Unit tests + e2e
├── run_sim.py            # Entry point
└── CLAUDE.md             # This file
```

## Build Phases
The project is structured as six incremental phases. Each phase produces a working,
observable experiment before the next adds complexity.

| Phase | Name | Status |
|-------|------|--------|
| 1 | LOB Engine | [x] |
| 2 | Equity Agents + Basic Microstructure | [x] |
| 3 | Equity Market Maker | [ ] |
| 4 | Options Pricing + Chain | [ ] |
| 5 | Options Dealer + Delta Hedging | [ ] |
| 6 | Calibration, Analytics, Full Run | [ ] |

Update the Status column as phases complete.

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
```yaml
market:
  tick_size: 0.01
  lot_size: 100
  initial_price: 100.0
  trading_days: 1          # simulation duration

agents:
  retail:
    arrival_rate: 10.0     # orders per minute (Poisson lambda)
    order_size_mean: 1     # lots
    direction_bias: 0.0    # 0 = perfectly random
  institution:
    n_agents: 3
    capital: 1_000_000
    position_limit: 5000   # max shares
    signal_halflife: 30    # minutes
  equity_mm:
    spread_target: 0.04    # $0.04 initial spread
    inventory_limit: 2000
    risk_aversion: 0.1
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

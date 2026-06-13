# Roadmap

Six incremental phases. Each produces a **working, observable experiment**
before the next adds complexity. Status mirrors the table in `CLAUDE.md` — keep
the two in sync.

| Phase | Name | Status | Output you can observe |
|------:|------|:------:|------------------------|
| 1 | LOB Engine | ✅ done | Matching, price-time priority, partial fills |
| 2 | Equity Agents + Microstructure | ✅ done | Retail + institution moving a seeded book |
| 3 | Equity Market Maker | ✅ done | Two competing MMs, vol-adjusted spread, P&L |
| 4 | Options Pricing + Chain | ✅ done | BS prices + Greeks, flat surface, chain |
| 5 | Options Dealer + Delta Hedging | ✅ done | Dealer quotes → hedges → moves equity book |
| 6 | **Calibration, Analytics, Full Run** | 🔶 **in progress** | Live multi-terminal dashboard; stylised facts reproduced end-to-end |

## Where we are
Phases 1–5 are complete. The codebase is clean and **255 tests pass**. Phase 5
shipped the options dealer (`agents/options_mm.py`) and the quote-driven demand
flow (`agents/options_flow.py`), closing the core feedback loop: option fill →
delta recompute → equity market order → underlying moves → re-hedge. The E1–E6
decisions are frozen in CLAUDE.md (Phase 5 Implementation Contracts), and the
e2e contract holds — net delta within `max(threshold, 0.5)` lots of zero after
every hedge cycle. **Phase 6 (Calibration, Analytics, Full Run) is in progress**
— the live multi-terminal dashboard (`sim/live/`) shipped with `Rich`-powered
per-agent dashboards, matplotlib 3D options surface, and macOS Terminal.app
spawning. Stylised facts validation and parameter calibration remain.

## Phase 4 — Options Pricing + Chain  (detailed plan: `PHASE_4_WORKPLAN.md`)
New package `sim/options/`:
- `pricer.py` — Black-Scholes pricing + Greeks (delta, gamma, vega; theta/rho
  optional). Pure functions + a frozen `Greeks` dataclass. SciPy for the
  normal CDF.
- `surface.py` — implied-vol surface; flat (constant σ) to start, behind an
  interface that a dynamic surface can later implement.
- `chain.py` — options chain: strikes × expiries, series management, anchored
  to the live underlying mid.
- Config: add `options` and `agents.options_mm` blocks to `params.yaml`.

**Critical first step:** resolve the unit-conversion decisions (sim-time →
years, integer-tick spot → BS spot, moneyness → integer strikes). These are
load-bearing for every downstream Greek and hedge. They are written up as open
decisions in the workplan — resolve them, record the choice in `CLAUDE.md`, then
code.

## Phase 5 — Options Dealer + Delta Hedging  (detailed plan: `PHASE_5_WORKPLAN.md`)
Shipped `sim/agents/options_mm.py` (dealer: BS quoting, gamma cap, delta
hedging) and `sim/agents/options_flow.py` (Poisson taker driving the
quote-driven options market — no options LOB). After every option fill and at
every dealer step: recompute net delta in lots → `round(-net_delta)` equity
market order → underlying moves → re-hedge. The Clock now owner-routes fills
(`Order.agent_id`) so flow-carried dealer hedges credit the dealer. Test
contract (held, `test_e2e_phase5.py`): **net delta within
`max(delta_hedge_threshold, 0.5)` lots of zero after each hedge cycle** — the
0.5 is the integer-lot quantisation floor (E2).

## Phase 6 — Calibration, Analytics, Full Run
Effective-spread / depth / realized-vol metrics (the Phase 6 additions to
`analytics/`), parameter calibration sweeps, and a full run validated against
the stylised-facts checklist in `GOALS.md`.

## Sync rule
When a phase completes: flip its status here **and** in the `CLAUDE.md` phase
table and architecture tree (mark new modules `[x]`), and update the test count.
A phase is not "done" until CLAUDE.md, this roadmap, and the tests all agree.

# Roadmap

Six incremental phases. Each produces a **working, observable experiment**
before the next adds complexity. Status mirrors the table in `CLAUDE.md` — keep
the two in sync.

| Phase | Name | Status | Output you can observe |
|------:|------|:------:|------------------------|
| 1 | LOB Engine | ✅ done | Matching, price-time priority, partial fills |
| 2 | Equity Agents + Microstructure | ✅ done | Retail + institution moving a seeded book |
| 3 | Equity Market Maker | ✅ done | Two competing MMs, vol-adjusted spread, P&L |
| 4 | **Options Pricing + Chain** | ⬜ **next** | BS prices + Greeks, flat surface, chain |
| 5 | Options Dealer + Delta Hedging | ⬜ | Dealer quotes → hedges → moves equity book |
| 6 | Calibration, Analytics, Full Run | ⬜ | Stylised facts reproduced end-to-end |

## Where we are
Phases 1–3 are complete and the Phase 3 Audit backlog is cleared (commit
`5d5779e`). The codebase is clean, 141 tests pass, and there is no carried-over
tech debt. **Phase 4 is the immediate work** — see `PHASE_4_WORKPLAN.md`.

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

## Phase 5 — Options Dealer + Delta Hedging
`sim/agents/options_mm.py`. The core experiment. After every options fill:
recompute portfolio delta → hedge qty = `-net_delta * lot_size` → submit equity
market order → underlying moves → option values change → re-quote. The Phase 5
test contract: **net delta within threshold of zero after each hedge cycle.**
Prerequisite: a stable, numerically-correct Phase 4 pricer.

## Phase 6 — Calibration, Analytics, Full Run
Effective-spread / depth / realized-vol metrics (the Phase 6 additions to
`analytics/`), parameter calibration sweeps, and a full run validated against
the stylised-facts checklist in `GOALS.md`.

## Sync rule
When a phase completes: flip its status here **and** in the `CLAUDE.md` phase
table and architecture tree (mark new modules `[x]`), and update the test count.
A phase is not "done" until CLAUDE.md, this roadmap, and the tests all agree.

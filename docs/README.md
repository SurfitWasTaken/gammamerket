# gammarket — Operating Docs (Fable handoff)

Welcome, Fable. This folder is your operating layer: **what to build, in what
order, and how you'll know it's done.** It sits on top of — and defers to —
`CLAUDE.md`, which remains the single source of truth for architecture,
coding standards, and the per-phase implementation contracts.

## Read in this order
1. **`../CLAUDE.md`** — project identity, architecture tree, coding standards,
   domain concepts (LOB, BS Greeks, delta-hedging loop), and the frozen
   implementation contracts. **Authoritative.** If anything here disagrees with
   it, CLAUDE.md wins (or fix one to match the other in the same commit).
2. **`GOALS.md`** — the north star and the definition of done (stylised facts).
3. **`ROADMAP.md`** — the six-phase plan and where we are.
4. **`PHASE_4_WORKPLAN.md`** — your immediate work: Options Pricing + Chain.
   Module-by-module specs, the open design decisions you must resolve first,
   and the test plan.
5. **`TODO.md`** — the living checklist. Keep it current as you work.

## Current state (handoff baseline — 2026-06-11)
- **Phases 1–3 complete.** LOB engine, equity agents (retail, institution,
  two competing market makers), discrete-event clock, central tape, metrics.
- **All 141 tests pass:** `.venv/bin/python -m pytest tests/ -q`
- **The Phase 3 Audit backlog is fully cleared** (commit `5d5779e`). The audit
  section in `CLAUDE.md` is now a dated resolution log, not an open backlog.
- **Phase 4 has not started** — no `sim/options/` package exists yet, and
  `params.yaml` has no `options` / `options_mm` blocks yet.

## How to work here (house rules, from CLAUDE.md)
- **One module at a time.** Complete and test a file before starting the next.
- **Tests are the checkpoint system.** After each module:
  `.venv/bin/python -m pytest tests/test_<module>.py -v`
- **Commit checkpoints** after each passing module:
  `git add -A && git commit -m "Phase 4: <module> complete"`
- **No refactoring working modules during a feature session.** If you find
  tech debt, log it (a new "Phase 4 Audit" backlog section, same format as the
  Phase 3 one) and clear it in a dedicated cleanup commit — don't fix inline.
- **`test_e2e_phase2.py` is frozen.** Do not modify it. Add new e2e tests per
  phase (`test_e2e_phase4.py`, etc.).
- **No new libraries without flagging.** Allowed: NumPy, SciPy (norm CDF),
  PyYAML, matplotlib, pytest, sortedcontainers. No Pandas in the hot loop.
- **Integer ticks for all LOB prices.** Options pricing works in float; the
  tick/year/strike conversions are an explicit Phase 4 decision (see workplan).

## Quick commands
```bash
.venv/bin/python -m pytest tests/ -q        # full suite
.venv/bin/python run_sim.py --no-plot       # run the Phase 3 sim, print summary
.venv/bin/python run_sim.py                 # + writes results/phase3.png
```

# Handoff

The roadmap a new owner (human or agent) reads first. Keep this in sync: a new
`specs/NNNN-*` directory should land with an edit here (enforced by the
`handoff-sync` gate).

## What this repo is

InventoryBallast is a portable, solver-neutral securities-lending inventory
optimization engine. It was extracted (2026-09-04) from the `QR-Haven` monorepo's
`projects/inventory_optimizer/` into its own repository, preserving that
directory's original 6 commits via `git subtree split`. It is not yet pushed to a
GitHub remote — it exists as a local repo only, by the owner's choice at
extraction time.

It also adopts the [QuantSmith](https://github.com/joshualutkemuller/QuantSmith)
agentic scaffold (`instructions/`, `hooks/`, `agents/`, `prompts/`, `templates/`,
`CLAUDE.md`) and pins the `quantsmith` package as an optional dependency. See
`CLAUDE.md` for the operating model and `docs/adoption_guide.md`-equivalent
guidance lives in the QuantSmith repo itself (not copied here — see "Open items"
below).

## The actual spec: `specs/spec002/`

The engine's normative specification is [`specs/spec002/`](../specs/spec002/) —
copied over from `QR-Haven` in the same extraction (it was **not** carried by the
`git subtree split`, since it lived outside `projects/inventory_optimizer/` in the
monorepo; it was copied separately and is new, uncommitted-by-QuantSmith content
specific to this engine, not the QuantSmith reference spec). Read in this order,
per `specs/spec002/00_PLAN.md`'s own "Handoff Order":

1. `01_SPEC.md` §4 — boundaries and vocabulary
2. `01_SPEC.md` §7 — target project structure
3. `01_SPEC.md` §9 — data contracts and invariants
4. `01_SPEC.md` §11-12 — LP formulation and elasticity
5. `01_SPEC.md` §15-16 — component/solver interfaces
6. `01_SPEC.md` §13 — scenario semantics
7. `01_SPEC.md` §22 — Bloomberg-enriched realism, source-of-truth rules
8. `01_SPEC.md` §23 — platform integration, agency/prime desk models
9. `EXAMPLES.md` — worked examples and golden-update policy
10. `TRACEABILITY.md` — requirement-to-evidence mapping, phased definition of done

`specs/0001-daily-momentum-signal/` is unrelated — it's QuantSmith's own reference
spec, copied in as a worked example of the SDD chain, not part of InventoryBallast's
scope.

## Current state (verified 2026-09-04)

Per `specs/spec002/00_PLAN.md`'s status line and `TRACEABILITY.md`:

- **Implemented and tested:** T01-T11, T34, and the `securities_lending_inventory`
  baseline of T35 — package scaffold, domain contracts, config, elasticity
  (`elasticity/`), sparse LP formulation (`formulation/`), the baseline LP compiler
  (`formulation/lp.py::compile_lp`), the HiGHS backend (`solvers/highs.py`), the
  independent solution verifier (`validation/solution_verifier.py`), and (as of
  2026-09-04) T11's result/attribution/explainability layer (`reporting/`;
  `specs/0002-result-attribution-explainability/`). 107 tests pass
  (`pytest tests/ -q`, with the `highs` extra installed).
- **Not yet started:** no CLI/facade module exists under `src/inventory_optimizer/`
  yet (confirmed by directory listing) — T12 below is a real gap, not just an
  unmarked completion.

## Environment

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev,highs,dataframe,agentic]"
.venv/bin/python -m pytest tests/ -q   # 107 passed, as of this writing
```

See `README.md`'s "Development" section for the extras breakdown. `.venv/` is
gitignored — recreate it rather than expecting it to be there.

## Next priorities, in order

### T11 — Result, attribution, and explainability (`01_SPEC.md` §18) — done (2026-09-04)

`specs/0002-result-attribution-explainability/` (`spec.md`, `plan.md`,
`tasks.md`) — the first real `NNNN-slug` SDD spec in this repo, shaped with
`agents/optimization/problem_formulation/` and
`agents/optimization/solver_diagnostics_sensitivity/` per the routing table
below. All eleven tasks (`T-001`-`T-011`) are done: the `reporting/` package
(`types.py`, `attribution.py`, `explanations.py`, `shadow_prices.py`,
`result_builder.py`), the thirteen new `domain/results.py` section models, and
10 new tests under `tests/unit/reporting/` (107 total, all passing).

What shipped, per §18: a full `OptimizationResult` assembly
(`reporting.result_builder.build_optimization_result`) covering all fifteen
§18.1 sections (Schedules/Collateral/Sources are explicit `None` — no upstream
domain model exists yet for them); objective attribution
(`reporting.attribution.attribute_objective`) that independently recomputes
each component's unscaled USD value and hard-fails
(`AttributionMismatchError`) if the sum disagrees with the solver's own
claimed objective; decision explanations (`reporting.explanations.explain_routes`)
deriving 3 of the 24 `ReasonCode` values so far (`HIGHER_NET_FEE`,
`DEMAND_CAP_BINDING`, `ELASTICITY_REDUCED_DEMAND`; the remaining 21 wait on
their owning constraint components — see the spec's tasks.md Follow-ups); and
LP shadow prices (`reporting.shadow_prices.build_shadow_prices`), correctly
omitted whenever the backend reports no dual (MIP solves).

`specs/spec002/TRACEABILITY.md` rows `LP-007`, `VER-001`, `VER-002`,
`VER-005`, `VER-006` moved `SPECIFIED` → `IMPLEMENTED`. `LP-008` was
**not** closed — the original spec draft incorrectly listed it; it needs the
joint collateral mode (T32, not started), not just T11, and was corrected in
`spec.md`'s Goals section before merge.

### T12 — Public API and CLI (`01_SPEC.md` §17) — next up

- The stable facade (§17.1): `InventoryOptimizer` class + `load_config(...)`,
  a thin wrapper over the already-implemented validators / elasticity service /
  formulation compiler / solver backend / verifier — plus the not-yet-built
  reporter from T11.
- Service protocols (§17.2): `OptimizationService`, `ScenarioService`,
  `ExplanationService`.
- CLI (§17.3): `inventory-optimizer validate|optimize|scenarios|components|doctor`
  — no `[project.scripts]` entry exists yet in `pyproject.toml` for this (compare
  the QuantSmith scaffold's own `quantsmith-*` console scripts for the pattern).
- Note: §17.4 (QR Haven platform adapter) and §17.5 (platform invocation
  contract) are QR-Haven-side / already-partially-implemented (`platform/`
  package here provides the invocation context); the adapter itself
  (`src/qr_haven/integrations/inventory_optimizer.py`) lives in `QR-Haven`, not
  here, and is out of scope for this repo.

### After T11/T12

`00_PLAN.md`'s "Implementation Sequence" continues with Phase 2 (scenario
engine, T13-T14), Phase 3 (MIP business rules), Phase 4 (QP), Phase 5
(nonlinear/multi-period research), the Bloomberg-enriched realism workstream, and
the agency/prime desk workstream — see that file for exit gates on each.

## Using QuantSmith to build the rest of this repo

Two layers were adopted (see "What this repo is"); both have concrete uses here,
beyond just the constitution/gates already wired into CI.

### The agents (scaffold) — routes almost 1:1 onto the task list above

| Next task | QuantSmith agent |
| --- | --- |
| T11 — shadow prices, solver diagnostics, reason codes | `agents/optimization/solver_diagnostics_sensitivity/` |
| T12 and later phases — turning an ambiguous next decision into variables/constraints/ACs before coding | `agents/optimization/problem_formulation/` |
| Phase 3 — MIP business rules (lot sizes, all-or-none, cardinality) | `agents/optimization/mixed_integer_optimization/` |
| Collateral workstream (T30-T32: haircuts, capacity, joint mode) | `agents/optimization/collateral_margin_optimization/` — named for exactly this problem |
| General LP review as more constraint components get added | `agents/optimization/linear_programming/` |
| Routing the above as work grows | `agents/optimization/optimization_orchestrator/` |
| Writing/keeping the tests that back each new AC | `agents/testing_validation/` |
| Driving each new task through Specify → Plan → Tasks → Implement → Verify → Operate | `agents/workflow_orchestrator/` — invoke this one first; it routes to the rest |

`agents/optimization/inventory_supply_chain/` also exists but is a false-friend
match — it's aimed at physical-goods inventory (safety stock, multi-echelon
replenishment), not securities-lending inventory. Don't route there.

### The `quantsmith` package (the `agentic` extra)

Narrower fit, since `inventory_optimizer` already has its own purpose-built
HiGHS/`CompiledProblem` stack — not a replacement for it. Two places it's
genuinely additive rather than redundant:

- `quantsmith.pipelines.solve_milp` / `solve_lp` as an independent, dependency-free
  reference solver to cross-check results against once Phase 3 (MIP) lands — a
  second implementation is a good input to a `solver_diagnostics_sensitivity`
  review, not something to import into the engine itself.
- `quantsmith.pipelines.DashboardSpec` / `render_streamlit` / `write_xlsx` if a
  quick allocation/economics/utilization dashboard over `OptimizationResult` is
  wanted once T11 exists — same governed-dashboard pattern QuantSmith uses for
  its own examples, no need to hand-roll one.

### How to actually start

**T11 done (2026-09-04)** — see above. Repeat the same "write the spec
first" pattern for T12 next: invoke `workflow_orchestrator`, let it route to
`problem_formulation` for turning §17's `InventoryOptimizer`/`load_config`/
service-protocol/CLI shape into `REQ-*`/`AC-*` rows and `testing_validation`
for the AC tests, and write a real `specs/0003-*` directory (not just prose
here) so it's tracked by the same `spec`/`spec-index` gates T11's spec was.
`reporting.result_builder.build_optimization_result` (T11) is T12's primary
dependency — its facade should call it directly rather than re-deriving any
of the assembly logic.

## Open items for the next agent (not yet resolved)

- **GitHub remote:** none yet. Local commits only. Create when the owner asks.
- **`quantsmith` pin:** `requirements.txt` and `pyproject.toml`'s `agentic` extra
  pin `quantsmith @ git+...@3951654f56c995465b4c090f39eeb34f8c9671ff` — the exact
  `origin/main` commit at adoption time, because QuantSmith has no tagged release
  yet. Re-pin to a tag once one exists.
- **CI not yet run for real:** `.github/workflows/ci.yml` was added and its gate
  commands were dry-run locally (`sh hooks/stages/run-stage.sh ...`, all passing),
  but it has never executed on actual GitHub Actions since there's no remote yet.
  Verify green on first push.
- **Attribution policy: adopted and enforced.** `CLAUDE.md`'s "GitHub posts"
  section says to omit AI attribution footers unconditionally, and CI's `gates`
  job now runs `hooks/stages/agent-attribution-check.sh` **enforced**
  (`QF_STAGE_ENFORCE=1`) — it fails the build if a commit carries an AI
  author/co-author. The commit history was rewritten (`git filter-branch
  --msg-filter`, local-only, never pushed) to strip the `Co-Authored-By: Claude
  Sonnet 5` trailers that earlier commits had; author/committer identity on
  every commit was already the repo owner's own, so only the trailers needed
  removing. Any agent committing here going forward must not add one.
- **`specs/spec002/` cross-references:** the 6,500-line spec set was copied
  verbatim from `QR-Haven` and still describes some things in monorepo terms
  (e.g. "the parent repository", the `qr_haven` platform adapter living
  elsewhere) — that's accurate (the adapter genuinely stays in `QR-Haven`), but
  worth a read-through pass if the spec set itself needs updating for the
  standalone repo's own docs conventions.

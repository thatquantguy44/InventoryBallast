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

- **Implemented and tested:** T01-T10, T34, and the `securities_lending_inventory`
  baseline of T35 — package scaffold, domain contracts, config, elasticity
  (`elasticity/`), sparse LP formulation (`formulation/`), the baseline LP compiler
  (`formulation/lp.py::compile_lp`), the HiGHS backend (`solvers/highs.py`), and the
  independent solution verifier (`validation/solution_verifier.py`). 97 tests pass
  (`pytest tests/ -q`, with the `highs` extra installed).
- **Not yet started:** no `reporting`/`attribution` module and no CLI/facade module
  exist under `src/inventory_optimizer/` yet (confirmed by directory listing) —
  T11 and T12 below are real gaps, not just unmarked completions.

## Next priorities, in order

### T11 — Result, attribution, and explainability (`01_SPEC.md` §18)

Nothing under `src/inventory_optimizer/` currently builds the
`OptimizationResult` reporting layer. Needed, per §18:

- The full `OptimizationResult` shape (§18.1): identity, status, allocations,
  balances, economics, demand, schedules, collateral, desk, sources, constraints,
  solver, verification, warnings, platform — most of the underlying data already
  exists in `CompiledProblem`/`SolverResult`/`verify_solution`'s output; T11 is
  mainly the assembly and shaping layer.
- Objective attribution (§18.2): reconstruct each objective component's unscaled
  USD value from domain allocations; sum must match the verified solver objective
  within tolerance. `components/objective_terms/{fee_revenue,transition_cost}.py`
  already compute these terms for the LP — T11 needs to expose them per-component
  in the result rather than only as compiled coefficients.
- Decision explanations (§18.3): the ~24 reason codes listed there
  (`HIGHER_NET_FEE`, `DEMAND_CAP_BINDING`, `INVENTORY_SCARCE`, ...), derived from
  coefficients/bounds/slacks/deltas — no generated prose.
- Shadow prices (§18.4): report LP duals when the backend provides them and
  verification passes; never label them as MIP shadow prices.
- Traceability rows to close: `LP-007`, `LP-008`, `VER-001` (fully), `VER-002`,
  `VER-005`, `VER-006` in `specs/spec002/TRACEABILITY.md` — all currently
  `SPECIFIED`, not `IMPLEMENTED`.

### T12 — Public API and CLI (`01_SPEC.md` §17)

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
- **Attribution policy conflict, unresolved:** `CLAUDE.md`'s "GitHub posts"
  section (copied from QuantSmith) says to omit AI attribution footers from PR
  descriptions/comments/replies unconditionally, and the copied
  `hooks/stages/agent-attribution-check.sh` gate can enforce "no AI agent as
  author or co-author" on commits. This repo's CI (`gates` job) currently runs
  that gate **advisory only** — it is not enforced — because the assistant that
  did this extraction operates under a standing platform instruction to add
  `Co-Authored-By` trailers to its own commits, which conflicts with this policy.
  Decide: enforce the gate (and require any agent working here to actually drop
  the trailers), or drop the gate/policy to match how commits are actually being
  made. Either way, the local commits made during this extraction/adoption
  (visible in `git log`) still carry `Co-Authored-By: Claude Sonnet 5` trailers
  and were made before this decision was resolved.
- **`specs/spec002/` cross-references:** the 6,500-line spec set was copied
  verbatim from `QR-Haven` and still describes some things in monorepo terms
  (e.g. "the parent repository", the `qr_haven` platform adapter living
  elsewhere) — that's accurate (the adapter genuinely stays in `QR-Haven`), but
  worth a read-through pass if the spec set itself needs updating for the
  standalone repo's own docs conventions.

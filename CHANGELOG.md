# Changelog

## Unreleased

- Phase 0A scaffold: package metadata, configuration loader, E1-vertical domain contracts
  (`SecurityInventory`, `LoanRoute`, `DemandForecast`, `CounterpartyLimit`, `UtilizationPolicy`,
  `OptimizationRequest`), validation/reconciliation, component registry, solver/demand/clock/audit/
  cache ports, and the platform invocation context.
- T06: elasticity service (`elasticity/`) -- constant and semi-log curves, uncertainty haircut and
  hard-cap clipping, `ElasticityConfig` -- golden-checked against `EXAMPLES.md` E2. Added the
  Section 12.2 demand-group fee-consistency reconciliation check.
- T07: sparse formulation infrastructure (`formulation/`) -- `VariableIndex`/`RowIndex`,
  deterministic `build_variable_index`, incremental `RowIndexBuilder`, `SparseBuilder` (COO
  accumulation converted once to CSR), and the real `CompiledProblem`/`ScalingMetadata` shapes from
  Section 16.1. `ports/solver.py` and `components/interfaces.py` now reference `CompiledProblem`/
  `SparseBuilder` directly instead of placeholder `object` types.
- `tests/golden/`: E1 (`test_e1_scarce_name_allocation.py`) and E2
  (`test_e2_fee_elasticity_shock.py`) golden fixtures, matching the target project structure.
- T08: baseline LP compiler (`formulation/lp.py::compile_lp`) plus the constraint components
  (`components/constraints/`) it registers -- `inventory_balance`/`transition_identity`
  (Section 11.3-11.4), `demand_cap` (11.6, wired to T06), `utilization_cap`/`reserve_buffer`
  (11.7, 11.9), `counterparty_limit` (11.8) -- and the objective terms
  (`components/objective_terms/`) `fee_revenue` and `transition_cost` (11.12). Route bounds follow
  a contractual-floor-survives-ineligibility / grandfather-on-ineligible-existing-route rule
  pending schedule-driven unwind (T29). `tests/golden/test_e1_scarce_name_allocation.py` now
  compiles the E1 fixture through `compile_lp` and solves it (via scipy's bundled HiGHS, pending
  the T09 adapter) to the exact expected allocation (`q_A=80, q_B=10, objective=0.0472222222`).
- T09: the real HiGHS backend (`solvers/highs.py::HighsBackend`), sole owner of `highspy` imports.
  Builds a `HighsLp` directly from `CompiledProblem`'s CSR matrix (`kRowwise` format maps straight
  onto scipy's `indptr`/`indices`/`data`), applies the allow-listed `SolverOptions`, and normalizes
  every `HighsModelStatus` to `SolverStatus` -- a limit status is only reported as `FEASIBLE_LIMIT`
  when HiGHS confirms a feasible incumbent, never assumed. LP duals/reduced costs are suppressed
  whenever any column is integer (Section 18.4: MIP shadow prices are a different thing). E1 now
  solves through the real adapter to the exact expected allocation and objective.

`highspy` is installed in this environment as of this entry (was previously documented as a gap).

- T10: independent solution verifier (`validation/solution_verifier.py::verify_solution`,
  requirement VER-001). Recomputes variable-bound, row, and integrality violations plus the
  objective directly from `CompiledProblem` and a `SolverResult` -- deliberately independent of
  `result.status`, so a `FEASIBLE_LIMIT` result with a valid primal still passes. Covered by
  corrupted-solution tests (`tests/unit/test_solution_verifier.py`): each of bound violation, row
  violation, integrality violation, and falsified objective is injected into a real solved E1
  result one at a time and confirmed caught.

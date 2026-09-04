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

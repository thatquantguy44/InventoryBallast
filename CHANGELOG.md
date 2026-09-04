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

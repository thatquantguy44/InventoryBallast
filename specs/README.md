# Specs

Each unit of work lives in its own directory here, following Spec-Driven
Development (see `instructions/spec_driven_development.md`).

```
specs/
  NNNN-short-slug/
    spec.md    # WHAT and WHY  — requirements, acceptance criteria, non-goals
    plan.md    # HOW           — architecture, data contracts, trade-offs
    tasks.md   # WORK          — ordered, traceable, testable tasks
```

- `NNNN` is a zero-padded sequence number; the slug is short kebab-case.
- Start from `templates/spec/`.
- The `spec` gate (`hooks/stages/spec-check.sh`) validates the chain and
  traceability across these directories; the `spec-index` gate
  (`hooks/stages/spec-index-check.sh`) checks that every `specs/NNNN-*` directory
  is listed below.

## Index

| ID | Feature | Status |
| --- | --- | --- |
| [0001-daily-momentum-signal](0001-daily-momentum-signal/) | Reference spec copied from QuantSmith — a worked, fully traceable example. Not part of InventoryBallast's own scope. | Reference |
| [0002-result-attribution-explainability](0002-result-attribution-explainability/) | T11 (`spec002/01_SPEC.md` §18): `OptimizationResult` assembly, objective attribution, decision explanations, shadow prices. Closes `TRACEABILITY.md` rows `LP-007`, `VER-001`, `VER-002`, `VER-005`, `VER-006` (`LP-008` stays open — needs T32). | Implemented |
| [0003-public-api-cli](0003-public-api-cli/) | T12 (`spec002/01_SPEC.md` §17): `InventoryOptimizer` facade, `load_config`, `OptimizationService`/`ExplanationService`, and the `inventory-optimizer` CLI. Adds an evidence pointer to `TRACEABILITY.md`'s `PLT-002` row (stays `SPECIFIED` — its `G2C` gate is a cross-cutting platform-ownership approval this repo does not grant unilaterally). | Implemented |
| [0004-scenario-engine](0004-scenario-engine/) | T13-T14 (`spec002/01_SPEC.md` §13): typed trade events, rate/demand shocks, `apply_scenario`/`run_scenario(s)`, `ScenarioComparison`, `ScenarioService`, a real `scenarios` CLI subcommand, and an additive "basic stress testing" capability (`run_stress_test`, not part of `01_SPEC.md`'s own text). Closes `TRACEABILITY.md` rows `SCN-001`–`SCN-003` (`SCN-004` stays open — needs T40). | Implemented |
| [0005-test-hardening](0005-test-hardening/) | Closes gaps found auditing `spec002/01_SPEC.md` §24 ("Testing Strategy") against the actual test suite: `hypothesis`-based property tests (§24.2, previously unused despite being a pinned dependency), dedicated `InventoryBalanceConstraint`/`TransitionIdentityConstraint` unit tests, an existing-loan-churn golden case (§24.5), a utilization-floor-exceeds-cap infeasibility case (§24.6), and a Core-desk-scale benchmark smoke test (§24.8, `slow`-marked). Strengthens `TRACEABILITY.md`'s `DOM-002`/`LP-002` evidence. | Implemented |
| [spec002](spec002/) | The normative specification for `src/inventory_optimizer` (not `NNNN-slug` form — copied from `QR-Haven` pre-dating this repo's spec-driven adoption; see `00_PLAN.md`/`TRACEABILITY.md` for its own phased status). | Living/reference |

InventoryBallast's own specs (the securities-lending inventory optimization
engine under `src/inventory_optimizer`) predate this adoption and were built
without the spec-driven scaffold — see `docs/handoff.md` for the plan to
backfill traceable `NNNN-slug` specs (like `0002-*` above) for each remaining
gap in `spec002/00_PLAN.md`'s implementation sequence.

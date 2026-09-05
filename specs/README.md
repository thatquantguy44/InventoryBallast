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
| [0002-result-attribution-explainability](0002-result-attribution-explainability/) | T11 (`spec002/01_SPEC.md` §18): `OptimizationResult` assembly, objective attribution, decision explanations, shadow prices. Closes `TRACEABILITY.md` rows `LP-007`, `LP-008`, `VER-001`, `VER-002`, `VER-005`, `VER-006`. | Draft |
| [spec002](spec002/) | The normative specification for `src/inventory_optimizer` (not `NNNN-slug` form — copied from `QR-Haven` pre-dating this repo's spec-driven adoption; see `00_PLAN.md`/`TRACEABILITY.md` for its own phased status). | Living/reference |

InventoryBallast's own specs (the securities-lending inventory optimization
engine under `src/inventory_optimizer`) predate this adoption and were built
without the spec-driven scaffold — see `docs/handoff.md` for the plan to
backfill traceable `NNNN-slug` specs (like `0002-*` above) for each remaining
gap in `spec002/00_PLAN.md`'s implementation sequence.

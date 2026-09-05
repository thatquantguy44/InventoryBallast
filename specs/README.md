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

InventoryBallast's own specs (the securities-lending inventory optimization
engine under `src/inventory_optimizer`) predate this adoption and were built
without the spec-driven scaffold — see `HANDOFF.md` for the plan to backfill
a spec for the existing engine and for the next spec to write going forward.

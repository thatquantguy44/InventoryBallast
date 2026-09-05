# Spec002 Plan: Platform-Integrated, Standalone Inventory Optimization Engine

## Status

- **Branch:** `inv_optimizer`
- **Artifact type:** implementation specification and engineering handoff
- **Implementation status:** Phase 0/1 in progress. T01-T10, T34, and the `securities_lending_inventory`
  baseline of T35 are implemented and tested (`projects/inventory_optimizer/`); `highspy` is
  installed and E1 compiles, solves, and independently verifies to its exact expected allocation.
  T11 (result/attribution) and T12 (public API/CLI) remain. See `TRACEABILITY.md` for the
  requirement-level status.
- **Primary solver:** HiGHS through `highspy`
- **First formulation:** continuous linear program (LP)

## Objective

Design a production-minded inventory optimization project for securities lending. The engine must
balance total lendable inventory against existing and proposed on-loan quantities, select the most
valuable allocations, and explain the effect of fee rates, utilization policy, demand elasticity,
and hypothetical trades.

The implementation is intentionally specified as a self-contained project under
`projects/inventory_optimizer/`, initially hosted and invoked by the existing QR Haven platform.
It owns its modules, configuration, contracts, services, tests, version, and release manifest. Its
core package must not import `qr_haven`, so it can later be moved to a dedicated repository without
redesigning the model or platform contract. QR Haven integration is a required platform-owned
adapter, not a core dependency.

## Locked Design Decisions

1. **Post-state allocation is the decision.** The main variable is the desired on-loan quantity for
   each eligible inventory/borrower route after optimization.
2. **LP first.** V0 treats fee rates as inputs and uses an elasticity model to turn fee assumptions
   into demand limits.
3. **HiGHS first, solver-neutral core.** HiGHS owns LP and MIP execution. Solver protocols leave
   room for continuous QP and optional nonlinear backends without leaking backend APIs into the
   domain model.
4. **No hidden inventory arithmetic.** `total_lendable`, `on_loan`, `reserved`, and
   `available_to_lend` have separate canonical definitions and must reconcile for every pool and
   security.
5. **Scenarios are immutable overlays.** Proposed buys, sells, transfers, recalls, returns, rate
   shocks, and demand shocks never mutate the baseline snapshot.
6. **Policies are configuration, not branches in the service layer.** Objective terms and
   constraints are registered components selected by validated configuration.
7. **Every answer is explainable.** A successful result includes allocation deltas, binding
   constraints, objective attribution, balance reconciliation, and solver diagnostics.
8. **No silent repair.** If a strict model is infeasible, any relaxation pass is explicit, ranked,
   and reported in the result.
9. **Vendor enrichment is not a book of record.** Bloomberg-derived identity, market, entity,
   corporate-action, event, holdings, and liquidity data enriches the model through adapters;
   internal inventory, loan terms, legal eligibility, and limits remain authoritative.
10. **Schedules are executable policy.** Eligibility, collateral, fee, term, settlement, event, and
    other constraint schedules are approved, bitemporal, deterministically resolved, and traceable
    into model bounds/rows. No universal haircut or eligibility default is hard-coded.
11. **Platform-integrated, module-owned.** QR Haven initially owns invocation, identity,
    authorization, upstream connectivity, persistence, and presentation. The optimizer owns its
    decision pipeline and canonical result, and remains independently testable and extractable.
12. **Desk modes are problem families.** Agency lending and prime inventory financing are opt-in
    registered families over the same verified kernel, not service-layer conditionals.

## Scope

### V0 must deliver

- A portable Python package and its own configuration tree.
- Typed input and output contracts.
- Point-in-time inventory reconciliation.
- Existing-loan retention, recall, and new-allocation decisions.
- Net lending economics based on fee revenue and configurable costs.
- Utilization targets, floors, caps, and reserve requirements.
- Demand limits adjusted by price elasticity.
- What-if trades and market/policy shocks.
- Sparse LP construction and solving with HiGHS.
- Optional MIP features for discrete business rules.
- Solver interfaces for later QP and nonlinear formulations.
- Deterministic diagnostics, audit records, and tests.
- Point-in-time lineage and adapter ports for Bloomberg or equivalent reference-data enrichment.
- Effective-dated eligibility schedule resolution with deny, grandfather, recall-only, and review
  semantics.
- Collateral schedule validation and optional capacity/joint-allocation extension paths.
- A QR Haven platform adapter and invocation contract with correlation, authorization, schema, and
  idempotency references.
- Registered extension paths for agency beneficial-owner allocation and prime inventory sourcing.

### Deferred extensions

- Intraday event streaming and order placement.
- Joint continuous optimization of fee and quantity.
- Multi-period stochastic optimization.
- Cross-currency collateral optimization.
- A dedicated optimizer UI or hosted service; the existing platform may expose the module through
  its current UI/API/job facilities.
- Broker, custodian, or market-data connectivity beyond adapter interfaces.

## Proposed Deliverables

| Deliverable | Purpose |
| --- | --- |
| `specs/spec002/00_PLAN.md` | Scope, decisions, sequence, and handoff map. |
| `specs/spec002/01_SPEC.md` | Full product, architecture, model, API, test, and operations specification. |
| `specs/spec002/ROADMAPS.md` | Coordinated release, model, data, engineering, validation, and integration roadmaps. |
| `specs/spec002/DICTIONARY.md` | Canonical business, data, mathematical, status, unit, and reason-code vocabulary. |
| `specs/spec002/WHITEPAPER.md` | Self-contained technical rationale and model narrative with research references. |
| `specs/spec002/EXAMPLES.md` | Deterministic worked examples and future golden-fixture expectations. |
| `specs/spec002/TRACEABILITY.md` | Requirements mapped to modules, configuration, evidence, tasks, releases, and gates. |
| `specs/spec002/OPERATIONAL_RUNBOOK.md` | Deployment, on-call, and incident procedures once implementation exists (placeholder; not yet written). |
| `projects/inventory_optimizer/` | Future self-contained implementation root. |
| `projects/inventory_optimizer/src/inventory_optimizer/` | Portable core package. |
| `projects/inventory_optimizer/tests/` | Unit, integration, golden, property, and performance tests. |
| `src/qr_haven/integrations/inventory_optimizer.py` | Initial platform-owned QR Haven adapter. |

This change creates only the specification artifacts. The implementation tree is a target described
by the Spec002 document set, not part of this handoff change.

## Implementation Sequence

### Phase 0 — Scaffold and contracts

1. Create the nested project, package metadata, dependency groups, and configuration tree.
2. Implement domain value objects, enums, request/result contracts, and validation errors.
3. Add unit/quantity conventions and point-in-time snapshot validation.
4. Add registry decorators and backend protocols without concrete business logic.
5. Add common schedule envelopes, authority/precedence policy, and synthetic schedule fixtures.
6. Add the platform invocation context, adapter contract, and in-process/serialized equivalence
   fixtures without importing QR Haven into the core.

**Exit gate:** contracts serialize deterministically, invalid units/balances fail early, and the core
package imports without QR Haven.

### Phase 1 — Baseline LP

1. Normalize inventory, loans, candidate routes, fees, and demand.
2. Apply elasticity to produce exogenous route or demand-group caps.
3. Resolve eligibility, collateral, fee, term, and other applicable schedules into route bounds and
   named constraint inputs.
4. Build sparse variables, constraints, and objective coefficients.
5. Implement the HiGHS LP backend and normalized status mapping.
6. Verify the returned solution independently of the solver.
7. Produce allocation, inventory-balance, utilization, economics, and diagnostics outputs.
8. Invoke the vertical slice through the QR Haven platform adapter and prove canonical result
   equivalence with a direct facade call.

**Exit gate:** deterministic golden cases pass and every pool/security balance reconciles within the
configured tolerance.

### Phase 2 — Scenario engine

1. Implement typed trade and market/policy overlays.
2. Add baseline-versus-scenario comparison and incremental P&L attribution.
3. Add batch execution with safe model reuse or warm starts where supported.
4. Add infeasible sell/transfer diagnostics and required-recall explanations.
5. Add eligibility-schedule version and collateral valuation/haircut/capacity stress overlays.

**Exit gate:** scenario inputs do not mutate the baseline and comparisons reconcile to each
individual result.

### Phase 3 — MIP business rules

1. Add lot sizes, minimum tickets, all-or-none requests, route activation, and cardinality.
2. Add discrete rate-ladder selection for optional price recommendations.
3. Configure time limits, relative gaps, and acceptable incumbent policy.
4. Test both proven-optimal and time-limited feasible outcomes.

**Exit gate:** integrality is verified after solve; a time-limited incumbent is never labeled
optimal.

### Phase 4 — QP and advanced objective terms

1. Add convex concentration, allocation-stability, and correlated risk penalties.
2. Add a QP-capable backend behind the same solver interface.
3. Add positive-semidefinite validation and scaling tests.

**Exit gate:** the LP remains the default and QP behavior is capability-gated and regression-tested.

### Phase 5 — Nonlinear and multi-period research

1. Add joint fee/quantity demand curves through an optional nonlinear backend or sequential convex
   approximation.
2. Add multi-period settlement and scenario-tree extensions.
3. Promote an extension only after benchmark, convergence, and fallback behavior are documented.

### Bloomberg-enriched realism workstream

1. Add bitemporal security mastering, vendor field mapping, freshness, and reconciliation controls.
2. Incorporate settlement calendars, security status, and corporate-action timing into bounds and
   scenarios.
3. Aggregate exposure through internally approved legal-entity hierarchies.
4. Replace contractual revenue with explainable expected revenue using take-up, survival, repricing,
   return/recall, and settlement-risk estimates.
5. Add dynamic liquidity buffers and piecewise-linear unwind/recall costs using approved market and
   liquidity inputs calibrated to internal outcomes.
6. Promote censoring-aware elasticity, robust scenarios, multi-period balances, and transformation
   graphs only after the baseline LP is validated.

**Exit gate:** all vendor-derived inputs retain observed/effective timestamps and lineage; no
licensed field name enters core model code; point-in-time tests prevent look-ahead; and internal
books, contracts, eligibility, and limits remain the source of truth.

### Agency and prime desk workstream

1. Register `agency_lending` and `prime_inventory_financing` beside the baseline problem family.
2. Add owner mandates, owner-partitioned balances, fee splits, indemnification, fairness,
   exclusives, voting/recall policy, and owner attribution for agency desks.
3. Add owned/client-reuse/affiliate/external inventory sources, client-short demand, external
   quotes, internalization, funding/capital limits, and source attribution for prime desks.
4. Add desk-specific scenarios and independent owner/source/client verifiers.
5. Enable MIP, QP, multi-period, or continuous pricing features only when the selected desk rule
   requires them and their validation gate passes.

**Exit gate:** the baseline family is unchanged when desk profiles are disabled; agency inventory
never commingles without authority; prime sources and required client coverage conserve exactly;
and every desk-specific cost and constraint is attributable.

## Workstream Dependencies

```text
contracts + units + config
          |
          v
normalization + bitemporal schedule resolution + elasticity
          |
          v
LP formulation --> HiGHS backend --> independent verifier --> reporting
          |                                   |
          +------------> agency/prime problem families
          |
          +------------> scenario overlays <--+
          |
          +------------> MIP extensions (including discrete collateral rules)
          |
          +------------> QP/NLP and multi-period extensions
```

## Acceptance Summary

The first implementation is ready for use when it can:

- reproduce a supplied baseline snapshot without losing or creating shares;
- prefer higher net-fee allocations when all other terms are equal;
- respect reserves, route eligibility, demand, utilization, and counterparty limits;
- resolve eligibility and collateral schedules deterministically and trace every derived bound/row;
- show the recall or opportunity cost of a proposed sale;
- reduce elasticity-adjusted demand when the configured fee increases for a positive elasticity;
- distinguish optimal, feasible/time-limited, infeasible, unbounded, invalid, and solver-error states;
- reconstruct every reported objective component from the returned allocations;
- run its unit and golden test suite without network access;
- integrate into QR Haven through a one-way adapter without surrendering optimizer module
  ownership or canonical validation/verification;
- reconcile agency mode by beneficial owner and prime mode by inventory source/client demand when
  those profiles are enabled;
- be copied out of QR Haven without changing imports in `inventory_optimizer` core modules; and
- use Bloomberg-enriched values through versioned, entitlement-aware adapters without changing the
  canonical inventory balance or creating backtest look-ahead.

## Handoff Order

An implementing engineer should read `01_SPEC.md` in this order:

1. Boundaries and vocabulary.
2. Target project structure.
3. Data contracts and invariants.
4. LP formulation and elasticity behavior.
5. Solver and component interfaces.
6. Scenario semantics.
7. Bloomberg-enriched realism and source-of-truth rules.
8. Platform integration and agency/prime desk operating models.
9. Worked examples and golden-update policy.
10. Requirements traceability, verification, testing, and phased definition of done.

Where the spec offers an extension and a V0 rule, the V0 rule is authoritative until a later
decision record changes it.

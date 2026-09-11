# Engine Spec Requirements Traceability Matrix

## Purpose

This document maps the Engine Spec requirements to the modules, configuration, evidence, implementation
tasks, releases, and approval gates that satisfy them. It is the handoff control connecting
`01_SPEC.md`, `EXAMPLES.md`, `ROADMAPS.md`, tests, and future code.

The matrix describes planned evidence until implementation exists. A requirement is complete only
when its referenced implementation and automated evidence exist and its required gate is approved.
Checking a documentation box alone does not satisfy it.

---

## Status Vocabulary

| Status | Meaning |
| --- | --- |
| `SPECIFIED` | Normative behavior is documented, but implementation evidence does not yet exist |
| `IMPLEMENTED` | Code exists and focused tests pass |
| `VERIFIED` | Independent/golden/integration evidence passes for the intended release |
| `APPROVED` | Required business/control/model/deployment gate is recorded |
| `DEFERRED` | Explicitly outside the current release with a documented dependency |

All rows in this initial matrix are `SPECIFIED` unless an implementation change updates the status
and links concrete evidence.

---

## Requirement ID Scheme

| Prefix | Domain |
| --- | --- |
| `ARC` | Architecture, modularity, and portability |
| `CFG` | Configuration and component registration |
| `DOM` | Domain contracts, units, and validation |
| `LP` | Baseline mathematical formulation and economics |
| `SCH` | Eligibility and other executable schedules |
| `COL` | Collateral schedules and allocation |
| `SCN` | Scenarios and timing |
| `MPS` | Multi-period settlement (deterministic projection and joint LP) |
| `SOL` | Solver adapters and statuses |
| `VER` | Independent verification, repair, and explanation |
| `DAT` | Bloomberg/reference data and point-in-time correctness |
| `PLT` | Existing-platform integration |
| `AGY` | Agency-lending problem family |
| `PRM` | Prime-inventory-financing problem family |
| `GOV` | Governance, audit, security, and release control |

---

## Core Architecture and Configuration

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ARC-001 | Optimizer is a module-owned subsystem initially integrated into QR Haven | 4.3, 17.4, 23.5 | public facade plus QR Haven-owned adapter | invocation context | E9; dependency tests | T17, T34 / R0-R1 / G2C | `SPECIFIED` |
| ARC-002 | Core never imports QR Haven, vendor clients, web frameworks, or platform models | 4.1-4.3, 7.1 | package/import boundary | dependency groups | import and portability tests | T01, T17 / R0 / G2C | `SPECIFIED` |
| ARC-003 | Project directory remains independently installable and extractable | 4.3, 7 | packaging and portability script | build metadata | `scripts/verify_portability.py`; `tests/test_portability.py` | T01 / R0, R8 / G8 | `IMPLEMENTED` |
| ARC-004 | Domain, schedules, formulation, solver, scenarios, services, reporting, and adapters remain separated | 7.1 | package layer boundaries | component manifest | `adapters` layer only: `tests/unit/test_architecture_boundaries.py` (`specs/0008-tabular-result-output/`) -- `adapters/*` imports nothing from `formulation`/`solvers`/`services`/`scenarios`/`components`/`validation`/`config`, and `pandas` is imported only by `adapters/dataframe.py` | T01, T05 / R0 / M0 | `SPECIFIED` (the `adapters` layer's own boundary is now tested; the full pairwise matrix across every other layer in Section 7.1's ownership table is not -- tracked as a follow-up in `specs/0008-tabular-result-output/tasks.md`) |
| ARC-005 | Advanced problem families reuse verified kernel without weakening its invariants | 4.4, 14.5, 23.1 | problem-family registry | desk profile | family-isolation regression | T35 / R0, D1-D2 / G2D-G2E | `SPECIFIED` |
| CFG-001 | Configuration merge order is deterministic and unknown keys fail | 8.1, 8.4 | config loader/hashing | all YAML layers | `tests/unit/test_config.py` | T02 / R0 | `IMPLEMENTED` |
| CFG-002 | Final config is frozen, validated, redacted, and hashed | 8.1-8.2 | config models/hashing | environment/run config | serialization/hash tests | T02 / R0 | `SPECIFIED` (frozen/validated/hashed done; no config field is sensitive yet, so redaction is undesigned) |
| CFG-003 | Component/problem-family registration is versioned and duplicate-safe | 15, 23.1 | decorators/registry | component manifest | `tests/unit/test_registry.py` | T05, T35 / R0 | `IMPLEMENTED` |
| CFG-004 | Desk profile declares required/optional components and capabilities | 8.5, 23.1 | desk profile service | `inventory_core`, `agency`, `prime` | missing/mismatch tests | T35 / R0 | `SPECIFIED` |

---

## Domain, LP, and Economics

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DOM-001 | Canonical units are shares, USD/share, annual decimals, and explicit day count | 5.2, 9.8 | domain values/validation | unit policy | `tests/unit/test_domain_contracts.py` | T03-T04 / R0 / G0 | `IMPLEMENTED` |
| DOM-002 | Total lendable includes on-loan; available reconciles exactly | 5.1, 9.2 | inventory/reconciliation | supply convention | E1 (`tests/golden/test_e1_scarce_name_allocation.py`); `test_domain_contracts.py`, `test_validation.py`; E3 scenario evidence (`tests/golden/test_e3_sale_and_recall_scenario.py`, T13) | T03-T04 / R0 / G0 | `IMPLEMENTED` |
| DOM-003 | Current route totals reconcile to inventory on-loan | 9.3, 9.8 | loan validation | route snapshot | `tests/unit/test_validation.py::test_aggregates_every_independent_issue_in_one_pass` and related | T04 / R0 | `IMPLEMENTED` |
| DOM-004 | Invalid inputs return aggregated structured issues | 9.8 | input validation/exceptions | validation policy | `tests/unit/test_validation.py` | T04 / R0 | `IMPLEMENTED` |
| LP-001 | Post-state route quantity is the primary allocation decision | 11.3 | variables/indexes | formulation LP | E1 (`tests/golden/test_e1_scarce_name_allocation.py::test_e1_compiles_and_solves_to_expected_allocation`) | T07-T08 / R1 | `IMPLEMENTED` |
| LP-002 | Inventory equality conserves every pool/security | 11.4 | inventory-balance component | inventory inputs | E1 solved and independently verified (`tests/unit/test_solution_verifier.py`); dedicated row-formula unit test (`tests/unit/test_lp_compiler.py::test_inventory_balance_row_matches_hand_formula`) and a Section 24.2 conservation property test across randomized inputs (`tests/property/test_lp_properties.py::test_conservation_and_non_negativity`) | T08, T10 / R1 | `IMPLEMENTED` |
| LP-003 | Route bounds enforce contract, eligibility, timing, and capacity | 11.5 | route-bound compiler | routes/schedules | E3-E4 | T08, T29, T33 / R1-R3 | `SPECIFIED` |
| LP-004 | Demand groups impose post-state elasticity-adjusted caps | 11.6, 12 | elasticity/demand component | curve and forecasts | E2 (`tests/golden/test_e2_fee_elasticity_shock.py`; `tests/unit/test_lp_compiler.py::test_demand_cap_uses_elasticity_adjusted_value`). Discrete per-candidate-fee evaluation (Section 12.4's `D_gk = D_g(f_gk)`, the same unchanged `evaluate_demand_cap` called once per tier instead of once per group; `specs/0009-discrete-fee-tier-pricing/`): `tests/golden/test_fee_tier_pricing.py`, `tests/unit/test_fee_tier_compiler.py::test_tier_rows_match_hand_formula` | T06, T08, T15 / R1 / G0 | `IMPLEMENTED` |
| LP-005 | Utilization floors/caps/reserves are hard only when approved | 11.7, 11.9 | utilization/reserve components | policy config | E1; `tests/unit/test_lp_compiler.py` | T08 / R1 / G1 | `IMPLEMENTED` (gate G1 business approval still outstanding) |
| LP-006 | Counterparty/entity/concentration limits use approved aggregation | 11.8, 22.9 | counterparty/concentration | limits/entity map | aggregation fixtures | T08, T22 / R1-R3 / G1 | `SPECIFIED` |
| LP-007 | Objective values fee, share, reinvestment, variable and transition economics in USD | 11.12 | objective components | objective profile | E1; `tests/unit/reporting/test_attribution.py` (`fee_revenue`/`transition_cost` attribution, reconciled to the solver objective) | T08, T11 / R1 / G0 | `IMPLEMENTED` (fee/revenue-share/variable/transition only; reinvestment has no objective term yet -- E7 evidence still pending its own component) |
| LP-008 | Joint collateral income cannot duplicate route reinvestment income | 11.11-11.12 | reinvestment attribution | collateral mode | E5; attribution test | T11, T32 / R3-R4 | `SPECIFIED` (unchanged: this requires the joint collateral mode itself, T32, which has not started; T11 only supplies the reconciliation pattern (`reporting.attribution.attribute_objective`) T32 will extend to a collateral/reinvestment term) |
| LP-009 | MIP/QP/PWL/NLP features are explicit and capability-gated | 14, 16 | formulation/backend adapters | formulation mode | MIP portion (`all_or_none`, minimum-ticket, lot-size, cardinality; `formulation/mip.py`, `components/constraints/mip_rules.py`): `tests/golden/test_mip_business_rules.py`, `tests/unit/test_mip_compiler.py` (`specs/0006-mip-business-rules/`). QP portion (allocation-stability convex penalty; `formulation/qp.py`, `components/objective_terms/allocation_stability.py`, `formulation/qp_support.py`): `tests/golden/test_qp_allocation_stability.py`, `tests/unit/test_qp_compiler.py`, `tests/unit/test_qp_support.py`, `tests/benchmark/test_qp_scale.py` (`specs/0007-qp-allocation-stability/`). Discrete fee-tier pricing portion (Section 12.4's discrete price-selection MIP -- binary tier selection `z_gk`/`"t"`, per-route-per-tier quantity `w_jk`/`"w"`, closing Phase 3's own deferred rate-ladder item and Section 14.1's seventh MIP trigger; `formulation/mip.py`, `components/constraints/fee_tiers.py`, `components/objective_terms/tier_pricing.py`): `tests/golden/test_fee_tier_pricing.py`, `tests/unit/test_fee_tier_compiler.py`, `tests/benchmark/test_fee_tier_scale.py` (`specs/0009-discrete-fee-tier-pricing/`) | T15, T18 / R4-R7 / G4-G7 | `IMPLEMENTED` (MIP business rules, the allocation-stability QP term, and Section 12.4's discrete fee-tier pricing MIP; PWL/NLP -- Section 14.3-14.4's continuous-fee case -- remain `SPECIFIED`, tagged T18 and later; QP's other three candidate terms -- concentration, covariance-weighted risk, utilization-target deviation -- also remain `SPECIFIED`, each needing a new domain concept not yet grounded) |

---

## Schedules, Collateral, and Scenarios

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SCH-001 | Schedules retain immutable version, observed/effective time, owner, approval, rules, and lineage | 9.6 | schedule contracts | schedule config | serialization/no-look-ahead tests | T19, T29 / R0-R3 / G2A | `SPECIFIED` |
| SCH-002 | Deny/review safety, authority, specificity, priority, and hard-limit intersection resolve deterministically | 9.6, 11.10 | resolver/precedence | precedence config | E4; permutation tests | T29 / R3 / G2A | `SPECIFIED` |
| SCH-003 | `ALLOW`, `DENY`, `GRANDFATHER`, `RECALL_ONLY`, and `REVIEW` compile into traceable bounds | 9.6, 11.10 | eligibility compiler | eligibility schedules | E4; action tests | T29 / R3 / G2A | `SPECIFIED` |
| SCH-004 | Fee, term, event, voting, settlement, and operating rules compile rather than hide in services | 11.10, 22.16 | schedule-limit components | constraint schedules | component/lineage tests | T33 / R3 / G1-G2A | `SPECIFIED` |
| COL-001 | Validate-only mode confirms route/schedule compatibility, valuation, and coverage | 11.11 | collateral validator | collateral config | invalid compatibility fixtures | T30 / R3 / G2B | `SPECIFIED` |
| COL-002 | Capacity mode limits exposure by margin-adjusted collateral credit | 11.11 | collateral-capacity component | capacity/schedule | E5A | T31 / R3 / G2B | `SPECIFIED` |
| COL-003 | Joint mode conserves collateral and enforces haircut coverage | 11.11 | joint collateral variables/rows | joint mode | E5B | T32 / R4 / G2B | `SPECIFIED` |
| COL-004 | Concentration and wrong-way exclusions are explicit and verified | 9.6, 11.11 | collateral rows/pair generation | collateral schedule | E5B; exclusion tests | T30-T32 / R3-R4 / G2B | `SPECIFIED` |
| SCN-001 | Scenario overlays never mutate the baseline | 13 | scenario apply/runner | scenario config | E2, E3; `tests/unit/test_scenarios_apply.py::test_apply_scenario_never_mutates_baseline`, `tests/golden/test_e2_rate_shock_scenario.py::test_baseline_request_unchanged_after_scenario` | T13-T14 / R2 | `IMPLEMENTED` (E4's schedule-overlay portion not attempted — no schedule subsystem exists yet, T29) |
| SCN-002 | Trades alter supply only when effective, settled, and eligible | 13.2-13.3 | trade overlays/calendars | trade events | E3; `tests/golden/test_e3_sale_and_recall_scenario.py`, `tests/unit/test_scenarios_apply.py::test_event_after_effective_date_is_not_applied` | T13, T21 / R2-R3 | `IMPLEMENTED` (calendar/holiday-aware settlement timing, `T21`, not attempted — plain `effective_date` comparison only) |
| SCN-003 | Batch and isolated scenarios are equivalent | 13.4 | scenario runner | batch config | E2; `tests/unit/test_scenarios_runner.py::test_batch_matches_isolated_runs` | T14 / R2 | `IMPLEMENTED` |
| SCN-004 | Desk events are typed and allowed only for the selected family | 13.1, 23.6 | desk scenario overlays | desk events | agency/prime scenario tests | T40 / D1-D2 | `SPECIFIED` |

---

## Solver, Verification, and Results

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| SOL-001 | HiGHS is isolated behind a solver-neutral protocol | 16.2-16.4 | solver protocol/HiGHS adapter | solver config | `tests/unit/test_highs_backend.py`; E1 solved via `HighsBackend` | T09 / R1 | `IMPLEMENTED` |
| SOL-002 | Native statuses map without overstating optimality | 16.3-16.4 | status mapper | status policy | `tests/unit/test_highs_backend.py::test_normalize_status_direct_mappings` and the time-limit/no-incumbent tests | T09 / R1 / G4 | `IMPLEMENTED` (gate G4 business approval still outstanding) |
| SOL-003 | Deterministic indexes/order/options support reproducibility | 16.5 | compiler/backend | threads/seed | `tests/unit/test_highs_backend.py::test_repeated_compile_and_solve_is_deterministic` | T07-T09 / R1 | `IMPLEMENTED` |
| VER-001 | Returned primal is independently checked for bounds, rows, balance, integrality, and objective | 18, 24 | solution verifier | tolerances | corrupted-solution tests (`tests/unit/test_solution_verifier.py`, T10) surfaced into the result (`tests/unit/reporting/test_result_builder.py::test_all_sections_present`, T11) | T10-T11 / R1 | `IMPLEMENTED` |
| VER-002 | Objective attribution reconstructs the unscaled result | 18.2 | attribution components | objective profile | E1; `tests/unit/reporting/test_attribution.py` (sum-reconciliation and seeded-mismatch tests) | T11 / R1-D2 | `IMPLEMENTED` |
| VER-003 | Strict infeasibility precedes any explicit allow-listed repair | 19 | diagnostics/repair | repair policy | E8 | T08-T11 / R1 / G1 | `SPECIFIED` |
| VER-004 | Legal, inventory, settlement, collateral coverage, and hard counterparty constraints never relax | 19.3 | repair policy/verifier | non-relaxable classes | E3-E5, E8 | T10 / R1-R3 / G1 | `SPECIFIED` |
| VER-005 | Explanations derive from coefficients, bounds, slacks, duals, and deltas | 18.3 | explanation service | reason policy | `tests/unit/reporting/test_explanations.py` (`HIGHER_NET_FEE`, `DEMAND_CAP_BINDING`, and the immaterial-change negative case) | T11 / R1 | `IMPLEMENTED` (2 of 24 reason codes derived so far, plus `ELASTICITY_REDUCED_DEMAND` carried through from T06; the remaining 21 wait on their owning constraint components, per `specs/0002-result-attribution-explainability/tasks.md` Follow-ups) |
| VER-006 | Result includes identity, desk, sources, balances, economics, constraints, solver, verification, and platform references | 18.1 | result contracts/reporting | output level | `tests/unit/reporting/test_result_builder.py::test_all_sections_present` | T11, T40 / R1-D2 | `IMPLEMENTED` (schedules/collateral/sources are explicit `None` -- no upstream domain model exists yet for them) |

---

## Point-in-Time Data and Bloomberg Enrichment

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| DAT-001 | Internal books/contracts/eligibility/limits remain authoritative | 22.1 | adapter reconciliation | source authority | conflict fixtures | T19-T20 / R3 / G2 | `SPECIFIED` |
| DAT-002 | Every enriched concept retains observed/effective time and mapping/source version | 22.2-22.3 | point-in-time contracts | field mapping | no-look-ahead tests | T19-T20 / R0-R3 / G2 | `SPECIFIED` |
| DAT-003 | Bloomberg concepts are mapped by deployment configuration, not hard-coded mnemonics | 22.2 | Bloomberg adapter | mapping config | synthetic contract tests | T20 / R3 / G2 | `SPECIFIED` |
| DAT-004 | Corporate-action changes preserve history and invalidate affected caches | 22.8 | event adapter/cache | event versions | amendment/cancel tests | T21 / R3 / G2 | `SPECIFIED` |
| DAT-005 | Liquidity and predictive estimates are calibrated to internal outcomes and labeled estimates | 22.5-22.7 | upstream feature adapter | model versions | walk-forward/challenger tests | T23-T25 / R3-R5 / G3 | `SPECIFIED` |
| DAT-006 | Licensed/vendor payloads do not enter fixtures or raw logs | 21.3, 22.2 | redaction/adapters | entitlement policy | fixture/log scan | T16, T20 / R3 / G2 | `SPECIFIED` |

---

## Multi-Period Settlement

No existing row covered §22.11/§22.12 before `specs/0010-multi-period-settlement/` (owner-approved
2026-09-07 to build both designs, sequenced): §22.11's deterministic form precedes §22.12's
stochastic/scenario-tree extension, which remains untouched and out of V0 scope per `00_PLAN.md`'s
own "Deferred extensions" list.

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MPS-001 | A deterministic projection walks the already-solved period-0 book forward through known future trade events, reusing the existing scenario-application mechanics unchanged | 22.11 | `settlement/project.py`, `scenarios/apply.py`'s shared `select_effective_events`/`apply_events` | `OptimizationRequest.planning_periods`/`.known_future_events` | `tests/golden/test_multi_period_settlement.py`, `tests/unit/test_settlement_project.py` (`specs/0010-multi-period-settlement/` Phase 1) | T-001–T-006 / Phase 5 item 2 | `IMPLEMENTED` |
| MPS-002 | A joint multi-period LP compiles §22.11's balance identities as real per-period constraints, letting period-0 allocation account for a known future event, as a pure continuous LP excluding MIP/QP/fee-tier triggers | 22.11 | `formulation/multi_period.py`, `components/objective_terms/multi_period_economics.py` | `OptimizationRequest.planning_periods`/`.known_future_events`, `MultiPeriodConfig.daily_discount_rate` | `tests/golden/test_multi_period_lp.py`, `tests/unit/test_multi_period_lp_compiler.py`, `tests/benchmark/test_multi_period_lp_scale.py` (`specs/0010-multi-period-settlement/` Phase 2) | T-007–T-012 / Phase 5 item 2 | `IMPLEMENTED` |
| MPS-003 | A known future recall's notice is validated against the referenced route's contractual minimum, uniformly for both designs | 22.11 | `validation/reconciliation.py::check_recall_notice_sufficiency` | `OptimizationRequest.known_future_events` | `tests/unit/test_validation.py::test_recall_notice_insufficient_is_reported`/`test_recall_notice_sufficient_is_accepted` (`specs/0010-multi-period-settlement/` T-002) | T-002 / Phase 5 item 2 | `IMPLEMENTED` |

---

## Existing-Platform Integration

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PLT-001 | QR Haven owns identity, authorization, data access, persistence, UI, approval, and recovery | 4.3, 17.5, 23.5 | QR Haven adapter/platform | responsibility map | architecture review | T17, T34 / R0-R1 / G2C | `SPECIFIED` |
| PLT-002 | Optimizer owns normalization, schedule resolution, formulation, solve, verification, and canonical result | 4.3, 23.5 | optimizer services | component manifest | end-to-end golden test: `tests/golden/test_e1_cli_end_to_end.py` (T12's `InventoryOptimizer`/CLI composing validation->formulation->solve->verification->result end to end); schedule resolution is not yet part of this chain (T29 has not started) | T01-T12 / R1 / G2C | `SPECIFIED` (T01-T12's own code/tests are complete; the row's `G2C` gate is a cross-cutting platform-ownership release approval shared with T17/T34-owned rows (`PLT-001`, `PLT-003`-`PLT-006`) this repo does not grant unilaterally) |
| PLT-003 | Invocation carries correlation, idempotency, authorization, schema, family, and as-of references | 17.4-17.5 | invocation contract | platform context | E9 schema tests | T34 / R0 / G2C | `SPECIFIED` |
| PLT-004 | Same idempotency key cannot represent different canonical input/config | 17.5 | cache/invocation service | idempotency policy | E9 conflict test | T34 / R0 / G2C | `SPECIFIED` |
| PLT-005 | Direct, in-process adapter, worker, and service transports preserve mathematical semantics | 17.5, 23.5 | facade/transports | schema versions | E9 equivalence suite | T17, T34 / R1, R8 / G2C-G8 | `SPECIFIED` |
| PLT-006 | Platform adapter cannot bypass validation or expose an unverified recommendation | 17.4, 23.7 | adapter/result workflow | approval policy | E9 corrupted-result test | T10, T17 / R1 / G2C | `SPECIFIED` |

---

## Agency-Lending Family

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AGY-001 | Agency inventory conserves separately by owner/pool/security | 23.3 | owner-balance component | owner/source mappings | E6; no-commingling property tests | T36 / D1 / G2D | `SPECIFIED` |
| AGY-002 | Cross-owner pooling/transformation requires explicit authority | 23.3 | pair/arc generation | mandate/transformation | E6 invalid-flow tests | T36 / D1 / G2D | `SPECIFIED` |
| AGY-003 | Owner mandates govern borrower, asset, market, term, collateral, utilization, voting, tax, and events | 23.2-23.3 | owner-mandate compiler | mandate schedules | E6; component tests | T29-T30, T36 / D1 / G2D | `SPECIFIED` |
| AGY-004 | Contractual allocation rules are hard; preferences are explicit attributable soft terms | 23.3 | fairness/exclusive components | fairness policy | E6 variants | T37 / D1 / G1, G2D | `SPECIFIED` |
| AGY-005 | Fee splits, reinvestment, servicing, transition, and owner revenue reconcile | 23.3 | agency economics/attribution | owner economics | E6; objective reconstruction | T36-T37 / D1 / G2D | `SPECIFIED` |
| AGY-006 | Indemnification exposure, limit, capital, stress, and cost are separate | 23.2-23.3 | indemnification component | indemnification policy | E6 variant/stress tests | T37 / D1 / G2D | `SPECIFIED` |
| AGY-007 | Owner contribution/withdrawal, mandate, exclusive, voting, and collateral shocks are immutable scenarios | 23.6 | agency scenario overlays | desk events | scenario golden tests | T40 / D1 / G2D | `SPECIFIED` |
| AGY-008 | Results attribute quantities, economics, opportunity cost, exceptions, and rules by owner | 18.1, 23.3, 23.6 | desk reporting | output config | E6 result schema | T40 / D1 / G2D | `SPECIFIED` |

---

## Prime-Inventory-Financing Family

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PRM-001 | Every source-to-client flow conserves authorized source capacity | 23.4 | source-network component | inventory sources/routes | E7; flow property tests | T38 / D2 / G2E | `SPECIFIED` |
| PRM-002 | Settled shorts/delivery commitments require full coverage or strict infeasibility | 23.4 | client-coverage component | demand lifecycle status | E7 expiry variant | T38 / D2 / G2E | `SPECIFIED` |
| PRM-003 | Indicative locates/forecasts may be explicitly unfilled under approved service policy | 23.4 | service/unfilled component | demand status/penalty | E7 locate variant | T38 / D2 / G2E | `SPECIFIED` |
| PRM-004 | Client-reuse and affiliate inventory default deny without effective authority | 9.8, 23.2, 23.4 | reuse-authority validator | consent/agreement | E7 reuse variant | T39 / D2 / G2E | `SPECIFIED` |
| PRM-005 | External borrow quotes carry lender/agreement, expiry, capacity, terms, stability, and all-in cost | 23.2, 23.4 | quote/source adapter | external quotes | E7 | T39 / D2 / G2E | `SPECIFIED` |
| PRM-006 | Prime objective attributes client revenue and every source/funding/collateral/capital/fail cost | 23.4 | prime economics/attribution | source/budget config | E7 reconstruction | T39 / D2 / G2E | `SPECIFIED` |
| PRM-007 | Funding, leverage, capital, liquidity, encumbrance, settlement, entity, and netting limits compile explicitly | 22.16, 23.4 | balance-sheet/limit components | budgets/netting sets | binding-budget fixtures | T22, T31, T39 / D2 / G2B, G2E | `SPECIFIED` |
| PRM-008 | Internal inventory carries explicit opportunity/funding/capital cost assumptions | 23.4, 28 | source economics | source-cost policy | zero-cost rejection/approval test | T39 / D2 / G2E | `SPECIFIED` |
| PRM-009 | Source recall, quote expiry/repricing, reuse loss, funding shock, fail, and buy-in are immutable scenarios | 23.6 | prime scenario overlays | desk events | E7 variants | T40 / D2 / G2E | `SPECIFIED` |
| PRM-010 | Results report internalization, external sourcing, replacement cost, coverage, and matched-book economics | 18.1, 23.6 | desk reporting | output config | E7 result schema | T40 / D2 / G2E | `SPECIFIED` |

---

## Governance and Release Evidence

| ID | Requirement | Spec location | Planned module/component | Config/input | Evidence | Task/release/gate | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GOV-001 | Every run records input/config/component/model/solver/result hashes and timing | 21.1 | run audit | observability config | audit schema tests | T16 / R1-R3 | `SPECIFIED` |
| GOV-002 | Sensitive names/raw records are excluded or redacted from logs | 21.3 | redaction/logging | data classification | log inspection tests | T16 / R1 / G2C | `SPECIFIED` |
| GOV-003 | Results are recommendations requiring downstream authorization | 21.3, 23.5 | platform approval workflow | authorization reference | adapter workflow tests | T17, T34 / R1 / G2C | `SPECIFIED` |
| GOV-004 | Changes to equations, units, source authority, status, or hard constraints require decision record and full-doc update | ROADMAPS 9 | release process | change metadata | PR/release checklist | all releases / applicable gate | `SPECIFIED` |
| GOV-005 | Golden updates require reviewed behavioral explanation and traceability update | EXAMPLES Golden-Update Policy | test/release process | fixture metadata | golden diff review | all releases | `SPECIFIED` |
| GOV-006 | Production promotion requires capability-appropriate business, control, engineering, and model-risk approval | 25, ROADMAPS 7 | release governance | approval records | gate checklist | R3-D2 and advanced releases | `SPECIFIED` |

---

## Critical End-to-End Trace Chains

### Baseline optimization

```text
platform/book snapshot
  -> canonical OptimizationRequest
  -> validation and reconciliation
  -> schedule resolution
  -> elasticity enrichment
  -> registered LP components
  -> sparse CompiledProblem
  -> HiGHS SolverResult
  -> independent VerifiedSolution
  -> attribution/explanation
  -> canonical OptimizationResult
  -> QR Haven persistence/presentation/approval
```

Primary requirements: `ARC-001`, `DOM-001` through `DOM-004`, `LP-001` through `LP-007`,
`SOL-001` through `SOL-003`, `VER-001` through `VER-006`, and `PLT-001` through `PLT-006`.

### Agency optimization

```text
owner/account inventory + mandates + schedules + borrower demand
  -> owner-mapped core inventory/routes/demand
  -> owner balance and mandate rows
  -> agency economics + indemnification + approved fairness/exclusives
  -> shared solve and independent verification
  -> owner-level allocation/economics/compliance result
```

Primary requirements: all baseline requirements plus `AGY-001` through `AGY-008`.

### Prime optimization

```text
client demand/obligations + owned/reusable/affiliate/external sources
  -> authority and agreement validation
  -> source-to-client route graph
  -> source conservation + hard/indicative coverage
  -> funding/collateral/capital/service economics and limits
  -> shared solve and independent verification
  -> client/source/entity matched-book result
```

Primary requirements: all baseline requirements plus `PRM-001` through `PRM-010`.

---

## Change-Control Rules

1. New normative behavior receives a stable requirement ID in this file.
2. Each requirement names at least one focused automated evidence item before implementation is
   considered complete.
3. A requirement affecting a public contract identifies schema compatibility and migration impact.
4. A requirement affecting mathematics identifies objective/row/bound units and independent
   verification impact.
5. A hard policy requirement identifies its authority, non-relaxable status, and approval gate.
6. A desk-specific requirement proves the baseline family is unchanged when that desk is disabled.
7. A platform requirement proves direct/adapter transport equivalence and preserves the one-way
   dependency.
8. A Bloomberg/vendor requirement uses synthetic fixtures and preserves licensing/entitlement
   boundaries.
9. Pull requests update status and evidence links only after the cited tests exist and pass.
10. Release approval records live in the implementation/release system; this portable document
    references them without embedding sensitive names or proprietary data.

---

## Initial Coverage Summary

| Domain | Requirement IDs | Worked examples |
| --- | --- | --- |
| Architecture/config | `ARC-001`–`ARC-005`, `CFG-001`–`CFG-004` | E9 |
| Domain/LP/economics | `DOM-001`–`DOM-004`, `LP-001`–`LP-009` | E1-E3, E5, E7-E8 |
| Schedules/collateral/scenarios | `SCH-001`–`SCH-004`, `COL-001`–`COL-004`, `SCN-001`–`SCN-004` | E2-E5 |
| Solver/verification/results | `SOL-001`–`SOL-003`, `VER-001`–`VER-006` | E1-E9 |
| Point-in-time/Bloomberg | `DAT-001`–`DAT-006` | Synthetic adapter fixtures; detailed implementation examples deferred |
| Multi-period settlement | `MPS-001`–`MPS-003` | Hand-constructed fixtures (`specs/0010-multi-period-settlement/`); no `EXAMPLES.md` worked case exists for a multi-period scenario |
| Platform integration | `PLT-001`–`PLT-006` | E9 |
| Agency | `AGY-001`–`AGY-008` | E6 |
| Prime | `PRM-001`–`PRM-010` | E7 |
| Governance | `GOV-001`–`GOV-006` | E8-E9 and golden-update policy |

This initial matrix provides specification coverage, not evidence of implementation. The first
implementation pull request should replace planned evidence descriptions with exact test paths and
CI job names for the rows it completes.

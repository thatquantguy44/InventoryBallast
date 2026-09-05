# Spec002: Platform-Integrated, Standalone Securities-Lending Inventory Optimization Engine

## 1. Document Control

| Field | Value |
| --- | --- |
| Status | Ready for implementation |
| Branch | `inv_optimizer` |
| Project code | `inventory_optimizer` |
| Proposed project root | `projects/inventory_optimizer/` |
| Core package | `inventory_optimizer` |
| Initial deployment | Modular subsystem integrated into the existing QR Haven platform |
| Python | 3.11 or newer |
| Initial formulation | Continuous LP |
| Initial solver | HiGHS via `highspy` |
| Future formulations | MIP, convex QP, piecewise-linear, SCA, optional NLP |
| Primary users | Inventory, agency-lending, and prime-financing desks; quantitative developers; operations; risk/control |

This document is the product specification, mathematical model, software architecture, and
implementation handoff. The initial deliverable is a first-class modular subsystem of the existing
QR Haven platform, with its own package, configuration, domain contracts, services, tests, and
release lifecycle. Its core remains portable so it can later be extracted into its own repository
without redesigning the model or platform contract.

Companion documents:

- `00_PLAN.md`: scope, locked decisions, and implementation sequence.
- `ROADMAPS.md`: coordinated release and workstream roadmaps.
- `DICTIONARY.md`: canonical terminology, units, symbols, statuses, and reason codes.
- `WHITEPAPER.md`: technical rationale, research context, and end-to-end model narrative.
- `EXAMPLES.md`: hand-calculable golden fixtures and expected results.
- `TRACEABILITY.md`: requirement-to-module/config/test/task/release/gate mapping.

---

## 2. Executive Summary

Build an inventory optimization engine that recommends how many shares to keep on loan, recall, or
newly allocate across eligible borrowers and inventory pools. It maximizes configurable net lending
economics while preserving exact inventory balances and enforcing operational, utilization,
counterparty, concentration, settlement, and demand constraints.

The engine accepts a point-in-time baseline, policy configuration, forecast demand, fee rates, and
optional scenarios. Its default LP treats the fee on each candidate route as exogenous. Demand
elasticity translates a fee assumption into a maximum demand quantity before formulation. This
separation keeps the first model linear, fast, and easy to audit.

The same domain contracts support later extensions:

- MIP for lots, minimum tickets, all-or-none orders, cardinality, and discrete fee selection.
- Convex QP for concentration risk, correlated revenue risk, and smooth allocation changes.
- Piecewise-linear or sequential convex approximation for selected nonlinear costs.
- Optional nonlinear backends for joint fee/quantity optimization.

The `inventory_optimizer` core package must have no import-time or runtime dependency on
`qr_haven`. The existing platform hosts and invokes it through platform-owned adapters that provide
inventory, loans, demand, schedules, reference data, identity, authorization context, audit sinks,
and reporting. The platform may depend on the optimizer; the optimizer core may not depend on the
platform.

---

## 3. Goals and Non-Goals

### 3.1 Goals

1. Reconcile total lendable inventory, reserved quantities, on-loan quantities, and remaining
   available-to-lend quantities for every inventory pool and security.
2. Allocate scarce inventory to the routes with the best risk- and cost-adjusted lending economics.
3. Incorporate current fee rates, forecast utilization, borrower demand, and demand elasticity.
4. Model the cost of changing the current book, including recalls, returns, setup, settlement, and
   configurable relationship penalties.
5. Evaluate proposed buys, sells, transfers, loans, returns, recalls, and rate/demand shocks as
   isolated what-if scenarios.
6. Make constraints, objective terms, policies, and solvers independently extensible.
7. Return an independently verified and fully attributable answer.
8. Remain efficient for desk-scale sparse problems and deterministic under fixed inputs/config.
9. Integrate cleanly into QR Haven through stable ports while retaining its own modules,
   configuration, tests, version, and release manifest.
10. Be separable from the QR Haven monorepo by copying one project directory and removing the
    platform-owned adapter.
11. Support opt-in agency-lending and prime-inventory-financing problem families without changing
    the verified baseline inventory equations.

### 3.2 Non-goals for V0

- Sending recalls, loan instructions, trades, or bookings to external systems.
- Replacing the system of record for positions, loans, or legal eligibility.
- Predicting demand inside the optimization package. It consumes demand and elasticity estimates.
- Optimizing collateral schedules, cash reinvestment portfolios, or collateral substitution. Their
  economics may be supplied as route attributes, but they are not decision variables in V0.
- Solving a multi-day stochastic control problem.
- Supporting generic algebraic user expressions in configuration.
- Automatically accepting a feasible answer after relaxing hard policy.
- Replacing the existing platform's GUI, API gateway, authentication, scheduler, persistence,
  streaming, or entitlement facilities. Platform adapters may expose optimizer functionality
  through them.

---

## 4. Design Principles and Boundaries

### 4.1 Dependency rule

Dependencies point inward:

```text
existing platform UI/API/jobs
            |
            v
platform-owned inventory_optimizer adapter
            |
            v
optimizer application services and scenarios
            |
            v
formulation + domain + ports
            |
            v
solver adapters / injected audit/cache/report ports
```

The domain and formulation layers may depend on Python, NumPy, SciPy sparse types, and local package
interfaces. They must not depend on dataframes, HiGHS classes, QR Haven classes, web frameworks, or
storage clients. Adapters convert external representations at the boundary.

### 4.2 Core principles

- **Point-in-time correctness:** every input carries a common `as_of` or explicit effective time.
- **Units at the boundary:** shares, USD/share, annual decimal rates, and calendar-day fractions are
  canonical. Bps exist only in transport/display helpers.
- **Immutable requests:** scenario evaluation never mutates a baseline request or snapshot.
- **Sparse by construction:** variable and row indexes are explicit; matrices are sparse.
- **Policy through components:** configured constraints/objective terms are registered components.
- **Backend isolation:** solver-native status, options, models, and arrays do not escape adapters.
- **Fail closed:** invalid balances, stale required data, unknown component names, or unsupported
  capabilities fail before solve.
- **Independent verification:** the service recalculates balances, bounds, integrality, and objective
  values from the returned primal solution.
- **Audit over cleverness:** an explainable LP is the default even when more complex modes exist.

### 4.3 Platform integration and standalone extraction rule

The existing platform is the initial runtime and system-integration boundary. It owns user identity,
authorization, upstream data access, orchestration, persistence, and presentation. The optimizer
owns normalization, schedule resolution, formulation, solution, independent verification,
attribution, and its canonical result contract. Integration may be in-process, a worker job, or a
later service transport, but all three invoke the same public facade and produce the same result.

The future directory `projects/inventory_optimizer/` is the extraction unit. A portability test must
copy it to a temporary directory, install it, run its tests, and import the package with the QR Haven
source tree absent from `PYTHONPATH`. Platform-specific code stays in
`src/qr_haven/integrations/inventory_optimizer.py` and is not copied.

### 4.4 Reuse by future optimization problems

V0 exposes one problem family, `securities_lending_inventory`. Later opt-in families
`agency_lending` and `prime_inventory_financing` reuse its verified inventory kernel. The
compiled-problem contract,
variable/row builders, solver ports, capability checks, component metadata, status normalization,
verification primitives, configuration loader, and run audit envelope are deliberately
domain-neutral. A later collateral, funding, liquidity, or balance-sheet optimizer may register a
different problem family and reuse those primitives.

The inventory domain records and equations remain inventory-specific. Do not weaken them into
generic dictionaries in anticipation of future models. When a second implemented problem proves a
shared abstraction, the domain-neutral modules may be extracted into an `optimization_kernel`
package with compatibility tests. Until then, reuse is through stable protocols and patterns, not an
unowned framework.

---

## 5. Canonical Vocabulary and Units

### 5.1 Inventory quantities

For one `(inventory_pool_id, security_id)` at one effective time:

```text
gross_inventory
  - ineligible_inventory
  - policy_exclusions
= total_lendable

available_to_lend
= total_lendable
   - on_loan
   - reserved
   - committed_out
```

`total_lendable` includes shares already on loan. Upstream feeds that use `lendable_supply` to mean
only available supply must be mapped explicitly. The optimizer never guesses which convention a
source uses.

Post-optimization:

```text
post_total_lendable
  = baseline_total_lendable + settled_trade_delta + eligible_transfer_delta

post_on_loan
  = sum(post_route_quantity for all routes drawing on the pool/security)

post_available_to_lend
  = post_total_lendable - post_on_loan - post_reserved - post_committed_out

post_utilization
  = post_on_loan / post_total_lendable, if post_total_lendable > 0
```

If `post_total_lendable == 0`, utilization is reported as `null`, not zero, and post on-loan,
reserved, and committed-out quantities must all be zero.

### 5.2 Units

| Concept | Canonical internal unit | Example |
| --- | --- | --- |
| Quantity | shares as `float64` | `125_000.0` |
| Price | USD per share | `42.50` |
| Notional | USD | quantity x price |
| Fee/rate | annual decimal | 175 bps = `0.0175` |
| Day fraction | calendar days / configured year basis | 1 day on ACT/360 = `1/360` |
| Elasticity | non-negative dimensionless magnitude | `0.60` |
| Utilization | decimal in `[0, 1]` | 92% = `0.92` |
| Timestamp | timezone-aware UTC | ISO 8601 |
| Money output | USD, full precision internally | rounding only at display |

Share quantities may be continuous in LP mode. If a business process requires integer shares or
board lots, it must enable rounding with repair or use the MIP formulation. The result records which
method was applied.

### 5.3 Terms

| Term | Meaning |
| --- | --- |
| Inventory pool | A legal/operational source of lendable inventory, such as a beneficial-owner account. |
| Route | A possible post-state loan allocation from one pool/security to one borrower under one set of economics and terms. |
| Current quantity | Shares currently on loan on a route; zero for a new candidate route. |
| Demand group | Routes competing to serve the same borrower/security demand forecast. |
| Hard constraint | A rule that cannot be relaxed by the normal solve. |
| Soft constraint | A target represented by explicit slack with a configured penalty. |
| Scenario | An immutable overlay on the baseline inputs or policy. |
| Strict result | A solution with no hard-policy relaxation. |
| Repaired result | A result from an explicitly requested relaxation policy, with all relaxations reported. |

---

## 6. Required Use Cases

### UC-1 — End-of-day rebalance

Given reconciled inventory, open loans, current fees, and next-period demand, recommend post-state
route quantities. Explain keeps, increases, decreases/recalls, idle inventory, expected net revenue,
and binding constraints.

### UC-2 — Scarce-name allocation

When demand exceeds lendable supply, prioritize higher net-economic routes while respecting
borrower, beneficial-owner, concentration, utilization, and reserve policies.

### UC-3 — Existing-book reallocation

Compare fee uplift against recall and setup costs before moving shares from a lower-value existing
loan to a higher-value route. Avoid churn when the incremental benefit does not clear configured
costs.

### UC-4 — Proposed sell

Reduce lendable inventory on the proposed settlement date. Determine whether the sale fits within
available inventory, which loans would need recall, the associated lost revenue/transition cost,
and whether settlement or legal rules make the scenario infeasible.

### UC-5 — Proposed buy or transfer-in

Increase eligible lendable inventory and estimate additional allocation, utilization, and lending
revenue. Unsettled or ineligible quantities do not enter supply.

### UC-6 — Fee and demand shock

Apply a rate change, demand multiplier, or elasticity override without mutating the baseline.
Recompute demand caps and compare allocations and economics.

### UC-7 — Discrete operating rules

When enabled, respect all-or-none requests, minimum tickets, lot sizes, maximum active routes, or
one selected rate tier using MIP variables.

### UC-8 — Batch scenario comparison

Evaluate many independent scenarios against the same snapshot and rank them by objective delta,
net revenue delta, utilization, recalls, unfilled demand, policy slacks, and feasibility.

### UC-9 — Agency beneficial-owner allocation

Allocate separately owned inventory across approved borrowers while preserving owner-level balances,
mandates, fee splits, collateral schedules, indemnification charges, voting/recall needs, and
contractual exclusives. Explain both economic allocation and any configured fairness tradeoff.

### UC-10 — Prime client-short sourcing

Cover client short demand from permitted firm inventory, rehypothecatable client inventory,
affiliates, and external borrows. Minimize replacement, funding, collateral, capital, settlement,
and expected recall/fail costs while preserving client and legal-entity service constraints.

### UC-11 — Existing-platform invocation

Accept an authorized, point-in-time request assembled by the existing platform, run the same
validate/solve/verify pipeline in-process or through a worker/service boundary, and return a
versioned canonical result that the platform can persist, display, and route for approval.

---

## 7. Target Project Structure

```text
projects/inventory_optimizer/
├── pyproject.toml
├── README.md
├── CHANGELOG.md
├── LICENSE                         # if/when extracted
├── configs/
│   ├── default.yaml
│   ├── environments/
│   │   ├── local.yaml
│   │   ├── test.yaml
│   │   └── production.yaml
│   ├── formulations/
│   │   ├── lp.yaml
│   │   ├── mip.yaml
│   │   └── qp.yaml
│   ├── objectives/
│   │   ├── net_revenue.yaml
│   │   └── balanced_utilization.yaml
│   ├── policies/
│   │   ├── standard.yaml
│   │   └── conservative.yaml
│   ├── desks/
│   │   ├── inventory_core.yaml
│   │   ├── agency.yaml
│   │   └── prime.yaml
│   ├── schedules/
│   │   ├── eligibility.example.yaml
│   │   ├── collateral.example.yaml
│   │   ├── fees.example.yaml
│   │   └── settlement.example.yaml
│   ├── solvers/
│   │   └── highs.yaml
│   └── scenarios/
│       ├── proposed_sale.example.yaml
│       └── rate_shock.example.yaml
├── src/inventory_optimizer/
│   ├── __init__.py
│   ├── api.py                     # stable public facade
│   ├── cli.py                     # validate/optimize/scenario commands
│   ├── version.py
│   ├── config/
│   │   ├── __init__.py
│   │   ├── models.py              # validated config objects
│   │   ├── loader.py              # deterministic layer merge
│   │   └── hashing.py             # canonical config hash
│   ├── domain/
│   │   ├── __init__.py
│   │   ├── enums.py
│   │   ├── identifiers.py
│   │   ├── inventory.py
│   │   ├── loans.py
│   │   ├── demand.py
│   │   ├── trades.py
│   │   ├── policies.py
│   │   ├── eligibility.py
│   │   ├── collateral.py
│   │   ├── schedules.py
│   │   ├── desks.py
│   │   ├── owners.py
│   │   ├── sources.py
│   │   ├── agreements.py
│   │   ├── requests.py
│   │   └── results.py
│   ├── ports/
│   │   ├── __init__.py
│   │   ├── solver.py
│   │   ├── demand.py
│   │   ├── clock.py
│   │   ├── audit.py
│   │   └── cache.py
│   ├── validation/
│   │   ├── __init__.py
│   │   ├── input_validation.py
│   │   ├── reconciliation.py
│   │   ├── freshness.py
│   │   └── solution_verifier.py
│   ├── elasticity/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── constant.py
│   │   ├── semilog.py
│   │   └── caps.py
│   ├── schedules/
│   │   ├── __init__.py
│   │   ├── resolver.py
│   │   ├── precedence.py
│   │   ├── eligibility.py
│   │   ├── collateral.py
│   │   └── compiled.py
│   ├── components/
│   │   ├── __init__.py
│   │   ├── decorators.py
│   │   ├── registry.py
│   │   ├── objective_terms/
│   │   │   ├── fee_revenue.py
│   │   │   ├── reinvestment.py
│   │   │   ├── transition_cost.py
│   │   │   ├── utilization.py
│   │   │   ├── risk_penalty.py
│   │   │   ├── indemnification.py
│   │   │   ├── external_borrow.py
│   │   │   └── balance_sheet.py
│   │   └── constraints/
│   │       ├── inventory_balance.py
│   │       ├── demand.py
│   │       ├── utilization.py
│   │       ├── counterparty.py
│   │       ├── eligibility.py
│   │       ├── collateral.py
│   │       ├── schedule_limits.py
│   │       ├── concentration.py
│   │       ├── owner_balance.py
│   │       ├── sourcing_network.py
│   │       ├── client_service.py
│   │       └── discrete.py
│   ├── formulation/
│   │   ├── __init__.py
│   │   ├── indexes.py
│   │   ├── variables.py
│   │   ├── rows.py
│   │   ├── sparse_builder.py
│   │   ├── lp.py
│   │   ├── mip.py
│   │   ├── qp.py
│   │   └── compiled.py
│   ├── solvers/
│   │   ├── __init__.py
│   │   ├── statuses.py
│   │   ├── capabilities.py
│   │   ├── highs.py
│   │   └── optional.py            # lazy optional-backend loading
│   ├── scenarios/
│   │   ├── __init__.py
│   │   ├── overlays.py
│   │   ├── apply.py
│   │   ├── runner.py
│   │   └── comparison.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── optimizer.py
│   │   ├── pipeline.py
│   │   ├── desk_profiles.py
│   │   └── explain.py
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── tables.py
│   │   ├── attribution.py
│   │   └── serialization.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── json_io.py             # request/result transport adapter
│   │   └── dataframe.py           # optional tabular boundary adapter
│   ├── observability/
│   │   ├── __init__.py
│   │   ├── logging.py
│   │   ├── metrics.py
│   │   └── audit.py
│   └── exceptions.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── golden/
│   ├── property/
│   ├── performance/
│   ├── fixtures/
│   └── conftest.py
├── examples/
│   ├── minimal_lp.py
│   ├── trade_scenarios.py
│   ├── agency_allocation.py
│   └── prime_sourcing.py
├── docs/
│   ├── data_contracts.md
│   ├── model_card.md
│   ├── operations.md
│   └── extension_guide.md
└── scripts/
    ├── benchmark.py
    └── verify_portability.py
```

### 7.1 Module ownership rules

| Layer | Owns | Must not own |
| --- | --- | --- |
| `domain` | Business records, IDs, enums, request/result types | Solver calls, dataframe transforms |
| `ports` | Protocols for external capabilities | Concrete adapters |
| `validation` | Input invariants and independent result checks | Objective policy |
| `elasticity` | Rate-to-demand transformations | Demand model training |
| `schedules` | Effective-dated rule resolution and compiled policy decisions | Solver calls or vendor-specific field logic |
| `components` | Small objective and constraint contributors | End-to-end orchestration |
| `formulation` | Variable indexes and mathematical program assembly | Business I/O or reporting |
| `solvers` | Backend translation and normalized solver results | Domain decisions |
| `scenarios` | Immutable overlays and comparisons | Baseline mutation |
| `services` | Application workflow, desk-profile selection, and explanation | Backend-specific APIs or platform authorization |
| `reporting` | Tables, attribution, serialization | Re-solving or changing results |
| `adapters` | JSON and optional dataframe conversion | Domain rules or formulation logic |
| `observability` | Structured logs, metrics, audit envelope | Raw sensitive payload dumps |

### 7.2 Dependency groups

The project metadata should keep capabilities optional:

| Group | Intended dependencies |
| --- | --- |
| Core | Pydantic, NumPy, SciPy, PyYAML |
| `highs` | `highspy` at a tested lower bound and locked production version |
| `dataframe` | pandas for boundary conversion only |
| `bloomberg` | Firm-approved Bloomberg client/connectivity dependencies, adapter-only |
| `dev` | pytest, Hypothesis, Ruff, mypy, coverage tools |
| `nonlinear` | Chosen NLP backend only after Phase 5 approval |

`highspy` is installed in the default deployment extra because HiGHS is the required V0 backend,
but it remains isolated to `solvers/highs.py`. Importing domain/config modules must not import a
solver or optional dataframe package.

---

## 8. Configuration Architecture

### 8.1 Layer precedence

Configuration is merged from lowest to highest precedence:

```text
package defaults
  < environment
  < desk profile
  < formulation
  < objective profile
  < policy profile
  < run/scenario file
  < explicit CLI or Python API overrides
```

The loader performs a deep merge, rejects unknown keys, validates the final object, redacts marked
sensitive values, and calculates a stable SHA-256 hash of canonical JSON. Environment variables may
reference secrets or paths, but they must not silently override model policy.

V0 uses Pydantic and PyYAML. Hydra is not required. Config objects are frozen after validation.

### 8.2 Configuration objects

```python
class InventoryOptimizerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    desk: DeskConfig
    formulation: FormulationConfig
    objective: ObjectiveConfig
    constraints: ConstraintConfig
    schedules: ScheduleConfig
    collateral: CollateralConfig
    elasticity: ElasticityConfig
    solver: SolverConfig
    validation: ValidationConfig
    scenarios: ScenarioConfig
    observability: ObservabilityConfig
```

Required nested classes:

- `DeskConfig`: problem family, enabled desk components, source hierarchy, attribution level, and
  capability requirements.
- `FormulationConfig`: `mode`, planning horizon, day-count basis, quantity type, scaling.
- `ObjectiveConfig`: enabled terms and weights, revenue horizon, churn/recall costs.
- `ConstraintConfig`: reserves, utilization policy, concentration/counterparty rules, soft rules.
- `ScheduleConfig`: sources, precedence, conflict behavior, effective-time rules, approvals.
- `CollateralConfig`: validation/capacity/joint mode, valuation, haircut, concentration, and fallback
  policy.
- `ElasticityConfig`: curve type, floors/caps, missing-estimate policy, uncertainty haircut.
- `SolverConfig`: backend, algorithm, tolerances, time/gap limits, threads, seed, log level.
- `ValidationConfig`: balance tolerance, staleness limits, duplicate policy, post-solve tolerances.
- `ScenarioConfig`: maximum batch size, parallelism, reuse policy, comparison metrics.
- `ObservabilityConfig`: run IDs, output level, audit sink, data redaction.

### 8.3 Illustrative `default.yaml`

```yaml
formulation:
  mode: lp
  planning_horizon_days: 1
  day_count_basis: 360
  quantity_mode: continuous
  objective_scale_usd: 1000.0

desk:
  problem_family: securities_lending_inventory
  profile: inventory_core
  source_hierarchy: [owned_inventory]
  require_owner_partition: false
  require_balance_sheet_budget: false

objective:
  profile: net_revenue
  terms:
    - name: fee_revenue
      weight: 1.0
    - name: collateral_reinvestment
      weight: 1.0
    - name: allocation_increase_cost
      weight: 1.0
    - name: recall_cost
      weight: 1.0
    - name: utilization_target_penalty
      weight: 0.0

constraints:
  enabled:
    - inventory_balance
    - demand_cap
    - eligibility
    - eligibility_schedule
    - collateral_schedule
    - utilization_cap
    - counterparty_limit
  default_utilization_cap: 0.98
  default_reserve_fraction: 0.02
  allow_explicit_soft_constraints: true

schedules:
  precedence: deny_then_specificity_then_priority
  conflict_policy: reject
  require_observed_and_effective_time: true
  require_approval_metadata: true

collateral:
  mode: validate_only
  missing_schedule_policy: reject
  stale_valuation_policy: reject
  wrong_way_risk_policy: reject

elasticity:
  curve: constant_elasticity
  missing_policy: conservative_default
  default_elasticity: 0.0
  uncertainty_haircut_sigma: 1.0
  minimum_fee_rate: 0.000001

solver:
  backend: highs
  algorithm: choose
  time_limit_seconds: 30.0
  relative_mip_gap: 0.001
  primal_feasibility_tolerance: 1.0e-7
  dual_feasibility_tolerance: 1.0e-7
  threads: 1
  random_seed: 0
  emit_native_log: false

validation:
  inventory_balance_tolerance_shares: 1.0e-6
  objective_tolerance_usd: 1.0e-6
  max_inventory_age_minutes: 60
  require_common_as_of: true
  reject_duplicate_ids: true

scenarios:
  maximum_batch_size: 500
  parallelism: 1
  reuse_compiled_structure: true
```

### 8.4 Configuration safety

- Unknown objective/constraint/backend names are errors.
- Duplicate component names are errors unless a component explicitly supports multiple instances.
- A nonzero soft-constraint penalty must state its USD interpretation.
- A solver mode must declare required capabilities before data processing begins.
- Production config must pin a tested `highspy` version in the lock file.
- Runtime output includes the config hash and resolved component manifest.
- The selected desk profile must be compatible with the request type, required domain records, and
  solver capabilities; a profile cannot silently enable a different economic objective.
- Schedule conflicts, missing approvals, expired rules, and missing required collateral schedules are
  errors unless the resolved configuration names a stricter deterministic fallback.

### 8.5 Illustrative desk profiles

```yaml
# configs/desks/agency.yaml
desk:
  problem_family: agency_lending
  profile: agency
  source_hierarchy: [beneficial_owner]
  require_owner_partition: true
  require_balance_sheet_budget: false
  required_components:
    - owner_inventory_balance
    - owner_mandate
    - agency_economics
    - indemnification
  optional_components:
    - agency_fairness
    - agency_exclusive
```

```yaml
# configs/desks/prime.yaml
desk:
  problem_family: prime_inventory_financing
  profile: prime
  source_hierarchy: [firm_owned, client_reuse, affiliate, external_borrow]
  require_owner_partition: false
  require_balance_sheet_budget: true
  required_components:
    - source_conservation
    - client_demand_coverage
    - reuse_authority
    - source_economics
    - balance_sheet_budget
  optional_components:
    - source_activation
    - source_stability
    - dynamic_client_pricing
```

The lists are manifests, not arbitrary Python import paths. Every named component must be registered,
versioned, formulation-compatible, and independently verified. Production overlays may disable an
optional component but cannot omit a family-required component.

---

## 9. Domain Model and Data Contracts

Boundary contracts should use frozen Pydantic models. Internal compiled arrays use immutable index
maps plus NumPy `float64` and SciPy sparse matrices. IDs are opaque strings; tickers are labels, not
join keys.

### 9.1 Primary classes

| Class | Responsibility |
| --- | --- |
| `SecurityInventory` | One pool/security supply record and its baseline reconciliation. |
| `LoanRoute` | Existing or candidate allocation path with economics, eligibility, and limits. |
| `DemandForecast` | Demand group reference quantity/rate, elasticity, uncertainty, and caps. |
| `CounterpartyLimit` | Borrower gross/notional/name-level limit. |
| `UtilizationPolicy` | Floor, target, cap, reserve, and soft/hard semantics. |
| `EligibilitySchedule` | Effective-dated allow/deny/grandfather/recall-only rules and route limits. |
| `CollateralSchedule` | Effective-dated eligible collateral, margin, haircut, concentration, and valuation rules. |
| `ConstraintSchedule` | Common versioned schedule envelope for fee, settlement, event, capital, or operating rules. |
| `DeskContext` | Selected problem family, desk/legal entity, platform tenant, and attribution scope. |
| `BeneficialOwnerMandate` | Agency owner permissions, economics, restrictions, fairness, and reporting policy. |
| `InventorySource` | Owned, client, affiliate, or external source with legal availability and costs. |
| `ClientShortDemand` | Prime-client short/settlement requirement and service semantics. |
| `ExternalBorrowQuote` | Effective, expiring third-party source capacity and all-in borrow terms. |
| `IndemnificationPolicy` | Covered risks, limits, capital/cost methodology, and exclusions. |
| `AgreementNettingSet` | Approved agreement/entity grouping for exposure, collateral, and close-out. |
| `BalanceSheetBudget` | Desk/entity funding, leverage, capital, liquidity, or encumbrance limit. |
| `TradeEvent` | Proposed settled inventory change. |
| `Scenario` | Immutable collection of trade, rate, demand, and policy overlays. |
| `OptimizationRequest` | Complete baseline solve request. |
| `ScenarioBatchRequest` | Baseline plus scenarios. |
| `OptimizationResult` | Verified allocations, balances, economics, status, and audit metadata. |
| `ScenarioComparison` | Baseline/scenario deltas and rankings. |

### 9.2 `SecurityInventory`

| Field | Type/unit | Required | Invariant |
| --- | --- | --- | --- |
| `inventory_id` | string | yes | Unique per request. |
| `inventory_pool_id` | string | yes | Opaque legal/operational pool ID. |
| `security_id` | string | yes | Stable CUSIP/ISIN/internal ID. |
| `as_of` | UTC datetime | yes | Within configured freshness window. |
| `settlement_date` | date | yes | Supply availability date. |
| `total_lendable_shares` | shares | yes | Non-negative. Includes on-loan. |
| `on_loan_shares` | shares | yes | Non-negative. Reconciles to current routes. |
| `reserved_shares` | shares | yes | Non-negative. |
| `committed_out_shares` | shares | yes | Non-negative. |
| `available_to_lend_shares` | shares | yes | Must equal the canonical balance. |
| `price_usd` | USD/share | yes | Strictly positive for economic optimization. |
| `currency` | ISO code | yes | V0 requires USD after adapter conversion. |
| `eligible` | bool | yes | False forces post on-loan to zero unless grandfather policy says otherwise. |
| `source_version` | string | yes | Lineage/audit reference. |

The adapter must reject or explicitly transform upstream inventory that cannot state whether
`lendable_supply` includes on-loan quantity.

### 9.3 `LoanRoute`

| Field | Type/unit | Required | Notes |
| --- | --- | --- | --- |
| `route_id` | string | yes | Unique and stable within a request. |
| `inventory_id` | string | yes | Source inventory record. |
| `security_id` | string | yes | Must match source inventory. |
| `borrower_id` | string | yes | Pseudonymous internal ID. |
| `demand_group_id` | string | yes | Groups routes serving the same demand. |
| `current_quantity_shares` | shares | yes | Zero for a new route. |
| `hard_minimum_quantity_shares` | shares | yes | Contractual post-state floor; defaults to zero. |
| `minimum_active_quantity_shares` | shares | no | Business ticket minimum; requires MIP when positive. |
| `maximum_quantity_shares` | shares | yes | Non-negative and at least current contractual minimum. |
| `fee_rate` | annual decimal | yes | Gross lender-side fee rate. |
| `revenue_share` | decimal `[0,1]` | yes | Portion credited to the optimized book. |
| `reinvestment_rate` | annual decimal | no | Net collateral reinvestment spread. |
| `collateral_factor` | decimal | no | Schedule-derived eligible cash collateral/notional multiplier for validate/capacity modes. |
| `variable_cost_rate` | annual decimal | yes | Per-notional operating/capital/risk charge. |
| `increase_cost_usd_per_share` | USD/share | yes | Setup and transition cost for positive delta. |
| `decrease_cost_usd_per_share` | USD/share | yes | Recall/return/relationship cost for negative delta. |
| `recall_notice_days` | days | yes | Used by scenario eligibility. |
| `term_end_date` | date or null | yes | Term routes cannot be reduced early unless allowed. |
| `eligible` | bool | yes | Structural/source eligibility intersected with the resolved schedule; false removes candidate capacity and an existing route follows its explicit unwind rule. |
| `all_or_none` | bool | yes | Requires MIP when true. |
| `lot_size_shares` | shares or null | no | Requires MIP or post-solve rounding/repair. |
| `priority_class` | string | no | Optional configured service-level grouping. |

### 9.4 `DemandForecast`

| Field | Type/unit | Required | Notes |
| --- | --- | --- | --- |
| `demand_group_id` | string | yes | Unique; referenced by routes. |
| `security_id` | string | yes | Demand security. |
| `borrower_id` | string | yes | Demand borrower. |
| `as_of` | UTC datetime | yes | Must satisfy freshness policy. |
| `reference_quantity_shares` | shares | yes | Unconstrained demand at the reference rate. |
| `reference_fee_rate` | annual decimal | yes | Strictly positive when elasticity is used. |
| `elasticity` | non-negative float | yes | Magnitude of price elasticity. |
| `forecast_std_shares` | shares | no | Used for conservative demand haircut. |
| `hard_max_quantity_shares` | shares or null | no | Absolute upper cap after elasticity. |
| `source_model` | string | yes | Lineage identifier. |
| `source_version` | string | yes | Model/data version. |

### 9.5 Policy and limit contracts

`CounterpartyLimit` contains a unique `limit_id`, `borrower_id`, effective interval, optional
security/pool scope, and one or both of `maximum_notional_usd` and `maximum_quantity_shares`. It also
contains a `hard` flag, source/version fields, and optional risk class. V0 rejects non-USD notional
limits unless an adapter has converted them with an identified FX snapshot.

`UtilizationPolicy` contains a unique `policy_id`, pool/security scope, effective interval, optional
`minimum_utilization`, `target_utilization`, and `maximum_utilization`, plus absolute/fractional
availability buffers. Each target declares hard or soft treatment. A soft side includes an explicit
USD-per-share penalty and priority; hard minimums/caps do not. The most specific applicable policy
wins only when configuration says so; otherwise overlapping policies are intersected and identified
in the component manifest.

### 9.6 Schedule contracts

All schedules share a frozen envelope:

- `schedule_id`, `schedule_type`, and immutable `version`;
- `observed_at`, `effective_from`, and optional `effective_to`;
- schedule owner, approval ID/status, source, and source version;
- timezone/calendar used for date boundaries;
- ordered rules with stable `rule_id`, scope selector, priority, reason code, and provenance; and
- supersedes/cancelled metadata for bitemporal history.

An `EligibilityRule` may select beneficial owner/pool, security/issuer/classification, borrower or
approved entity aggregate, country/market/currency, account/legal agreement, collateral schedule,
term, event/status, or scenario. Its action is one of:

- `ALLOW`: route may be created within the resolved bounds;
- `DENY`: no new allocation and existing quantity follows the explicit unwind rule;
- `GRANDFATHER`: current quantity may remain but cannot increase;
- `RECALL_ONLY`: current quantity must decline according to the effective recall requirement; or
- `REVIEW`: route is not automatically eligible and fails closed unless an approved override is
  attached.

Rules may also set maximum quantity/fraction, reserve, minimum fee, maximum term, allowed collateral
schedule IDs, recall/voting requirements, or a stricter route capacity.

A `CollateralSchedule` selects borrower/legal agreement, beneficial owner/pool, loaned-security
class, currency, market, and effective interval. It contains:

- accepted collateral asset/cash types and eligible identifiers or classification predicates;
- margin/overcollateralization factor and haircut method;
- haircut buckets by asset type, issuer/country, rating/quality, residual maturity, liquidity,
  currency mismatch, and counterparty where approved;
- valuation source, FX source, stale-price fallback, mark-to-market frequency, and rounding;
- aggregate and per-asset/issuer/country/currency concentration limits;
- wrong-way-risk exclusions and correlation/concentration add-ons;
- available or indicated collateral capacity when the borrower supplies it;
- minimum transfer amount, lot/denomination, substitution rights/cutoffs, and settlement lag;
- reuse/segregation and cash-reinvestment treatment needed for economics; and
- dispute thresholds, cure/grace rules, and operational exceptions where modeled.

No haircut, margin factor, accepted asset type, or legal rule is hard-coded as a universal market
default. The applicable agreement, jurisdiction, counterparty, owner policy, and approved schedule
determine it.

Schedule resolution is deterministic:

1. select versions observed by request `as_of` and effective for the modeled date/time;
2. filter rules whose complete scope matches the route/inventory/collateral candidate;
3. apply safety precedence (`DENY`/`REVIEW` and non-relaxable legal rules before permissive rules);
4. apply configured specificity and explicit priority only within the same authority tier;
5. intersect quantitative hard limits unless an approved override explicitly replaces one; and
6. reject unresolved contradictions, missing approvals, or missing required schedules.

The result retains every matched rule, winning/intersected decision, and rejected override. Existing
loans are never assumed immediately recallable when a new schedule makes them ineligible.

### 9.7 Request contract

```python
class OptimizationRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    as_of: datetime
    effective_date: date
    problem_family: ProblemFamily = ProblemFamily.SECURITIES_LENDING_INVENTORY
    desk_context: DeskContext | None = None
    inventory: tuple[SecurityInventory, ...]
    routes: tuple[LoanRoute, ...]
    demand: tuple[DemandForecast, ...]
    counterparty_limits: tuple[CounterpartyLimit, ...] = ()
    utilization_policies: tuple[UtilizationPolicy, ...] = ()
    eligibility_schedules: tuple[EligibilitySchedule, ...] = ()
    collateral_schedules: tuple[CollateralSchedule, ...] = ()
    constraint_schedules: tuple[ConstraintSchedule, ...] = ()
    beneficial_owner_mandates: tuple[BeneficialOwnerMandate, ...] = ()
    inventory_sources: tuple[InventorySource, ...] = ()
    client_short_demands: tuple[ClientShortDemand, ...] = ()
    external_borrow_quotes: tuple[ExternalBorrowQuote, ...] = ()
    indemnification_policies: tuple[IndemnificationPolicy, ...] = ()
    agreement_netting_sets: tuple[AgreementNettingSet, ...] = ()
    balance_sheet_budgets: tuple[BalanceSheetBudget, ...] = ()
    config_overrides: Mapping[str, JsonValue] = MappingProxyType({})
    metadata: Mapping[str, str] = MappingProxyType({})
```

Implementation may use a frozen mapping helper instead of `MappingProxyType` if serialization
requires it. Mutability must not leak to scenario execution.

Every family still supplies the core `inventory`, `routes`, and `demand` collections. Agency maps
each inventory record to one beneficial owner/pool mandate. Prime maps each inventory record to one
`InventorySource`, each client requirement to a demand group, and each permitted source-to-client
pair to a `LoanRoute`. Family-specific records add authority, lifecycle, economics, aggregation, and
reporting semantics; they do not create an alternate path around the shared balance and route
validators.

### 9.8 Required validation invariants

Before formulation:

1. IDs are unique in their declared scope and all foreign keys resolve.
2. Required timestamps are timezone-aware and meet freshness/common-as-of policy.
3. All quantities and prices are finite; non-negative fields are non-negative.
4. Rates, quantities, and prices use canonical units.
5. Baseline inventory reconciles within tolerance.
6. Sum of current route quantities equals inventory `on_loan_shares` for each pool/security.
7. Current route quantity does not exceed its hard contractual maximum.
8. Term/recall rules are consistent with the effective date.
9. Demand groups do not mix security or borrower IDs.
10. Eligible route inventory and security IDs agree.
11. Counterparty and utilization bounds are ordered correctly.
12. Configuration components and solver capabilities resolve.
13. Schedule versions are observed/effective, approved, non-duplicated, and authority-resolvable.
14. Every route requiring collateral resolves exactly one compatible effective schedule or an
    explicitly permitted intersection.
15. Eligibility actions, quantitative limits, and grandfather/recall timing compile without
    contradiction.
16. Collateral prices, FX, haircuts, margin factors, capacities, and concentration rules have valid
    units and freshness.
17. Request `problem_family`, desk configuration, enabled components, and supplied desk records
    agree; family-specific records are rejected rather than silently ignored.
18. Agency inventory reconciles separately by beneficial owner/pool/security and cannot be
    commingled without explicit legal authority.
19. Prime inventory sources state ownership, reuse/rehypothecation authority, settlement
    availability, priority, capacity, and cost; client assets default to unavailable without
    affirmative permission.
20. External borrow quotes are observed, effective, unexpired for the decision horizon, and mapped
    to an approved lender/agreement.
21. Netting, collateral reuse, indemnification, and balance-sheet aggregation use internally
    approved legal-entity and agreement sets, not inferred vendor relationships.

Validation returns structured issue codes and locations. Public API calls raise one
`InputValidationError` containing all detectable issues rather than failing one field at a time.

---

## 10. Processing Pipeline

```text
request + resolved config
          |
          v
schema validation and point-in-time checks
          |
          v
problem-family, desk-profile, and component resolution
          |
          v
inventory, owner/source, demand, and current-loan reconciliation
          |
          v
scenario overlay (none for baseline)
          |
          v
effective eligibility/collateral/constraint schedule resolution
          |
          v
elasticity-adjusted demand caps and route enrichment
          |
          v
component resolution and sparse formulation compile
          |
          v
solver capability check and solve
          |
          v
independent primal/integrality/objective verification
          |
          v
optional rounding + constrained repair + re-verification
          |
          v
allocation, attribution, explanation, and audit result
```

Every stage takes an immutable input and returns a new typed artifact. The pipeline attaches timing,
row counts, hashes, and warnings to a `RunTrace`; it must not log raw borrower names or full source
records.

---

## 11. Default LP Formulation

### 11.1 Index sets

- `i in I`: inventory records, each representing one pool/security.
- `j in J`: loan routes.
- `J(i)`: routes drawing inventory from inventory record `i`.
- `g in G`: demand groups.
- `J(g)`: routes serving demand group `g`.
- `b in B`: borrowers.
- `J(b)`: routes assigned to borrower `b`.

Each route maps to exactly one inventory record, security, borrower, and demand group.

### 11.2 Scenario-adjusted parameters

For inventory `i`:

- `L_i`: post-trade total lendable shares.
- `R_i`: hard reserved shares.
- `C_i`: committed-out shares.
- `P_i`: USD price per share.
- `u_min_i`, `u_target_i`, `u_max_i`: optional utilization policy levels.

For route `j`:

- `q0_j`: current on-loan shares.
- `lb_j`, `ub_j`: feasible post-state lower and upper quantities.
- `f_j`: annual fee rate.
- `s_j`: lender revenue share.
- `r_j`: net reinvestment rate.
- `h_j`: schedule-derived eligible cash-collateral/notional factor in validate/capacity modes; zero
  when reinvestment economics are modeled from joint collateral decisions.
- `c_j`: annual variable cost rate.
- `k+_j`, `k-_j`: one-time increase and decrease costs in USD/share.
- `e_j`: eligibility indicator applied when bounds are built.

For demand group `g`:

- `D_g`: elasticity- and uncertainty-adjusted maximum demand.

Global:

- `tau`: revenue horizon day fraction.
- `K_b`: optional borrower notional capacity.
- component-specific penalty coefficients for explicitly soft targets.

### 11.3 Decision variables

- `q_j >= 0`: post-state on-loan shares assigned to route `j`.
- `inc_j >= 0`: positive allocation change from baseline.
- `dec_j >= 0`: decrease/recall from baseline.
- `a_i >= 0`: post-state available-to-lend shares.
- `d+_i, d-_i >= 0`: optional utilization-target deviations.
- `m_g >= 0`: optional unmet-demand quantity when service-level attribution is enabled.
- explicitly named slack variables for configured soft constraints only.

Transition identities and tight change bounds:

```text
q_j - q0_j = inc_j - dec_j
0 <= inc_j <= max(ub_j - q0_j, 0)
0 <= dec_j <= max(q0_j - lb_j, 0)
```

With positive transition costs, both `inc_j` and `dec_j` will not be positive at an optimum. The
post-solve verifier checks this and reports degeneracy if both exceed tolerance.

### 11.4 Hard inventory balance

For every inventory record `i`:

```text
sum(q_j for j in J(i)) + a_i = L_i - R_i - C_i
```

This is an equality, not an inequality. It ensures the model neither creates nor loses shares.
Inputs with `L_i - R_i - C_i < 0` are invalid before solve.

### 11.5 Route bounds and eligibility

```text
lb_j <= q_j <= ub_j
```

The bound compiler accounts for legal eligibility, term maturity, recall notice, settlement timing,
inventory ownership, borrower access, and policy. A disabled new route receives `ub_j = 0`. An
ineligible existing loan follows configured grandfather/unwind policy; it is never silently set to
zero if it cannot operationally be recalled.

### 11.6 Demand limits

For every demand group `g`:

```text
sum(q_j for j in J(g)) <= D_g
```

If demand describes only incremental interest rather than total borrower capacity, the adapter must
convert it to a total post-state cap or assign current and incremental quantities to separate groups.
The core model never infers that semantic.

For service-level reporting:

```text
m_g >= D_g - sum(q_j for j in J(g))
```

`m_g` is informational unless a configured objective term or minimum-service constraint uses it.

### 11.7 Utilization policy

Post on-loan for inventory `i` is `O_i = sum(q_j for j in J(i))`.

Hard floor/cap, when configured:

```text
u_min_i * L_i <= O_i
O_i <= u_max_i * L_i
```

A preferred target may be soft:

```text
O_i - u_target_i * L_i = d+_i - d-_i
```

The objective penalizes `d+_i` and/or `d-_i` only when the policy profile assigns a nonzero USD
penalty. The default economics profile sets target penalties to zero and uses the utilization cap as
a safety constraint. This avoids lending uneconomic inventory merely to improve a utilization KPI.

### 11.8 Counterparty and concentration limits

Illustrative borrower notional cap:

```text
sum(P_i(j) * q_j for j in J(b)) <= K_b
```

Optional linear concentration limits can apply by borrower, security, pool, legal entity, priority
class, collateral type, or any precompiled grouping. Components must expose the exact grouping keys
and units in result metadata.

### 11.9 Reserve and liquidity rules

V0 reserves are scenario-adjusted parameters and therefore part of the inventory-balance right-hand
side. Optional policies may require:

```text
a_i >= absolute_buffer_i
a_i >= buffer_fraction_i * L_i
```

If both apply, both rows are added. If a reserve is already deducted from `L_i` by the source
adapter, it must not also appear as `R_i`; the input convention field and reconciliation check guard
against double counting.

### 11.10 Eligibility-schedule constraints

Resolved eligibility rules first tighten route bounds:

```text
ALLOW:        resolved_lb_j <= q_j <= resolved_ub_j
DENY:         q_j = 0 for a new route; existing route follows approved unwind bounds
GRANDFATHER:  resolved_lb_j <= q_j <= q0_j
RECALL_ONLY:  resolved_lb_j <= q_j <= required_recall_ceiling_j
REVIEW:       no automatic recommendation without an approved override
```

A rule can add group limits rather than only a route bound. Examples:

```text
sum(q_j for j in owner_program_p) <= maximum_lend_fraction_p * eligible_inventory_p

sum(P_i(j) * q_j for j in country_or_market_k) <= scheduled_notional_cap_k

a_i >= schedule_reserve_i
```

For an exogenous-fee LP, a route below a hard scheduled minimum fee receives no new capacity; an
existing route follows its repricing/unwind rule. In a fee-tier MIP, disallowed tiers are removed or
their selection binary is fixed to zero. Minimum revenue, exclusive-allocation, borrower-tier,
voting/record-date, prohibited-market, and maximum-term schedules compile into named bounds or rows,
never hidden service-layer conditionals.

The schedule compiler records every rule contributing to each bound/row so the explanation can state
whether inventory, route, borrower, collateral, event, or owner policy caused ineligibility.

### 11.11 Collateral-schedule modes and constraints

Collateral is relevant whenever it changes route legality, capacity, expected economics, credit
exposure, or operational feasibility. Three modes are supported:

1. `validate_only` (V0 default): collateral is allocated externally. The schedule validates route
   compatibility, valuation freshness, margin/haircut coverage, and terms. Failure removes new-route
   capacity or makes a required existing state invalid according to policy.
2. `capacity`: external collateral availability/credit is a parameter. It tightens route or borrower
   capacity while allocation of individual collateral assets remains outside the optimizer.
3. `joint`: the optimizer allocates eligible collateral assets/lots to loan routes alongside shares.

For capacity mode, an approved collateral-credit limit `K_coll_b` yields:

```text
sum(margin_factor_j * P_i(j) * q_j for j in J(b)) <= K_coll_b
```

For joint mode, let `c in C` be collateral lots/types, `y_jc >= 0` be collateral market value
assigned to route `j`, `H_jc` be the total approved haircut including FX/add-ons, and `A_c` be
available collateral market value. Ineligible `(j,c)` pairs are omitted:

```text
sum_c [(1 - H_jc) * y_jc]
    >= margin_factor_j * P_i(j) * q_j                 for every route j

sum_j y_jc <= A_c                                    for every collateral c
```

The canonical range is `0 <= H_jc < 1` for an eligible pair and `margin_factor_j > 0`. Coverage may
be aggregated across routes only within an internally approved agreement/netting set; in that case
the same equation is compiled by netting set rather than individual route, with the grouping recorded.

Illustrative concentration and wrong-way-risk constraints:

```text
sum(y_jc for (j,c) in concentration_bucket_k)
    <= concentration_limit_k * sum(y_jc for (j,c) in concentration_base_k)

y_jc = 0 for prohibited same-issuer, affiliate, currency, country, or wrong-way pairs
```

Where concentration ratios create an awkward or weak formulation, compile the equivalent linear
row using the known schedule limit and total assigned value. Minimum transfer amounts, denominations,
whole collateral lots, and discrete substitutions require MIP. Time-dependent margin calls,
settlement lags, and substitution windows belong in the multi-period model.

Haircut convention is explicit. In the equations above, `H_jc` reduces collateral credit from market
value. If a source represents required overcollateralization instead, the adapter converts it to the
canonical coverage form and preserves the original convention in lineage. Haircuts and margin may
depend on collateral asset risk, exposure, currency mismatch, tenor, liquidity, and counterparty;
there is no universal hard-coded percentage.

In joint mode, cash collateral reinvestment economics are calculated from assigned cash `y_jc`, not
again from route notional, to avoid double counting. In validate/capacity mode, the route-level
reinvestment coefficient remains permissible if it is derived from the resolved schedule.

### 11.12 Objective

The default validate/capacity model maximizes horizon net economics:

```text
maximize
    sum_j [P_i(j) * q_j * tau
           * (f_j * s_j + r_j * h_j - c_j)]
  - sum_j [k+_j * inc_j + k-_j * dec_j]
  - utilization_target_penalties
  - unmet_demand_penalties
  - other explicitly configured linear penalties
```

Equivalent minimization coefficients are passed to HiGHS. All objective components are converted to
USD over the configured horizon before scaling. A component must not combine daily, annual, bps, and
notional units implicitly.

In joint collateral mode, the route term `r_j * h_j` is replaced by registered objective terms over
assigned cash collateral `y_jc` (and, if in scope, its currency, duration, investment eligibility,
liquidity buffer, and reinvestment return). The formulation manifest must prove that exactly one
collateral-income method is active.

The result includes both total post-state economics and delta versus the unchanged baseline. The
unchanged baseline is evaluated through the same objective components, not through a separate P&L
formula.

### 11.13 Lexicographic option

Weighted objectives are the default. A later configuration may request lexicographic passes:

1. Minimize hard-approved policy slack.
2. Maximize net economics while fixing pass-1 slack to its optimum.
3. Minimize churn while preserving economics within a configured tolerance.

Each pass and tolerance must be reported. V0 need not implement lexicographic solving, but interfaces
must not assume exactly one solver call per optimization request.

---

## 12. Demand Elasticity

### 12.1 V0 contract

Elasticity is preprocessing, not an LP decision. For each demand group, the scenario supplies or
implies an evaluated fee `f_g`. The elasticity component calculates `D_g(f_g)` before model build.

Default constant-elasticity curve:

```text
D_raw_g(f_g) = Q_ref_g * (max(f_g, fee_floor) / F_ref_g) ^ (-epsilon_g)

D_g = clip(
    D_raw_g(f_g) - uncertainty_haircut_sigma * forecast_std_g,
    lower=0,
    upper=hard_max_g if supplied else +infinity,
)
```

For `epsilon_g > 0`, a higher fee reduces demand. `epsilon_g = 0` means price-insensitive demand.
Negative elasticity magnitudes are invalid. A fee at or below zero requires an explicit alternative
curve or the configured positive floor; it may not enter the power formula directly.

Optional semi-log curve:

```text
D_raw_g(f_g) = Q_ref_g * exp(-beta_g * (f_g - F_ref_g))
```

### 12.2 Rate aggregation rule

All routes in one LP demand group must share the evaluated borrower fee, or the adapter must provide
a group-level fee used only for demand. Lender revenue shares may still produce different net route
economics. If route rates imply genuinely different borrower price choices, use distinct demand
groups or the discrete pricing MIP.

### 12.3 Missing and uncertain elasticity

The policy must select one behavior:

- `reject`: required estimate missing is an input error.
- `zero`: assume demand is rate-insensitive.
- `conservative_default`: use a configured non-negative default and add a warning.
- `external_cap_only`: ignore a curve and accept a supplied hard demand cap.

Every fallback is recorded per demand group. Estimated uncertainty may haircut demand or generate
scenarios; it must not silently change the fee rate.

### 12.4 Discrete price-selection MIP

For candidate fee tiers `k in K(g)`:

- binary `z_gk` selects a price tier;
- continuous `q_gk` is allocated quantity at that tier;
- precomputed `D_gk = D_g(f_gk)` is the tier capacity.

```text
sum_k z_gk <= 1
0 <= q_gk <= D_gk * z_gk
route allocations at tier k sum to q_gk
```

The objective uses `f_gk * q_gk`. Because each `f_gk` is a constant, the formulation is linear MIP.
Tier ordering and one-price-per-group behavior must be explicit; the optimizer may not allocate the
same borrower demand at multiple mutually exclusive prices.

### 12.5 Future joint nonlinear pricing

Continuous fee `f_g` and quantity `q_g = D_g(f_g)` create a nonlinear revenue term `f_g * q_g`.
This belongs in an optional nonlinear formulation or a documented sequential/piecewise
approximation. It must not be disguised as an LP.

---

## 13. Trade and What-If Scenarios

### 13.1 Scenario model

```python
class Scenario(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    scenario_id: str
    name: str
    trade_events: tuple[TradeEvent, ...] = ()
    rate_shocks: tuple[RateShock, ...] = ()
    demand_shocks: tuple[DemandShock, ...] = ()
    inventory_shocks: tuple[InventoryShock, ...] = ()
    policy_overrides: tuple[PolicyOverride, ...] = ()
    schedule_overlays: tuple[ScheduleOverlay, ...] = ()
    collateral_shocks: tuple[CollateralShock, ...] = ()
    desk_events: tuple[DeskScenarioEvent, ...] = ()
    metadata: Mapping[str, str] = MappingProxyType({})
```

Every `TradeEvent` contains `event_id`, `event_type`, `security_id`, source or destination
`inventory_pool_id` as applicable, non-negative `quantity_shares`, trade/effective/settlement dates,
and a source/version reference. `RETURN` and `RECALL` also require a `route_id`; `NEW_LOAN` requires
a candidate route and demand reference. BUY/SELL may include `trade_price_usd` for context, but that
price is not part of the lending objective. Direction comes from `event_type`; signed input
quantities are rejected.

Allowed `TradeEvent` types:

- `BUY`: increases eligible lendable quantity on/after settlement.
- `SELL`: decreases lendable quantity and may require recalls.
- `TRANSFER_IN`: adds quantity if the destination pool is eligible.
- `TRANSFER_OUT`: removes quantity from the source pool.
- `NEW_LOAN`: adds or changes a candidate route/demand cap, not supply.
- `RETURN`: reduces a specified current route baseline before optimization.
- `RECALL`: lowers a specified route maximum or current quantity according to effective timing.

Rate, demand, inventory, and policy shocks are separate typed overlays so a fee shock cannot be
mistaken for a booked trade.

Schedule overlays may activate a future approved schedule version, expire a rule, or apply a named
eligibility/collateral stress. They cannot invent an unapproved permissive rule. Collateral shocks
may change valuation, FX, haircut add-on, eligible capacity, concentration, substitution timing, or
settlement delay; the baseline schedule remains immutable.

Desk events are typed and family-gated. Agency events include owner contribution/withdrawal,
mandate/panel/exclusive/fee-split change, indemnification stress, and owner recall. Prime events
include client short/cover, locate conversion/cancellation, source recall, external quote
expiry/repricing, client-reuse authority loss, affiliate/funding/capital change, and fail/buy-in.

### 13.2 Timing semantics

- Only events effective by the request `effective_date` alter V0 supply or route state.
- Later events are retained in scenario metadata but do not affect a single-period solve.
- A sell before a loan can be recalled is infeasible unless unloaned supply and buffers cover it.
- Buy/transfer quantities enter `total_lendable` only if settled and eligible.
- Conflicting overlays on the same field are rejected unless explicit ordered composition is enabled.
- Schedule versions are selected using both scenario effective time and request observation time;
  a scenario cannot use a schedule revision not known at `as_of` unless explicitly labeled as a
  forward stress rather than a historical fact.

### 13.3 Overlay algorithm

1. Validate the scenario independently.
2. Clone the baseline through immutable model-copy semantics.
3. Sort effective events deterministically by effective time, type priority, and event ID.
4. Apply supply, source, client/owner, and route state changes allowed by the selected family.
5. Apply rate/demand shocks.
6. Resolve eligibility, collateral, fee, settlement, and other constraint schedules.
7. Apply allowed policy/schedule/collateral overrides.
8. Re-run complete request validation and reconciliation.
9. Solve and compare with the already-computed baseline.

### 13.4 Required comparison output

For each scenario:

- normalized status and feasibility;
- objective and net-revenue delta;
- post total lendable, on-loan, available, and utilization delta;
- allocation delta by route/security/pool/borrower;
- required recalls and lost existing-loan revenue;
- new allocations and incremental revenue;
- unfilled demand delta;
- changed binding constraints and slacks;
- changed demand caps with elasticity attribution;
- changed eligibility decisions, matched schedule rules, collateral coverage/capacity, and
  concentration headroom;
- agency owner/mandate/indemnification/fairness deltas or prime client/source/internalization/
  replacement-cost/balance-sheet deltas when enabled;
- trade economics separate from lending economics;
- warnings, relaxations, runtime, and config/scenario hashes.

Trade price P&L is out of scope; a proposed buy/sell changes supply. The report may show the trade
notional as context but must not combine it with lending revenue.

---

## 14. MIP, QP, and Nonlinear Extensions

### 14.1 MIP triggers

Use MIP only when requested policy requires discrete variables:

- all-or-none fill;
- minimum active ticket;
- integer shares or lot multiples;
- fixed route activation cost;
- maximum active route count;
- mutual exclusion;
- one fee tier per demand group.

Typical activation constraints:

```text
q_j <= ub_j * z_j
q_j >= min_ticket_j * z_j
sum_j z_j <= max_active_routes
z_j in {0, 1}
```

Lot-size modeling uses integer lot variables, not rounded continuous results, when exact compliance
is required.

### 14.2 Convex QP extensions

Candidate convex terms include:

- squared deviation from current allocations;
- borrower/security concentration penalty;
- covariance-weighted revenue or recall risk;
- smooth deviations from utilization targets.

QP matrices must be symmetric and positive semidefinite within tolerance. The compiler reports any
regularization added. Continuous QP support is backend/version capability-gated. Mixed-integer
quadratic behavior requires a separate capable backend or an explicitly documented decomposition;
it must never be labeled globally optimal when it is not.

### 14.3 Piecewise-linear extensions

Prefer piecewise-linear approximations when they preserve acceptable accuracy for:

- tiered operating costs;
- convex utilization penalties;
- recall-cost curves;
- demand/revenue curves with fixed breakpoints.

The model records breakpoints, approximation error bounds, and whether SOS/integer variables were
introduced.

### 14.4 Nonlinear extensions

Use a separate `NonlinearSolverBackend` capability for:

- continuous joint fee/quantity optimization;
- nonconvex relationship utility;
- nonlinear fail/recall probability costs;
- other differentiable nonlinear constraints.

Optional approaches include a true NLP backend, sequential convex approximation, or decomposition.
Every nonlinear mode needs convergence criteria, initialization policy, maximum iterations, a
feasible fallback, and a result status that distinguishes local from global optimality.

### 14.5 Extension compatibility rule

An extension may add fields and result metadata but must preserve:

- the canonical inventory balance;
- request immutability;
- normalized status semantics;
- objective attribution;
- independent verification;
- scenario isolation; and
- the public `optimize`/`run_scenarios` facade.

---

## 15. Component and Decorator System

Decorators register stateless component classes with immutable metadata. Registration occurs at
module import, but component instances are constructed explicitly from resolved configuration.

```python
@problem_family(
    name="securities_lending_inventory",
    version="1",
    supported_formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
)
class SecuritiesLendingInventoryProblem(ProblemFamily):
    request_type = OptimizationRequest
    result_type = OptimizationResult


@constraint_component(
    name="inventory_balance",
    version="1",
    formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
    hard=True,
)
class InventoryBalanceConstraint(ConstraintComponent):
    def contribute(self, context: BuildContext, builder: ModelBuilder) -> None:
        ...


@objective_component(
    name="fee_revenue",
    version="1",
    formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
)
class FeeRevenueTerm(ObjectiveComponent):
    def contribute(self, context: BuildContext, builder: ModelBuilder) -> None:
        ...


@solver_backend(
    name="highs",
    capabilities={Capability.LP, Capability.MIP, Capability.CONTINUOUS_QP},
)
class HighsBackend(SolverBackend):
    ...
```

### 15.1 Decorator requirements

- Reject duplicate `(kind, name, version)` registrations.
- Preserve the decorated class and type information.
- Store no mutable global component instances.
- Require each problem family to declare its request/result contracts and default component set.
- Declare formulations, required inputs, produced variables/rows, and capability requirements.
- Expose a manifest for audit and documentation.
- Support explicit test registries so tests do not mutate process-global production state.
- Never execute solver or I/O work inside a decorator.

### 15.2 Component interfaces

```python
class ConstraintComponent(Protocol):
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: BuildContext, builder: ModelBuilder) -> None: ...


class ObjectiveComponent(Protocol):
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: BuildContext, builder: ModelBuilder) -> None: ...
    def attribute(self, solution: VerifiedSolution) -> ObjectiveAttribution: ...
```

Component ordering is deterministic: hard structural constraints, configured policy constraints,
objective terms, then formulation-specific auxiliaries. Components may depend on named variables,
but circular dependencies are rejected during manifest resolution.

---

## 16. Formulation and Solver Interfaces

### 16.1 Compiled problem

```python
@dataclass(frozen=True)
class CompiledProblem:
    formulation: Formulation
    objective_sense: ObjectiveSense
    linear_objective: NDArray[np.float64]
    quadratic_objective: SparseMatrix | None
    constraint_matrix: SparseMatrix
    row_lower: NDArray[np.float64]
    row_upper: NDArray[np.float64]
    variable_lower: NDArray[np.float64]
    variable_upper: NDArray[np.float64]
    integrality: NDArray[np.int8]
    variable_index: VariableIndex
    row_index: RowIndex
    scaling: ScalingMetadata
    manifest: ComponentManifest
```

Use CSR/CSC sparse matrices. No component may assemble a dense matrix proportional to routes x
constraints. `VariableIndex` and `RowIndex` provide reversible mappings between domain IDs and
solver positions.

### 16.2 Solver protocol

```python
class SolverBackend(Protocol):
    @property
    def capabilities(self) -> frozenset[Capability]: ...

    def solve(
        self,
        problem: CompiledProblem,
        options: SolverOptions,
        warm_start: SolverWarmStart | None = None,
    ) -> SolverResult: ...
```

`SolverResult` includes:

- normalized status;
- primal vector and optional duals/reduced costs;
- objective value in scaled and unscaled units;
- best bound and relative gap when applicable;
- runtime, iterations, nodes, and termination reason;
- backend name/version and effective options;
- native status string preserved only as diagnostic metadata.

### 16.3 Normalized statuses

```text
OPTIMAL
FEASIBLE_LIMIT
INFEASIBLE
UNBOUNDED
INFEASIBLE_OR_UNBOUNDED
INVALID_MODEL
NUMERICAL_ERROR
INTERRUPTED
SOLVER_ERROR
```

`FEASIBLE_LIMIT` requires a verified incumbent and includes the gap/bound if available. It must not
be promoted to `OPTIMAL`. Results without a feasible primal vector do not produce allocation
recommendations.

### 16.4 HiGHS adapter

The HiGHS adapter owns all `highspy` imports and:

1. checks required capabilities against the installed/pinned backend;
2. creates columns, sparse rows, bounds, objective coefficients, integrality, and optional Hessian;
3. applies allow-listed solver options;
4. executes the model;
5. translates native status to normalized status;
6. extracts primal/dual/bound/gap diagnostics where available;
7. returns no mutable HiGHS model object to callers.

The initial acceptance target is LP and linear MIP. Continuous convex QP is enabled only after a
pinned-version capability test. Generic NLP and mixed-integer nonlinear/quadratic claims are outside
the HiGHS adapter unless the pinned backend proves them in tests.

### 16.5 Determinism

- Pin dependencies and record backend version.
- Set seed and thread count where supported.
- Sort IDs before building indexes.
- Use deterministic component order.
- Serialize floats consistently for hashes.
- Golden tests compare allocations/objectives within tolerance, not raw native logs.

---

## 17. Public API and Services

### 17.1 Stable facade

```python
from inventory_optimizer import InventoryOptimizer, load_config

config = load_config(
    environment="production",
    desk="inventory_core",
    formulation="lp",
    objective="net_revenue",
    policy="standard",
)

optimizer = InventoryOptimizer(config=config)
result = optimizer.optimize(request)

comparison = optimizer.run_scenarios(
    ScenarioBatchRequest(baseline=request, scenarios=tuple(scenarios))
)
```

Agency and prime invocations select `desk="agency"` or `desk="prime"` and submit matching
family-specific records through the same `InventoryOptimizer` facade. The configured family must
equal the request family.

`InventoryOptimizer` is a thin facade over injected validators, elasticity service, formulation
compiler, solver backend, verifier, and reporter. It is safe to construct once and call repeatedly;
individual calls hold no shared mutable model state.

### 17.2 Service interfaces

```python
class OptimizationService(Protocol):
    def optimize(self, request: OptimizationRequest) -> OptimizationResult: ...


class ScenarioService(Protocol):
    def run(self, request: ScenarioBatchRequest) -> ScenarioComparison: ...


class ExplanationService(Protocol):
    def explain(self, result: OptimizationResult) -> OptimizationExplanation: ...
```

### 17.3 CLI

```text
inventory-optimizer validate --request request.json --config run.yaml
inventory-optimizer optimize --request request.json --config run.yaml --output result.json
inventory-optimizer scenarios --request batch.json --config run.yaml --output comparison.json
inventory-optimizer components
inventory-optimizer doctor
```

CLI writes machine-readable output to the requested file/stdout and diagnostics to stderr. Exit
codes distinguish success, invalid input, infeasible model, feasible-limit result, and internal or
solver errors.

### 17.4 QR Haven platform adapter

The initial integration adapter at `src/qr_haven/integrations/inventory_optimizer.py`:

- convert QR Haven securities-lending features into demand/inventory fields;
- consume QR Haven borrow-demand forecasts and calibrated rate assumptions;
- load approved eligibility, collateral, agreement, owner, client, source, and limit schedules;
- pass an opaque invocation context containing platform tenant, actor, authorization decision,
  correlation ID, and idempotency key;
- translate optimizer results into QR Haven reporting/terminal contracts; and
- route verified results to the platform's persistence and approval workflow without creating an
  executable instruction.

It may depend on both projects. The standalone core must not import the adapter or QR Haven. The
adapter cannot bypass canonical validation, schedule resolution, solver-status normalization, or
independent verification.

### 17.5 Platform invocation contract

The same facade supports three deployment shapes: in-process library call, platform worker/job, or
versioned service endpoint. Deployment shape cannot change model semantics. Each invocation carries
`request_id`, `correlation_id`, `idempotency_key`, requested problem family, decision `as_of`,
platform authorization decision/reference, and request schema version. The optimizer:

- treats authorization as an input assertion from the platform and does not implement user RBAC;
- rejects reuse of an idempotency key with a different canonical request/config hash;
- returns the same completed result for a valid duplicate when the injected result cache supports
  it;
- cooperatively honors cancellation and time budgets while preserving accurate normalized status;
- emits a versioned result envelope independent of platform UI/storage schemas; and
- never reads platform databases, global process state, or user sessions directly.

The platform owns authentication, authorization, entitlements, scheduling, retries, persistence,
encryption, user presentation, downstream approvals, and operational recovery. The optimizer owns
mathematical reproducibility and supplies sufficient hashes for the platform to detect stale or
superseded results.

---

## 18. Result, Attribution, and Explainability

### 18.1 `OptimizationResult`

Required sections:

| Section | Contents |
| --- | --- |
| Identity | request/run IDs, timestamps, config/input hashes, package/backend versions |
| Status | normalized/native status, strict/repaired flag, termination reason |
| Allocations | route current, post, increase, decrease, fee, demand cap, eligibility |
| Balances | pre/post lendable, reserved, committed, on-loan, available, utilization |
| Economics | fee, reinvestment, variable costs, transition costs, penalties, total/delta USD |
| Demand | raw/effective cap, elasticity inputs, filled/unfilled, fill ratio |
| Schedules | matched/resolved rules, actions, limits, versions, owners, approvals, conflicts |
| Collateral | mode, eligible assignments, market/credit value, haircut, margin, capacity, concentration |
| Desk | problem family, desk/legal entity, owner/client attribution, enabled family components |
| Sources | owned/client/affiliate/external capacity used, cost, authority, and unused alternatives |
| Constraints | bounds, activity, slack, dual/shadow price when reliable |
| Solver | runtime, iterations/nodes, gap/bound, options, scaling |
| Verification | max violations, objective reconstruction delta, integrality checks |
| Warnings | fallbacks, stale optional inputs, approximations, relaxations |
| Platform | request/correlation/idempotency references, schema version, authorization reference |

### 18.2 Objective attribution

Each objective component recomputes its unscaled USD value from domain allocations. The sum must
match the verified solver objective within configured tolerance. Attribution includes total
post-state value and delta versus unchanged baseline.

### 18.3 Decision explanations

For every material route change, expose reason codes based on deterministic evidence:

- `HIGHER_NET_FEE`
- `DEMAND_CAP_BINDING`
- `INVENTORY_SCARCE`
- `UTILIZATION_CAP_BINDING`
- `RESERVE_BINDING`
- `COUNTERPARTY_LIMIT_BINDING`
- `INELIGIBLE_ROUTE`
- `TERM_OR_RECALL_RESTRICTION`
- `TRANSITION_COST_EXCEEDS_UPLIFT`
- `TRADE_REDUCED_SUPPLY`
- `ELASTICITY_REDUCED_DEMAND`
- `SOFT_TARGET_TRADEOFF`
- `ELIGIBILITY_SCHEDULE_BOUND`
- `COLLATERAL_SCHEDULE_MISMATCH`
- `COLLATERAL_CAPACITY_BINDING`
- `COLLATERAL_CONCENTRATION_BINDING`
- `OWNER_MANDATE_BOUND`
- `AGENCY_FAIRNESS_TRADEOFF`
- `INDEMNIFICATION_COST`
- `SOURCE_CAPACITY_BINDING`
- `EXTERNAL_BORROW_SELECTED`
- `CLIENT_REUSE_NOT_AUTHORIZED`
- `HARD_COVERAGE_REQUIREMENT`
- `BALANCE_SHEET_LIMIT_BINDING`

Explanations are derived from coefficients, bounds, slacks, and allocation deltas. They must not rely
on generated prose to establish correctness. A renderer may turn the structured reasons into text.

### 18.4 Shadow prices

For continuous LP results, report dual values when the backend provides them and verification
passes. Label them with objective scaling and sign convention. Do not report LP duals as valid MIP
shadow prices; optionally re-solve a fixed-integer LP for local sensitivity and label it accordingly.

---

## 19. Infeasibility and Repair Policy

### 19.1 Strict solve first

The normal service always builds and solves the strict configured model. It never weakens an
inventory equality, legal eligibility rule, term restriction, or hard counterparty limit.

### 19.2 Diagnostics

On infeasibility, return or raise a structured result containing:

- failing pre-solve balance checks, if any;
- solver infeasibility status;
- irreducible/inconsistent row information if available;
- likely conflicting row groups from a diagnostic feasibility model;
- conflicting/expired eligibility rules or deficient collateral coverage/capacity where applicable;
- minimum additional inventory or limit change suggested by named diagnostic slacks;
- scenario events most directly involved.

### 19.3 Explicit repair mode

If `repair_policy` is explicitly enabled, a second model may soften only allow-listed constraints in
this default order:

1. utilization target;
2. service-level target;
3. internal concentration preference;
4. internal reserve above the non-relaxable legal minimum.

Inventory balance, non-negative availability, legal/schedule eligibility, required collateral
coverage, effective settlement, and hard counterparty/legal limits are never relaxed. The result is
labeled `repaired`, lists every slack and penalty, and is not represented as the strict optimum.

---

## 20. Efficiency and Scale

### 20.1 Engineering requirements

- Vectorize coefficient generation after domain validation.
- Build matrices in coordinate form and convert once to the backend-preferred sparse format.
- Avoid dataframe row iteration in formulation code.
- Reuse stable index maps and matrix structure across compatible scenarios.
- Change only right-hand sides, bounds, or objective coefficients when a scenario permits safe
  incremental model reuse.
- Cache elasticity evaluation by `(demand_version, rate, config_hash)` within one batch.
- Cache only schedule resolutions whose request-as-of/effective date, rule versions, approvals, and
  scope keys match exactly; invalidate them on amendment/cancellation.
- Keep independent scenario result objects even if compiled structure is shared.
- Bound logs and diagnostics; never serialize a solver model by default.

### 20.2 Initial benchmark shapes

Benchmarks should cover:

| Profile | Inventory/source rows | Routes/source-client arcs | Demand groups | Owners/clients | Scenarios |
| --- | ---: | ---: | ---: | ---: | ---: |
| Small/golden | 10 | 50 | 20 | 5 | 5 |
| Core desk | 5,000 | 50,000 | 20,000 | 1,000 | 25 |
| Agency desk | 10,000 | 100,000 | 30,000 | 2,000 owners | 25 |
| Prime desk | 10,000 | 150,000 | 40,000 | 5,000 clients | 25 |
| Stress | 20,000 | 250,000 | 100,000 | 10,000 | 100 |

Performance gates are established from repeatable CI/reference-hardware baselines after Phase 1.
The initial design target is linear memory in variables plus nonzeros and no dense route-by-route
matrix. Scenario batching must record compile time separately from solve time.

### 20.3 Numerical scaling

- Optimize quantities in configurable share or thousand-share scale.
- Normalize USD objectives by `objective_scale_usd` before solve.
- Avoid coefficients spanning excessive orders of magnitude.
- Store both scaled and original values in `ScalingMetadata`.
- Verify the unscaled economic objective independently.
- Warn on near-zero prices/rates or extreme big-M bounds.

---

## 21. Observability, Audit, and Data Handling

### 21.1 Run audit envelope

Every call records:

- run/request/scenario, platform correlation, and idempotency IDs;
- problem family, desk profile, request/result schema version, and authorization reference;
- UTC start/end and stage timings;
- input/config/component/model hashes;
- resolved schedule/rule, approval, and collateral valuation/version hashes;
- record counts and validation issue counts;
- formulation dimensions and nonzero count;
- solver/backend version, status, options, and diagnostics;
- verification summary;
- result hash and output location if persisted.

### 21.2 Structured metrics

At minimum:

- request and scenario count by status;
- validation/infeasibility rate;
- compile and solve latency distributions;
- variables, rows, nonzeros, MIP nodes/gap;
- objective and net-revenue delta;
- utilization, unfilled demand, recalls, and slack totals;
- owner/client/source allocations, internalization/external sourcing, and desk-specific cost totals
  when their family is enabled;
- verifier failures and backend errors.

### 21.3 Data controls

- Use pseudonymous borrower and inventory-pool IDs.
- Do not log raw input rows or borrower names.
- Redact fields marked sensitive before audit serialization.
- Keep audit output append-only at the adapter layer.
- Include model/data lineage without embedding proprietary upstream datasets.
- Treat optimizer output as a recommendation requiring downstream authorization; V0 has no execution
  capability.

---

## 22. Bloomberg-Enriched Realism and Model Extensions

### 22.1 Scope and source-of-truth rule

Assume the project has licensed, programmatic access to appropriate Bloomberg reference, pricing,
event, fund/holdings, entity, and liquidity datasets. Bloomberg documents its reference-data scope
as including terms and conditions, legal entities, corporate actions, classifications, holdings,
ownership, and exchange/contributed pricing. Its real-time feed documentation also describes
instrument identifiers, market depth, normalized security status, and end-of-day reference prices.
Those categories can substantially improve the optimizer, but entitlements and precise available
fields must be confirmed in the firm's data catalog before implementation:

- [Bloomberg Reference Data](https://professional.bloomberg.com/products/data/enterprise-catalog/reference/)
- [Bloomberg Real-Time Market Data Feed](https://professional.bloomberg.com/products/data/enterprise-catalog/real-time-data-feed/)
- [Bloomberg Event-Driven Feeds](https://professional.bloomberg.com/products/data/enterprise-catalog/event-driven-feeds/)
- [Bloomberg Funds Data](https://professional.bloomberg.com/products/data/enterprise-catalog/funds/)
- [Bloomberg Liquidity Assessment](https://professional.bloomberg.com/products/risk/lqa/)

Vendor data enriches the decision but does not become authoritative for firm-owned positions,
contractual loan terms, beneficial-owner restrictions, approved counterparties, limits, or actual
locate/loan activity.

| Data domain | Authoritative source | Bloomberg role | Optimizer treatment |
| --- | --- | --- | --- |
| Gross inventory and on-loan book | Custodian/agent-lender books and records | Identifier/reference enrichment | Hard reconciled input |
| Existing loan economics and term | Loan transaction/contract system | Market context only | Hard route state and coefficients |
| Beneficial-owner and legal eligibility | Internal legal/compliance master | Classification/regulatory enrichment | Hard constraint after internal approval |
| Counterparty exposure and limits | Internal credit/risk system | LEI/entity hierarchy enrichment | Internal limit aggregated on resolved hierarchy |
| Borrower demand and elasticity | Locate/loan history and demand models | Market, event, ownership, and peer features | Forecast input with lineage/uncertainty |
| Security identity and terms | Internal security master reconciled to Bloomberg | FIGI/entity/market/terms enrichment | Point-in-time canonical mapping |
| Price, FX, volume, status, volatility | Approved market-data source | Primary or secondary market enrichment | Objective/risk parameter with freshness checks |
| Corporate actions and events | Approved operations feed | Early-warning and enrichment source | Bounds, scenarios, and event-risk coefficients |
| Market liquidity analytics | Internal realized trades plus approved vendor analytics | Liquidity cost/horizon and stress input | Buffer, transition cost, or scenario input |

If an internal and Bloomberg value conflict, the adapter emits a reconciliation exception or a
configured override record. It never silently chooses one.

### 22.2 Bloomberg adapter boundary

Do not place Bloomberg field mnemonics in domain or formulation code. Add the following optional
structure to the standalone project:

```text
projects/inventory_optimizer/
├── configs/
│   └── data_sources/
│       ├── bloomberg.example.yaml
│       ├── field_mapping.example.yaml
│       └── freshness_policy.yaml
└── src/inventory_optimizer/
    ├── domain/
    │   ├── reference.py
    │   ├── events.py
    │   ├── liquidity.py
    │   └── lineage.py
    ├── ports/
    │   ├── reference_data.py
    │   ├── market_data.py
    │   ├── corporate_actions.py
    │   ├── entity_data.py
    │   └── liquidity_data.py
    ├── enrichment/
    │   ├── security_master.py
    │   ├── event_features.py
    │   ├── liquidity_features.py
    │   ├── entity_hierarchy.py
    │   └── point_in_time.py
    └── adapters/
        └── bloomberg/
            ├── __init__.py
            ├── client.py
            ├── field_mapping.py
            ├── reference.py
            ├── pricing.py
            ├── corporate_actions.py
            ├── events.py
            ├── funds.py
            ├── entities.py
            └── liquidity.py
```

The port contracts describe business concepts; `field_mapping.py` maps licensed vendor fields into
those contracts. The mapping is configuration-versioned and includes unit conversion, null policy,
effective-time semantics, and entitlement identifier. Tests use synthetic responses and never
redistribute proprietary payloads.

### 22.3 Point-in-time data model

Every enriched value must carry:

```python
@dataclass(frozen=True)
class PointInTimeValue(Generic[T]):
    value: T
    observed_at: datetime          # when the firm received it
    effective_from: datetime       # when it applies economically
    effective_to: datetime | None
    source: str
    source_version: str
    field_mapping_version: str
    quality: DataQuality
```

For backtests, join on both economic effective time and knowledge/observation time. A corporate
action correction received tomorrow must not appear in yesterday's simulated decision. Current
solves use the latest observation known at `request.as_of`, subject to freshness and future-effective
event rules.

Required enriched contracts:

- `SecurityReference`: canonical internal ID, FIGI or other licensed identifiers, issuer ID, share
  class, instrument type, primary/listing markets, currency, country of risk, trading/settlement
  status, lot/tick conventions, and effective interval.
- `EntityRelationship`: entity/LEI identifiers, parent and ultimate-parent IDs, relationship type,
  ownership confidence, and effective interval.
- `CorporateActionEvent`: event ID/type/status, announcement/updated/effective/record/ex/pay dates,
  affected security IDs, terms, election deadline, and cancellation/supersession lineage.
- `MarketState`: price and type, FX, volume/ADV, spread, volatility, market depth or approved proxy,
  trading status, and quality/freshness.
- `LiquidityEstimate`: size, horizon, expected cost, stressed cost or percentile, model/source
  version, and as-of time.
- `FundHolding`: fund/ETF ID, component security, weight/shares, AUM context, effective date, and
  publication/observation time.
- `MarketCalendar`: market, currency, trading and settlement dates, cutoffs, and exceptional
  closures.

Identifiers are mappings, not immutable truths. Mergers, ticker changes, share-class changes, ADR
program changes, and vendor remaps are represented by effective-dated relationships; history is not
rewritten.

### 22.4 High-value enrichment map

| Enrichment | Examples of normalized inputs | Model use | First formulation |
| --- | --- | --- | --- |
| Security master | Stable IDs, share class, currency, market, country, status | Prevent wrong-security netting; eligibility and units | Pre-solve validation/LP bounds |
| Settlement/calendar | Market holidays, settlement convention, cutoffs, status | Decide whether buys, sells, transfers, or recalls are effective | LP scenario bounds; later multi-period LP |
| Corporate actions | Dividend, split, merger, tender, rights, spinoff, meeting/vote dates | Recall window, manufactured-payment/tax cost, quantity transformation, event reserve | LP coefficients/bounds and scenarios; MIP for elections |
| Legal-entity hierarchy | Issuer/borrower parent, ultimate parent, LEI, relationship dates | Aggregate counterparty limits and connected exposure | LP grouping constraints |
| Classification | Sector, industry, country, asset/security type | Concentration limits and peer priors | LP constraints; QP risk groups |
| Price and FX | Approved close/mid, currency pairs, quality flags | Notional, revenue, limits, comparisons | LP coefficients |
| Tradability and market status | Active/halted/suspended/delisted status | Disable routes or increase reserve/risk | LP bounds/scenarios |
| Volume, spread, depth, volatility | ADV, spread, realized/implied volatility, depth proxy | Recall/sale liquidity cost and available buffer | LP/PWL; QP or scenario risk |
| Liquidity analytics | Size/horizon cost, stressed cost, liquidation horizon | Scenario-specific unwind cost and liquidity reserve | PWL LP/MIP or scenario input |
| Funds/ETF holdings | Constituent weights, AUM, ownership, effective dates | Passive-flow demand, creation/redemption pressure, crowded supply | Forecast features/scenarios |
| Shares/float/ownership | Shares outstanding, free float, ownership concentration | Market-wide scarcity and capacity sanity checks | Forecast/robust caps |
| Event calendars | Earnings, shareholder meetings, index changes where licensed | Demand, volatility, recall, and fee-regime scenarios | Forecast features/scenarios |

The exact Bloomberg product and field availability is deployment-specific. The adapter's
`doctor` command must list required business concepts, mapped fields, entitlements, last successful
observation, and unavailable optional concepts without exposing credentials.

### 22.5 Realistic economic coefficients

V0 assumes approved post-state quantity remains active through the whole horizon. A more realistic
linear coefficient accounts for take-up, loan survival, and route availability:

```text
expected_active_fraction_j
  = take_up_probability_j
    * conditional_expected_days_active_j / planning_horizon_days

expected_fee_revenue_j
  = P_i(j) * q_j * tau
    * expected_active_fraction_j
    * (f_j * s_j + r_j * h_j)
```

Add the following independently calibrated terms:

- `take_up_probability`: probability an indicated/located quantity becomes an actual loan.
- `return_hazard`: borrower return probability and expected loan survival by route and regime.
- `repricing_hazard`: probability and expected effect of an open-loan rate change.
- `recall_failure_probability`: chance shares are unavailable by the required settlement date.
- `manufactured_payment_cost`: expected dividend/tax/friction cost during the horizon.
- `indemnification_capital_cost`: route/pool-specific capital charge where applicable.
- `settlement_fail_cost`: expected operational/buy-in cost under approved policy assumptions.
- `relationship_value_or_cost`: controlled, reviewable coefficient rather than an undocumented
  trader override.

These remain linear when estimated before solve. Each coefficient carries model version,
calibration date, uncertainty, and a switch allowing the simpler contractual value for controlled
comparison.

### 22.6 Censored and endogenous demand

Observed loans and approved locates understate unconstrained demand when inventory or limits bind.
Observed fees are also endogenous: desks raise rates when names become scarce. A realistic demand
pipeline should therefore:

1. train on requested quantity, rejected/partial locates, cancellations, and realized loan take-up;
2. mark observations censored by inventory, counterparty, or policy limits;
3. estimate borrower/security elasticity with hierarchical shrinkage toward sector, liquidity,
   country, and fee-regime peers;
4. use point-in-time market, ownership, event, and utilization features;
5. separate forecast uncertainty from residual execution/no-show uncertainty;
6. backtest against realized unconstrained proxies and avoid using optimizer outcomes as labels
   without selection-bias controls; and
7. expose conservative quantiles, not just a mean forecast.

Bloomberg classifications, issuer/security relationships, ownership, events, and market state are
especially valuable for cold-start peer groups. Internal locate and loan history remains the target
and primary behavioral source.

For V0, the optimizer consumes fixed quantiles/caps. A later joint demand-price model must address
price endogeneity with an approved causal or instrumental-variable design; a high in-sample fit is
not enough.

### 22.7 Dynamic availability and liquidity buffers

A flat reserve percentage ignores market depth, pending trades, events, and recall timing. Replace or
supplement it with a precomputed dynamic buffer:

```text
required_buffer_i = max(
    legal_minimum_i,
    pending_settlement_need_i,
    demand_uncertainty_quantile_i,
    event_recall_buffer_i,
    liquidity_horizon_buffer_i,
)

a_i >= required_buffer_i
```

Candidate inputs include ADV, market depth or approved proxies, spread, volatility, security status,
liquidation horizon/cost, ownership concentration, corporate-action proximity, and expected trade
settlements. Because the buffer is computed before solve, the default remains an LP.

A more precise version represents a convex cost of recall/sale size with piecewise-linear segments:

```text
recall_or_sale_cost_i(v_i) = PWL_i(v_i; size/horizon/cost knots)
```

Use approved vendor analytics as one input and recalibrate against the firm's realized recalls,
fails, and execution costs. Never treat a vendor estimate as a guaranteed executable price or
horizon.

### 22.8 Corporate-action-aware allocation

Corporate actions can change both economics and the number or identity of lendable shares. The
scenario compiler must classify each event:

| Event behavior | Examples | Required model action |
| --- | --- | --- |
| Quantity transformation | Splits, consolidations, some distributions | Transform inventory/routes on effective date and preserve pre/post lineage |
| Cash-flow adjustment | Dividends and distributions | Add manufactured-payment, tax, or rebate economics from approved rules |
| Election/consent | Tenders, rights, voluntary reorganizations | Reserve/elect quantities; use MIP only if the choice is discrete |
| Identity transformation | Merger, spinoff, conversion, share-class change | Create effective-dated successor inventory and conversion constraints |
| Voting/record-date risk | Shareholder meetings/proxy deadlines | Add beneficial-owner-specific recall buffer or hard recall requirement |
| Tradability interruption | Suspension, delisting, bankruptcy event | Disable new routes and stress return/recall costs |

Announcements may be amended or cancelled. Scenario hashes include the corporate-action event
version. Backtests use only the version known at the simulated decision time.

### 22.9 Legal-entity and concentration realism

Borrower limits should aggregate across branches and affiliates using an effective-dated hierarchy:

```text
sum(notional_j for routes mapped to ultimate_parent_b) <= parent_limit_b
sum(notional_j for routes mapped to legal_entity_b) <= entity_limit_b
```

Issuer relationships also support exposure limits across multiple securities, share classes, ADRs,
and subsidiaries. Bloomberg entity data can propose the hierarchy, but internal credit/legal owners
approve borrower netting sets and limits. Low-confidence or conflicting mappings fail closed for
hard aggregation and are visible in the data-quality report.

### 22.10 Multi-market fungibility and substitution

Reference data can identify related listings, ADRs, share classes, ETFs, or convertible instruments,
but economic substitutability is not the same as identifier relatedness. An approved
`InventoryTransformation` contract must state:

- source and destination securities/pools;
- conversion ratio and direction;
- fees, taxes, FX, settlement lag, and capacity;
- legal/operational eligibility;
- creation/redemption or conversion minimums; and
- effective interval and source approval.

Approved transformations create a network-flow extension:

```text
source balance - transformation outflow = retained/loaned/available source
destination balance + ratio * transformation inflow = retained/loaned/available destination
```

Continuous transformations stay LP. Fixed fees, minimum creation units, or mutually exclusive
routes require MIP. Basis/currency risk can add convex QP terms or explicit scenarios. Do not infer
fungibility from a common issuer alone.

### 22.11 Multi-period inventory and settlement model

A single effective date cannot fully represent a sale today, recall notice, borrower return, and
settlement several days later. The natural extension uses time buckets `t in T`:

```text
on_loan_i,t
  = on_loan_i,t-1 + new_loans_i,t - returns_i,t - recalls_i,t

available_i,t
  = lendable_i,t - on_loan_i,t - reserved_i,t - committed_i,t

lendable_i,t
  = lendable_i,t-1 + settled_buys_i,t - settled_sells_i,t
    + transfers_in_i,t - transfers_out_i,t + corporate_action_delta_i,t
```

The objective discounts daily expected revenue and applies time-specific transition, liquidity, and
fail costs. Calendar data determines valid business/settlement dates. Deterministic flows remain a
large sparse LP; lots/elections make it MIP. This should precede a fully stochastic formulation
because it captures most operational realism while remaining explainable.

### 22.12 Robust and stochastic optimization

Forecast means can over-allocate scarce names. Add named scenarios for demand, fee, return hazard,
inventory withdrawal, price/FX, liquidity cost, and corporate-action outcomes. Candidate approaches:

- conservative parameter quantiles in the existing LP;
- budgeted robust bounds for demand/supply uncertainty;
- two-stage stochastic LP with first-stage reserve/retention and second-stage allocation/recall;
- CVaR penalty on revenue shortfall, settlement failure cost, or forced recall cost; and
- chance constraints approximated by validated linear bounds.

Scenario probabilities must be calibrated and versioned. Report expected value, downside quantiles,
CVaR, worst named scenario, and the price of robustness versus the deterministic solution. Avoid
claiming robustness from a few arbitrary shocks.

### 22.13 Event and regime features

Create point-in-time features rather than direct undocumented overrides:

- days to ex/record/pay date and expected manufactured-payment impact;
- days to earnings, shareholder meeting, tender/election, index rebalance, or lockup expiry where
  licensed/available;
- trading status, spread/volume/volatility regime, and market stress percentile;
- free-float and ownership concentration percentile;
- ETF/index ownership and expected passive-flow pressure;
- security/sector/country peer utilization and fee regime; and
- issuer/parent event contagion indicators.

Use these in demand, take-up, return/recall hazard, liquidity, and reserve models. Each downstream
model publishes feature definitions, leakage controls, training window, performance by regime, and
fallback behavior. The optimizer receives only validated predictions and uncertainty, not an opaque
feature dataframe.

### 22.14 Shadow prices as internal inventory value

For a verified LP, the dual on an inventory balance estimates the local marginal objective value of
one additional lendable share. Use it to produce:

- an internal reservation value for a proposed buy/sell/transfer;
- a break-even lending fee for the next route;
- an opportunity-cost explanation for a reserve or restriction; and
- a ranked list of securities where sourcing inventory is most valuable.

This is local sensitivity, valid only while the active basis and linear assumptions remain stable.
For large changes, discrete models, or nonlinear models, re-solve explicit scenarios. Do not use a
dual as a transaction price or guaranteed profit.

### 22.15 Realism extension priority

| Priority | Extension | Why first | Formulation impact |
| --- | --- | --- | --- |
| P0 | Point-in-time security master and identifier mapping | Prevents invalid joins and false netting | Validation only |
| P0 | Settlement calendars, security status, and corporate-action lineage | Prevents impossible trade/recall scenarios | LP bounds/RHS |
| P0 | Vendor field mapping, lineage, freshness, and reconciliation | Makes enriched results auditable | Data architecture |
| P1 | Entity hierarchy aggregation | Captures connected counterparty/issuer exposure | LP constraints |
| P1 | Take-up, survival, repricing, and return/recall hazards | Converts quoted revenue into expected realized revenue | LP coefficients/scenarios |
| P1 | Dynamic reserve and liquidity-aware unwind cost | Makes sell/recall scenarios operationally credible | LP/PWL |
| P1 | Corporate-action costs and beneficial-owner recall policies | Captures common real-world revenue/risk discontinuities | LP/MIP scenarios |
| P2 | Censoring-aware hierarchical elasticity | Improves scarce-name allocation and cold starts | Upstream forecast; LP caps |
| P2 | Robust/CVaR scenarios | Controls downside from uncertain demand/supply and fails | Larger LP |
| P2 | Multi-period settlement/loan balances | Represents timing rather than coarse static deltas | Sparse LP/MIP |
| P3 | Cross-listing/ADR/ETF transformation graph | Unlocks alternative inventory paths | Network LP/MIP/QP |
| P3 | Continuous joint fee/quantity optimization | Optimizes pricing as well as allocation | PWL MIP or NLP |

P0 should be designed with the initial LP even if only synthetic adapters exist. P1 is the
recommended first realism release. P2/P3 require separate model-validation evidence and should not
delay a correct, explainable LP baseline.

### 22.16 Eligibility, collateral, and constraint catalog

Eligibility and collateral schedules are material risk controls, not merely data enrichment. Basel
Committee guidance for securities-financing transactions emphasizes explicit eligible-collateral
policies, risk-sensitive haircuts, margin sufficiency, possible margin-delivery delay, and collateral
substitution; applicability and parameter values still depend on the firm, agreement, transaction,
and jurisdiction ([BIS counterparty credit risk guidance](https://www.bis.org/committees/bcbs/basel-consolidated-guidelines/module/cri/40),
[BIS securities-lending market study](https://www.bis.org/publ/cpss32.pdf)). The project therefore
models these inputs as versioned schedules and never embeds a single regulatory or market-standard
percentage.

Candidate constraints are grouped below. “Pre-solve” means validation or bound compilation; it does
not mean the rule is less important.

| Domain | Constraint or schedule rule | Typical implementation |
| --- | --- | --- |
| Inventory | Exact lendable/on-loan/reserved/committed/available balance | Hard LP equality |
| Inventory | Pool/security maximum lend fraction | LP upper row/bound |
| Inventory | Absolute/fractional/dynamic availability reserve | LP lower bound on availability |
| Inventory | Exclusive inventory committed to a program/borrower | LP partition rows; MIP if exclusive choice is a decision |
| Inventory | Pending receipt/delivery and settlement eligibility | Pre-solve bounds; multi-period balance |
| Inventory | No cross-pool netting without legal authority | Index construction/hard separate balances |
| Agency | Beneficial-owner/pool/security conservation | Hard LP equality per owner inventory record |
| Agency | Owner mandate, borrower panel, fee split, and program limit | Pre-solve bounds, LP rows, objective coefficients |
| Agency | Contractual pro-rata/minimum participation or exclusive | LP row; MIP for discrete exclusive selection |
| Agency | Indemnification exposure, limit, capital, and cost | LP rows/objective; scenario/robust stress |
| Prime | Owned/client-reuse/affiliate/external source conservation | Network LP source rows |
| Prime | Hard client short/delivery coverage | LP equality; no unfilled slack |
| Prime | Locate/forecast service demand | LP equality with explicit unfilled quantity/penalty |
| Prime | Client reuse/rehypothecation and affiliate authority | Pre-solve source eligibility/default deny |
| Prime | External quote expiry, capacity, term, and all-in cost | Pre-solve bounds/objective; MIP if all-or-none |
| Prime | Funding, leverage, capital, liquidity, and encumbrance budget | LP group rows/PWL costs |
| Eligibility | Beneficial-owner allow/deny list | Pre-solve route bound |
| Eligibility | Borrower/legal-agreement approval and effective term | Pre-solve route bound |
| Eligibility | Security, issuer, asset class, country, market, or currency restriction | Pre-solve bound or group cap |
| Eligibility | `GRANDFATHER` existing loan with no increase | Route upper bound `q0_j` |
| Eligibility | `RECALL_ONLY` schedule action | Time-aware upper bound/required decrease |
| Eligibility | Voting, record-date, ESG, sanctions, tax, or client-policy restriction | Hard bound/reserve from approved policy |
| Eligibility | Minimum fee or maximum loan term | Pre-solve bound; MIP tier removal; multi-period limit |
| Demand | Elasticity-adjusted group maximum | LP upper row |
| Demand | Locate expiry/validity window | Pre-solve route bound |
| Demand | All-or-none, minimum fill, or minimum ticket | MIP activation/logical rows |
| Demand | Service-level floor by approved borrower tier | Hard LP row or explicit soft target |
| Pricing | Fee/rebate minimum, benchmark spread, or rate-card floor | Bound/tier removal; MIP pricing |
| Pricing | Tiered revenue share or fixed route fee | PWL/MIP or precomputed coefficient |
| Pricing | Break-even uplift after recall/setup cost | Objective economics; optional policy threshold |
| Collateral | Route-to-schedule compatibility | Pre-solve validation/bound |
| Collateral | Eligible collateral asset/type/currency/market | Pre-solve pair generation |
| Collateral | Haircut-adjusted coverage and margin factor | LP coverage row |
| Collateral | Available collateral capacity by borrower/type | LP capacity row |
| Collateral | Issuer/country/currency/asset concentration | LP group rows |
| Collateral | Wrong-way-risk and affiliate exclusions | Pair omission/hard zero bound |
| Collateral | FX mismatch haircut/add-on | Precomputed coefficient or scenario |
| Collateral | Stale/missing price or disputed valuation | Fail closed or approved conservative valuation |
| Collateral | Minimum transfer, denomination, or whole lot | MIP or external validation |
| Collateral | Substitution rights, cutoff, and settlement lag | Multi-period LP/MIP |
| Collateral | Segregation, reuse, or rehypothecation prohibition | Separate balances/eligibility bounds |
| Collateral | Cash reinvestment eligibility and duration/liquidity limit | External schedule coefficient or later joint cash model |
| Counterparty | Borrower/legal entity/ultimate-parent notional or quantity maximum | LP group rows |
| Counterparty | Exposure after collateral credit/haircuts | LP rows; scenario/robust add-on |
| Counterparty | Internal rating/watchlist/stress limit | Effective schedule bounds/scenarios |
| Concentration | Security, issuer, sector, country, pool, owner, or borrower maximum | LP group rows |
| Concentration | Diversification preference rather than hard maximum | PWL or convex QP penalty |
| Contract | Term maturity, recall notice, open/term behavior | Bounds; multi-period constraints |
| Contract | Maximum tenor or weighted-average tenor | LP row; multi-period state |
| Contract | Early termination, recall fee, or break cost | Linear/PWL objective term |
| Corporate action | Mandatory quantity/identity transformation | Pre-solve transform or multi-period equality |
| Corporate action | Voluntary election/tender/rights quantity | Reserve; MIP if optimizer selects election |
| Corporate action | Record-date/proxy recall requirement | Schedule reserve/required decrease |
| Corporate action | Manufactured payment and tax cost | Linear objective coefficient/scenario |
| Liquidity | ADV/depth/liquidation-horizon buffer | Precomputed LP reserve |
| Liquidity | Size-dependent unwind or recall cost | PWL LP/MIP or convex term |
| Liquidity | Halt/suspension/delisting treatment | Bounds and stress scenarios |
| Capital | Indemnification, RWA, leverage, balance-sheet, or liquidity budget | LP group rows/objective costs |
| Operations | Daily route/borrower/security capacity | LP rows |
| Operations | Maximum active routes/instructions | MIP cardinality |
| Operations | Settlement-location or custodian capacity | LP group rows/multi-period |
| Operations | Cutoff, holiday, or processing-window restriction | Pre-solve/multi-period calendar rule |
| Risk | Revenue, recall, or collateral covariance | Convex QP |
| Risk | Demand/supply/fee/collateral uncertainty budget | Robust LP |
| Risk | Tail revenue shortfall, fail, or forced-recall cost | Scenario CVaR LP |
| Relationship | Approved allocation floor/fairness target | Hard row only if contractual; otherwise explicit soft term |
| Governance | Manual override maximum and expiry | Pre-solve approval/metadata validation |
| Governance | Non-relaxable constraint class | Compiler/repair-policy enforcement |

Constraint inclusion rules:

1. A hard constraint requires an authoritative schedule/contract/policy source, owner, effective
   interval, unit, and test fixture.
2. A preference must not be disguised as a hard rule; model it as an explicit soft target or
   objective cost with documented USD interpretation.
3. Duplicate constraints from multiple schedules are intersected unless an approved authority rule
   permits replacement.
4. A rule that cannot be represented faithfully in the selected formulation fails capability
   validation; it is not approximated silently.
5. Each compiled row/bound retains schedule/rule IDs for audit, explanation, and infeasibility
   diagnosis.

### 22.17 Bloomberg-enriched acceptance criteria

- Vendor fields are mapped by versioned configuration, not hard-coded in the optimizer core.
- Each enriched value has source, observed, effective, quality, and mapping-version metadata.
- Internal positions, contract terms, eligibility, and limits remain authoritative.
- Security identity changes and corporate-action revisions do not rewrite history.
- Backtests cannot observe data or event revisions unavailable at the simulated as-of time.
- Stale, missing, conflicting, unentitled, halted, and future-effective data follow explicit policy.
- Proposed trades use market-specific settlement dates and recall timing.
- Entity limits aggregate through internally approved effective-dated hierarchies.
- Expected economics separate contractual rate, take-up, survival, repricing, and transition costs.
- Vendor liquidity estimates are calibrated/benchmarked against internal realized outcomes.
- Every extension declares whether it is preprocessing, LP, MIP, QP, PWL, stochastic, or nonlinear.
- All Bloomberg adapter tests use synthetic/licensing-safe fixtures.
- Eligibility and collateral schedule versions are bitemporal, approved, deterministically resolved,
  and attached to compiled bounds/rows.
- Collateral coverage, capacity, concentration, haircut convention, and valuation freshness verify
  independently when collateral is relevant.

---

## 23. Platform Integration and Desk Operating Models

The optimizer is one modular capability within the existing platform. Desk support is implemented
as registered problem families over a shared inventory kernel, not as branches scattered through
the service layer. Selecting a family changes its required records, objective components,
constraints, result attribution, and capability manifest; it never changes the canonical meaning of
shares, price, time, eligibility, or verified solver status.

| Problem family | Primary decision | Default scope |
| --- | --- | --- |
| `securities_lending_inventory` | Retain, recall, or allocate owned/controlled lendable inventory | Initial LP and what-if release |
| `agency_lending` | Allocate each beneficial owner's inventory across approved borrower routes | Opt-in agency desk profile |
| `prime_inventory_financing` | Source and allocate inventory to cover prime-client demand | Opt-in prime desk profile |

No problem-family name is a legal conclusion about the platform or firm. Deployment owners must map
actual booking entities, agency/principal capacity, agreements, client consents, and regulatory
obligations into approved inputs.

### 23.1 Problem-family registry and shared kernel

A problem-family registry declares request type, required components, default config profile,
solver capabilities, result schema additions, and verifier set:

```python
@problem_family(
    name="agency_lending",
    version="1.0",
    supported_formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
)
class AgencyLendingFamily(ProblemFamily):
    request_type = OptimizationRequest
    result_type = OptimizationResult
    default_components = AGENCY_DEFAULT_COMPONENTS
    verifier_types = AGENCY_VERIFIERS
```

The registry is frozen after application startup. Duplicate names/versions, missing verifiers, an
unknown family, or a family/request mismatch fail before normalization. Family components reuse:

- canonical inventory reconciliation and route quantities;
- bitemporal schedules and approved entity/agreement mappings;
- elasticity, scenarios, sparse builders, and solver adapters;
- normalized statuses, infeasibility policy, and independent verification; and
- result, explanation, audit, and platform invocation envelopes.

Desk-specific code may add typed records and rows but cannot weaken shared non-relaxable constraints.
The baseline family remains behaviorally unchanged when agency and prime profiles are disabled.

### 23.2 Shared desk contracts

| Contract | Required semantics |
| --- | --- |
| `DeskContext` | Problem family, platform tenant, booking/legal entity, desk, region, base currency, attribution scope, effective time |
| `BeneficialOwnerMandate` | Owner/pool scope, allowed borrowers/assets/markets, utilization/reserves, fee split, collateral rules, recall/voting/tax policy, exclusives, fairness and reporting policy |
| `InventorySource` | Source ID/type linked to `inventory_id`, owner, security/location, current/available quantity, settlement timing, reuse authority, agreement, priority, variable/fixed costs, source version |
| `ClientShortDemand` | Client/account linked to `demand_group_id`, security/location, requested or required quantity, locate/pre-borrow/settled status, due time, fee, service class, take-up uncertainty |
| `ExternalBorrowQuote` | Lender/agreement linked to external `source_id`, security, available quantity, fee/rebate, term, collateral, expiry, settlement, recall stability, all-in costs, observed/effective time |
| `IndemnificationPolicy` | Covered risk, beneficiary, exposure measure, limit, exclusions, capital/cost coefficient, stress method, owner, approval and version |
| `AgreementNettingSet` | Approved counterparties/accounts/agreement, products, collateral set, close-out/netting scope, effective interval and authority |
| `BalanceSheetBudget` | Legal entity/desk scope, exposure measure, hard limit or soft cost curve, currency, horizon, owner and approval |

Source types include `BENEFICIAL_OWNER`, `FIRM_OWNED`, `CLIENT_REUSE`, `AFFILIATE`, and
`EXTERNAL_BORROW`. `CLIENT_REUSE` and `AFFILIATE` default to unavailable unless affirmative legal,
client-consent, entity, agreement, settlement, and operational permissions all resolve. Source
priority is explanatory policy, not an economic shortcut: a hard priority requires an approved
rule; otherwise the objective compares full marginal cost.

### 23.3 Agency lending family

Agency mode preserves inventory and attribution by beneficial owner. Let `o in O` denote owners and
`J(o,i)` the eligible routes drawing from owner `o` and inventory record `i`. Every owner/pool/
security balance remains separate:

```text
sum(q_j for j in J(o,i)) + a_oi = L_oi - R_oi - C_oi
```

Cross-owner pooling or substitution is forbidden unless an approved mandate and legal/operational
mapping creates an explicit transformation arc. The agency objective extends the baseline with
owner-specific economics:

```text
maximize
    owner-attributed fee and reinvestment revenue
  - recall, settlement, event, and servicing costs
  - indemnification and balance-sheet charges
  - approved soft fairness deviations
```

Required agency components support:

- owner-specific borrower, asset, market, country, term, collateral, ESG, tax, voting, record-date,
  and utilization schedules;
- contractual revenue shares, minimum fees, benchmark spreads, exclusives, and minimum owner
  participation;
- borrower and ultimate-parent limits both within an owner program and across the agent's approved
  aggregate exposure;
- cash-versus-noncash collateral rules, reinvestment eligibility, liquidity/duration constraints,
  and owner-specific income attribution;
- indemnification coverage, exclusions, stress exposure, capital consumption, and pricing;
- recalls and reserves needed for sales, redemptions, voting, corporate actions, mandate changes,
  or owner withdrawals; and
- owner-level revenue, utilization, opportunity cost, exceptions, and policy-compliance reporting.

Fairness is never implied. A contractual pro-rata or minimum-allocation rule is a hard row. A
business preference uses named deviation variables with a documented USD penalty or an optional
convex QP dispersion term. It cannot force an otherwise ineligible or negative-value allocation.
Exclusive selection, discrete borrower panels, or whole-program choices require MIP.

The independent verifier reconciles quantities and economics at owner, pool, security, borrower,
agreement, and collateral-schedule levels. Indemnification exposure and cost are reported separately
from owner lending revenue rather than buried in a generic variable-cost coefficient.

### 23.4 Prime inventory financing family

Prime mode treats inventory coverage as a sourcing network. Let `s in S` be permitted inventory
sources, `d in D` prime-client demands, and `x_sd >= 0` the post-state quantity sourced from `s` to
cover `d`. Pairs exist only for the same deliverable security/location or through an approved
transformation arc.

```text
sum_d x_sd <= source_capacity_s                        for every source s

sum_s x_sd + unfilled_d = demand_quantity_d            for every demand d
```

For a settled short, delivery obligation, or approved pre-borrow commitment, `unfilled_d = 0` is
hard unless the source system explicitly identifies an allowed exception workflow. For an
indicative locate or forecast opportunity, `unfilled_d >= 0` measures unserved demand and may carry
an approved service penalty. Existing source allocations have increase/decrease variables and
term/recall/settlement bounds just like baseline loan routes.

The prime objective is:

```text
maximize
    client borrow revenue
  - external borrow and internal transfer cost
  - funding, collateral, capital, liquidity, and encumbrance cost
  - source-switch, recall, fail, buy-in, and operational cost
  - approved client-service penalties
```

Required prime components support:

- internalization across firm-owned and affirmatively reusable client inventory;
- external borrow quote selection with expiry, term, collateral, lender limits, settlement
  probability, recall stability, and replacement cost;
- locate, pre-borrow, booking, allocation, settlement, return, recall, repricing, fail, buy-in, and
  cancellation lifecycle states;
- client/account service tiers, hard delivery obligations, concentration, and relationship targets;
- legal-entity, agreement/netting-set, collateral, wrong-way-risk, and counterparty stress limits;
- rehypothecation/client-consent restrictions and no reuse beyond contractual or regulatory scope;
- funding, leverage, economic-capital, liquidity, encumbrance, and intraday settlement budgets;
- approved affiliate transfers and physical/synthetic transformation routes with explicit cost,
  basis risk, capacity, and timing; and
- client, source, legal-entity, and matched-book profitability attribution.

Internal inventory is not automatically free: it carries its configured scarcity opportunity value,
funding/capital cost, and alternative-use value. External quotes are not guaranteed executable
capacity and therefore require expiry/freshness validation plus take-up/settlement scenarios. The
model exposes marginal source and demand values; any internal transfer price applied downstream is
an approved reporting policy, not a replacement for solver attribution.

Minimum source tickets, all-or-none quotes, source activation fees, cardinality, exclusivity, and
discrete price ladders require MIP. Concentration or source-stability preferences may use convex QP.
Recall cascades, rolling locates, settlement queues, and collateral calls belong in the multi-period
LP/MIP. Joint continuous client pricing and quantity remains an optional PWL/NLP extension.

### 23.5 Platform responsibilities and integration modes

| Existing platform owns | Inventory optimizer owns |
| --- | --- |
| Authentication, authorization, tenant/user context | Canonical request validation |
| Books/records and upstream data connectivity | Inventory and source reconciliation |
| Entitlements and licensed-data handling | Bitemporal schedule resolution |
| Scheduling, queues, retries, persistence | Problem-family/component selection |
| UI, workflow, approvals, notification | Sparse formulation and solver execution |
| Deployment, secrets, encryption, recovery | Independent solution verification |
| Regulatory/booking adapters | Attribution, reason codes, canonical result/audit envelope |

The preferred first integration is an in-process or worker invocation through the platform-owned
adapter because it minimizes distributed-system surface area. A service boundary is justified only
by independent scaling, language/runtime isolation, or release needs. All modes use canonical JSON-
serializable contracts and contract tests. Platform dataframes, ORM objects, user-session objects,
and vendor SDK records do not cross into the optimizer core.

### 23.6 Desk scenarios and comparison output

Agency scenarios add owner contribution/withdrawal, mandate or borrower-panel change, exclusive
award/loss, fee-split change, indemnification stress, proxy/record-date recall, collateral-policy
change, and cash-reinvestment liquidity shock.

Prime scenarios add client short/cover, locate conversion/cancellation, external quote expiry or
repricing, source recall, client-reuse loss, affiliate capacity change, funding/capital shock,
counterparty downgrade, margin/haircut shock, fail/buy-in, and crowded-cover demand.

Comparison output adds:

- owner/client/source/legal-entity allocation and economic deltas;
- internalized versus external-sourced quantities and replacement cost;
- owner fairness or client-service deviations with hard/soft classification;
- indemnification, funding, capital, collateral, and liquidity consumption;
- source concentration, stability, expiries, recalls, fails, and uncovered hard obligations; and
- binding mandate/agreement/balance-sheet rules with full lineage.

### 23.7 Desk-family acceptance criteria

- The core family produces identical compiled models/results whether desk extensions are installed
  but disabled or absent.
- Agency quantities and economics reconcile by beneficial owner with no unauthorized commingling.
- Prime demand coverage and every inventory source reconcile without creating shares or reuse
  capacity.
- A hard settled short cannot be returned as silently unfilled; infeasibility or an explicit
  exception workflow is required.
- Client inventory and affiliate sources remain unavailable without affirmative effective authority.
- Agency fairness and prime service preferences are labeled hard or soft and cannot weaken legal,
  inventory, collateral, or settlement constraints.
- Indemnification, external-borrow, funding, capital, and transfer-price economics are separately
  attributable and reconstruct the objective.
- Every source, mandate, agreement, quote, limit, and platform invocation reference retains
  bitemporal lineage and approval metadata.
- In-process, worker, and service contract fixtures produce equivalent canonical results.
- The platform adapter cannot return an allocation recommendation that failed optimizer
  verification.

---

## 24. Testing Strategy

`EXAMPLES.md` cases E1-E9 are mandatory golden-fixture seeds. Every normative test must reference at
least one stable requirement ID from `TRACEABILITY.md`; every implemented traceability row must link
the exact test path and CI evidence that satisfies it.

### 24.1 Unit tests

- Unit/rate conversion and day-count behavior.
- Config merge precedence, unknown-key rejection, and stable hashing.
- Inventory arithmetic and current-route reconciliation.
- Constant and semi-log elasticity, floors, caps, and uncertainty haircuts.
- Every objective and constraint component in isolation.
- Variable/row index reversibility.
- Decorator duplicate rejection and capability manifests.
- Scenario overlay ordering and baseline immutability.
- Native-to-normalized solver status mapping.
- Objective reconstruction and solution verification.

### 24.2 Property tests

- Conservation: all feasible outputs satisfy inventory equality.
- Supply monotonicity under simple positive-economics cases.
- Higher route fee never lowers that route's allocation when no other coefficient/constraint changes
  and the optimum is unique.
- Positive elasticity never increases demand when fee increases.
- Permuting input record order does not change ID-keyed results.
- Applying an empty scenario equals baseline.
- Repeating a scenario produces the same hashes and results within tolerance.
- No reported available, on-loan, or allocation quantity is negative beyond tolerance.

### 24.3 Golden LP case

Inputs:

- One inventory pool/security with 100 lendable shares, no reserve, no current loans, price USD 10.
- Route A: maximum 80 shares, annual fee 2.00%, no costs.
- Route B: maximum 80 shares, annual fee 1.00%, no costs.
- Both demand caps are 80 shares and utilization cap is 90%.

Expected result:

```text
Route A post quantity = 80
Route B post quantity = 10
Post on-loan          = 90
Post available        = 10
Post utilization      = 90%
Inventory balance residual = 0
```

Removing the utilization cap yields A = 80 and B = 20. A 30-share settled sale from the uncapped
baseline yields 70 total lendable and A = 70, B = 0. These are mandatory exact-allocation golden
tests within quantity tolerance.

### 24.4 Golden elasticity case

With reference demand 80 shares at a 2.00% fee and elasticity `0.5`, a fee shock to 3.00% produces:

```text
80 * (0.03 / 0.02) ** (-0.5) = 65.319726...
```

Before other caps/haircuts, the effective demand cap must equal that value within tolerance, and the
scenario explanation contains `ELASTICITY_REDUCED_DEMAND`.

### 24.5 Existing-loan churn case

Supply is fully allocated to a 1.00% current route. A 1.10% candidate route appears. With transition
costs greater than the horizon fee uplift, the current route remains. With zero transition costs,
inventory moves to the higher-rate route, subject to its demand maximum. The objective attribution
must explain both outcomes.

### 24.6 Infeasibility cases

- Reserved plus committed inventory exceeds post-trade lendable.
- A settled sell leaves term loans above post-trade lendable.
- Current route totals do not reconcile with on-loan input.
- Hard utilization floor exceeds cap.
- Counterparty minima conflict with hard counterparty maxima.
- MIP time limit returns no incumbent versus a verified incumbent.

### 24.7 Integration tests

- JSON/YAML request -> config -> HiGHS solve -> verified JSON result.
- LP and MIP capability checks against the pinned backend.
- Batch scenarios match isolated scenario solves.
- QR Haven adapter mapping and authorization/idempotency context, in a QR Haven-owned test, without
  reversing the dependency.
- In-process and serialized worker/service invocations produce equivalent canonical results.
- Portability copy/install/import test.

### 24.8 Performance tests

- Compile and solve benchmark profiles from Section 20.
- Sparse memory/nonzero growth.
- Batch model-reuse correctness and benefit.
- Degenerate fee ties and numerically small/large coefficients.
- MIP limit behavior with realistic discrete rules.

### 24.9 Bloomberg-enrichment tests

- Bitemporal joins exclude observations/revisions received after the simulated as-of time.
- Identifier changes preserve historical security identity and effective-dated successors.
- Corporate-action amendments and cancellations invalidate the appropriate cached scenarios.
- Split/conversion events reconcile pre/post quantities and route lineage exactly.
- Market calendars apply settlement dates and cutoffs without weekend/holiday shortcuts.
- Halted, suspended, delisted, stale, conflicting, and unentitled concepts follow configured policy.
- Entity exposure aggregates across approved legal entity and ultimate-parent mappings.
- Dynamic liquidity buffers and PWL costs are monotone and match configured knots.
- Expected revenue reconstructs take-up, active-horizon, rate, and cost components.
- Bloomberg adapters pass contract tests using synthetic responses and contain no licensed fixtures.
- Missing or renamed vendor mappings fail in the adapter health check before optimization.

### 24.10 Eligibility, collateral, and schedule tests

- Schedule versions resolve on both observation and effective time without using future revisions.
- `DENY`, `GRANDFATHER`, `RECALL_ONLY`, and `REVIEW` actions produce their specified route bounds.
- Safety authority, specificity, explicit priority, intersection, and contradiction behavior are
  deterministic under permuted rule input.
- Expired, unapproved, missing, and conflicting required schedules fail closed.
- A newly ineligible term loan is not assumed immediately recallable.
- Minimum fee, maximum term, lend-fraction, exclusive, voting, and locate-expiry rules compile into
  named, traceable bounds/rows.
- Validate-only collateral rejects incompatible type, stale valuation, insufficient coverage, and
  wrong-way-risk pairs.
- Capacity mode limits total loan exposure to haircut-adjusted collateral credit.
- Joint mode conserves collateral capacity and satisfies route coverage/concentration rows.
- Haircut conversion tests distinguish market-value deduction from required-margin conventions.
- Cash reinvestment income is not counted from both route notional and assigned collateral.
- MIP collateral lots/minimum transfers and multi-period substitutions verify when enabled.
- Every schedule-derived row/bound maps back to rule ID, version, owner, and approval metadata.

### 24.11 Agency, prime, and platform tests

- Mandatory agency golden case: owner A has 60 eligible shares, owner B has 40, common demand is
  100, and B's approved mandate caps lending at 20. With equal positive economics and no other
  limits, post allocation is A = 60 and B = 20 with B availability = 20; the model may not use B's
  residual to manufacture A inventory.
- Mandatory prime golden case: hard client coverage is 100 shares, an eligible internal source has
  capacity 60 at 0.20% fully adjusted cost, and an eligible external source has capacity 50 at
  0.80%, with identical timing and no other limits. At a 1.00% client fee, source allocation is 60
  internal and 40 external, `unfilled = 0`, and both source and client balances reconcile.
- Agency fixtures reconcile independently by owner/pool/security and reject unauthorized pooling.
- Owner-specific mandates, fee splits, exclusives, voting recalls, collateral rules, and
  indemnification charges compile with complete attribution.
- Hard agency pro-rata/minimum rules and soft fairness objectives are distinguished and verified.
- Prime fixtures conserve every owned, client-reuse, affiliate, and external source.
- Client reuse and affiliate capacity fail closed without affirmative permission and agreement
  lineage.
- Required settled shorts are fully covered or produce strict infeasibility; locates may be
  explicitly unfilled according to their status.
- External quote expiry, recall, fee, settlement, all-in cost, and source-switch behavior pass
  golden cases.
- Balance-sheet, funding, collateral, legal-entity, and client-service rows verify independently.
- Disabling desk extensions reproduces the baseline core family byte-for-byte at compiled metadata
  level and within tolerance at result level.
- Duplicate idempotent platform invocations return/refer to the same canonical result; conflicting
  payload reuse is rejected.
- A platform timeout or cancellation cannot be mislabeled optimal and cannot bypass verification.

Tests run without network access and use deterministic fixtures.

---

## 25. Delivery Phases and Definition of Done

### Phase 0 — Package foundation

Deliver project scaffold, config loader, contracts, exceptions, registries, validation framework,
platform invocation contract, problem-family registry, and portability test.

Done when:

- package and CLI import successfully;
- strict typing/lint/tests pass;
- config is frozen, validated, and hashed;
- invalid balance fixtures produce aggregated structured errors;
- no core file imports `qr_haven`.
- platform context serializes without importing platform identity/session objects.

### Phase 1 — Production-quality LP slice

Deliver normalization, elasticity caps, core objective/constraints, sparse compiler, HiGHS LP,
verifier, attribution, result serialization, and QR Haven platform-adapter invocation.

Done when:

- all LP golden/property tests pass;
- solver objective equals attributed unscaled objective;
- every inventory balance reconciles;
- normalized statuses and diagnostic output are complete;
- benchmark data compiles without dense matrix growth.
- direct and platform-adapter invocations return equivalent canonical results.

### Phase 2 — Scenario analysis

Deliver typed trade/rate/demand/policy overlays, batch runner, comparison, and explanations.

Done when:

- baseline remains immutable;
- batch and isolated results match;
- proposed sells expose recalls or infeasibility correctly;
- elasticity shock attribution is visible;
- comparison tables reconcile to underlying results.

### Phase 3 — MIP rules

Deliver activation/lot/minimum/all-or-none/cardinality/discrete-rate components and HiGHS MIP
settings/status handling.

Done when:

- integer and logical rules verify independently;
- time-limit outcomes distinguish incumbent quality;
- big-M coefficients are tight and diagnosed;
- LP behavior is unchanged when discrete components are disabled.

### Phase 4 — QP

Deliver one justified convex quadratic term, PSD checks, backend capability tests, and attribution.

Done when:

- QP mode is optional and config-gated;
- convexity/scaling failures are actionable;
- returned solution verifies and objective attribution includes the quadratic term;
- fallback behavior is explicit.

### Phase 5 — Nonlinear research extension

Deliver only after an approved model note defines the nonlinear business need, formulation,
backend, convergence, and benchmarks.

Done when local/global status, fallback, sensitivity to initialization, and approximation error are
all reportable.

### Realism releases R0-R3

These releases can proceed alongside the formulation phases but cannot bypass their exit gates:

- **R0 — Data correctness:** point-in-time security master, lineage, field mapping, freshness,
  calendars, status, and corporate-action versioning.
- **R1 — Expected economics:** legal-entity aggregation, take-up/survival/repricing hazards,
  dynamic reserves, liquidity-aware costs, and event economics.
- **R2 — Uncertainty and timing:** censoring-aware elasticity, robust/CVaR scenarios, and
  deterministic multi-period settlement balances.
- **R3 — Structural alternatives:** approved fungibility/transformation graph and continuous joint
  pricing research.

R0 is required before production use. R1 is required before presenting model economics as expected
realized revenue rather than contractual run-rate revenue. R2 and R3 require separate model-risk
approval.

### Desk and platform releases D0-D2

- **D0 — Platform module integration:** platform-owned adapter, invocation context, canonical
  request/result schema, idempotency contract, authorization reference, equivalence tests, and
  portability boundary.
- **D1 — Agency lending:** owner mandates and partitioned balances, agency economics,
  indemnification, fairness/exclusives, owner scenarios, and owner-level verification/reporting.
- **D2 — Prime inventory financing:** inventory-source network, client demand lifecycle, external
  quotes, internalization, balance-sheet constraints, prime scenarios, and source/client
  verification/reporting.

D0 proceeds with the initial LP vertical slice. D1 and D2 are separately enabled business
capabilities; neither is required for the core family. Each requires business, legal, operations,
risk/control, data, and engineering approval for the actual desk and booking entities.

---

## 26. Implementation Task Matrix

| ID | Task | Depends on | Primary acceptance evidence |
| --- | --- | --- | --- |
| T01 | Scaffold standalone project/package | none | portability import test |
| T02 | Implement frozen config and loader | T01 | precedence/hash tests |
| T03 | Implement domain contracts and units | T01 | schema/unit tests |
| T04 | Implement reconciliation/validation | T03 | aggregated invalid fixtures |
| T05 | Implement component registries/decorators | T01, T02 | registry/manifest tests |
| T06 | Implement elasticity service | T02, T03 | golden/property tests |
| T07 | Implement sparse indexes/builders | T03, T05 | matrix/index tests |
| T08 | Implement LP components/compiler | T04, T06, T07 | compiled golden model |
| T09 | Implement HiGHS LP adapter | T08 | solver integration tests |
| T10 | Implement independent verifier | T03, T08 | corrupted-solution tests |
| T11 | Implement result/attribution/explanation | T09, T10 | objective reconciliation |
| T12 | Implement public API and CLI | T02, T11 | end-to-end JSON test |
| T13 | Implement scenario overlays | T04, T06 | immutability/timing tests |
| T14 | Implement scenario batch/comparison | T11, T13 | batch equivalence tests |
| T15 | Implement MIP components/backend path | T08, T09 | integrality/limit tests |
| T16 | Implement benchmarks/observability | T11, T14 | benchmark/audit output |
| T17 | Implement QR Haven platform adapter | T12, T34 | one-way dependency and invocation-equivalence tests |
| T18 | Implement QP extension | Phase 1 stable | PSD/capability tests |
| T19 | Implement point-in-time lineage/reference contracts | T03, T04 | bitemporal/no-look-ahead tests |
| T20 | Implement Bloomberg ports, mappings, and adapter health check | T02, T19 | synthetic contract tests |
| T21 | Add calendars, security status, and corporate-action scenarios | T13, T19, T20 | event/settlement golden tests |
| T22 | Add approved entity-hierarchy aggregation | T08, T19, T20 | parent/entity limit tests |
| T23 | Add take-up/survival/repricing expected economics | T06, T11, T19 | realized-revenue attribution tests |
| T24 | Add dynamic buffers and liquidity PWL terms | T08, T19, T20 | monotonicity/knot tests |
| T25 | Add censoring-aware hierarchical elasticity upstream adapter | T06, T19 | walk-forward forecast tests |
| T26 | Add robust/CVaR scenarios | T14, T23, T24 | downside/price-of-robustness tests |
| T27 | Add deterministic multi-period balances | T21, T23 | daily conservation tests |
| T28 | Add approved inventory-transformation graph | T15, T19, T21 | conversion/fungibility tests |
| T29 | Implement effective-dated eligibility schedule resolver | T02-T05, T19 | precedence/action/bitemporal tests |
| T30 | Implement collateral schedule contracts and validate-only mode | T03, T04, T29 | compatibility/coverage tests |
| T31 | Implement collateral capacity constraints | T08, T22, T30 | haircut-credit/capacity tests |
| T32 | Implement joint collateral allocation mode | T15, T24, T30-T31 | collateral conservation/concentration tests |
| T33 | Implement fee, term, event, and operating constraint schedules | T08, T21, T29 | compiled rule-lineage tests |
| T34 | Implement platform invocation context and adapter contract | T02-T05, T19 | schema/idempotency contract tests; transport equivalence completes with T17 |
| T35 | Implement problem-family and desk-profile registry | T02, T03, T05 | family isolation/capability tests |
| T36 | Implement agency mandates, owner balances, and attribution | T08, T29-T30, T35 | no-commingling and owner-reconciliation tests |
| T37 | Implement agency indemnification, fairness, and exclusive components | T23, T31, T36; T15/T18 when enabled | objective attribution and LP/QP/MIP policy tests |
| T38 | Implement prime inventory-source and client-demand network | T08, T21-T22, T29-T31, T35 | source/demand conservation tests |
| T39 | Implement external-quote, reuse, funding, and balance-sheet components | T23-T24, T38; T15/T27 when enabled | authority, cost, capacity, and expiry tests |
| T40 | Implement desk scenarios and platform-facing desk reports | T14, T34, T36-T39 | agency/prime scenario and reporting golden tests |

T01-T12 plus T17, T34, and the baseline portion of T35 define the minimum useful platform-integrated
LP release. T13-T14 define the what-if release. T15 and T18 are
separate opt-in increments. T19-T21 form required realism release R0; T22-T24 form R1; and T25-T28
are independently approved R2/R3 extensions. T29-T30 and applicable T33 schedule controls are part
of production R3; T31-T32 are enabled only when collateral capacity/allocation is in model scope.
T34 is part of initial platform integration. T35 is the desk-extension foundation; T36-T37 deliver
agency mode and T38-T39 prime mode. T40 completes their scenario/reporting surface.

---

## 27. Risks and Mitigations

| Risk | Consequence | Mitigation |
| --- | --- | --- |
| Upstream ambiguity about lendable supply | Double-counted or missing shares | Required convention mapping and reconciliation failure |
| Fee units mixed between bps and decimals | Materially wrong revenue | Canonical unit types/helpers and golden conversion tests |
| Demand is approved quantity, not unconstrained demand | Biased low demand caps | Source semantics field and adapter validation |
| Utilization penalty overwhelms economics | Uneconomic loans | Default zero target penalty; all penalties in USD |
| Large transition costs freeze the book | No useful reallocations | Attribute costs and scenario-sweep parameters |
| Loose big-M bounds | Slow/unstable MIP | Derive bounds from demand and supply; warn/reject extreme values |
| Scenario mutates baseline | Corrupted comparisons | Frozen contracts, copy-on-overlay, immutability tests |
| Solver status misinterpreted | Unsafe recommendation | Normalized status mapping and independent verification |
| QP matrix is not PSD | Nonconvex model sent as convex | PSD validation and explicit regularization metadata |
| Nonlinear local optimum presented as global | Misleading economics | Separate statuses and backend-specific convergence report |
| Monorepo coupling blocks extraction | Rewrite required later | Standalone project root, one-way adapter, portability CI |
| Float share outputs violate operating lots | Booking mismatch | MIP lots or explicit rounding/repair with re-verification |
| Term/settlement rules omitted in sell scenario | Unfulfillable recall recommendation | Effective-date and recall-bound compiler plus infeasibility tests |
| Vendor identifiers or fields change | Broken joins or silent nulls | Versioned mapping, adapter health check, and effective-dated IDs |
| Revised vendor data leaks into history | Inflated backtest results | Observed/effective timestamps and vintage-aware fixtures |
| Corporate action is amended/cancelled | Stale route bounds or quantities | Event version lineage, cache invalidation, and re-solve |
| Vendor data conflicts with internal books | Unsafe override of authoritative state | Reconciliation issue and explicit approved override only |
| Liquidity estimate is treated as executable | Understated unwind/fail risk | Internal calibration, stress percentiles, and caveated output |
| Entity hierarchy differs from legal netting | Incorrect counterparty aggregation | Internal credit/legal approval over vendor-proposed relationships |
| Licensed data appears in tests/logs | Contractual or confidentiality breach | Synthetic fixtures, redaction, entitlement-aware adapters |
| Eligibility schedules overlap or conflict | Incorrectly permitted/prohibited route | Authority/specificity precedence, hard-limit intersection, conflict rejection |
| New schedule strands an existing term loan | Impossible immediate recall | Grandfather/recall-only bounds with effective notice and settlement timing |
| Collateral haircut convention is inverted | Material overstatement of coverage | Canonical credit convention and source-conversion golden tests |
| Collateral value is stale or disputed | Under-collateralized recommendation | Freshness/dispute policy and conservative fail-closed treatment |
| Wrong-way or concentrated collateral is accepted | Credit loss amplification | Pair exclusions, concentration rows, approved risk add-ons |
| Collateral/reinvestment is counted twice | Inflated expected economics | Mode-exclusive attribution and independent objective reconstruction |
| Too many scheduled constraints make model infeasible | No recommendation | Schedule lineage on rows, IIS/diagnostic groups, explicit non-permissive repair policy |
| Platform integration leaks into core | Extraction and testing become costly | One-way platform adapter, canonical contracts, portability and import-boundary tests |
| Platform retries create duplicate runs | Conflicting results or wasted capacity | Idempotency key plus canonical request/config hash and persisted result reference |
| Desk profile silently changes economics | Incomparable or unauthorized recommendation | Registered family manifest, required approvals, and family-specific attribution |
| Agency inventory is commingled across owners | Legal/mandate breach | Owner-level balance rows and no transformation without explicit authority |
| Fairness rule forces uneconomic lending | Owner harm masked as service policy | Hard only when contractual; otherwise explicit bounded soft term with attribution |
| Indemnification is underpriced | Agency revenue overstated | Separate approved exposure, stress, capital, and cost components |
| Client inventory is reused without authority | Prime legal/client-consent breach | Default-deny source contract and bitemporal consent/agreement validation |
| External borrow quote is treated as firm capacity | Prime coverage/fail risk understated | Quote expiry, settlement/take-up scenario, replacement-cost and source-stability fields |
| Prime source flow double counts inventory | False short coverage | Per-source conservation, location/settlement identity, and independent network verifier |
| Balance-sheet costs use inconsistent exposure units | Wrong source/client economics | Typed exposure measures, approved aggregation sets, and unit-level golden tests |

---

## 28. Open Decisions with V0 Defaults

These questions do not block Phase 0/1 because a default is specified. A later decision record may
override them.

| Decision | V0 default |
| --- | --- |
| Optimization horizon | One effective date; one-day economics on ACT/360 |
| Fee perspective | Gross lender-side annual decimal times route revenue share |
| Utilization target | Informational; cap is hard, target penalty is zero |
| Missing elasticity | Conservative configured default with warning |
| Forecast uncertainty | One-standard-deviation demand haircut when std is present |
| Existing loan treatment | Optimizable within term/recall bounds with change costs |
| Partial shares | Continuous in LP; MIP/repair required for exact lots |
| FX | Inputs normalized to USD outside core V0 |
| Cash collateral reinvestment | Optional linear route economics, not a decision |
| Repair | Disabled unless explicitly requested |
| Scenario parallelism | One process/thread by default for determinism |
| Persisted data | None in core; audit sink is an injected adapter |
| API compatibility | Semantic versioning after first released package |
| Bloomberg access method | Injected adapter selected by deployment; no access SDK in core |
| Vendor field identifiers | Versioned deployment mapping; no hard-coded mnemonic in domain/formulation |
| Vendor/internal conflict | Internal record wins only through an explicit reconciled override record |
| Corporate-action treatment | Scenario/bounds first; automatic elective decisions disabled |
| Legal-entity aggregation | Vendor hierarchy proposed, internal credit/legal hierarchy authoritative |
| Liquidity estimate use | Conservative buffer/scenario input, calibrated to internal outcomes |
| Eligibility schedule precedence | Safety authority, then specificity, then explicit priority; unresolved conflict rejects |
| Existing loan newly denied | No increase; grandfather or recall-only according to approved effective rule |
| Collateral scope | Validate-only by default; capacity/joint modes require explicit business ownership |
| Haircut convention | Collateral market value reduced to recognized credit; adapters convert alternatives |
| Missing required collateral schedule | Reject affected new route; existing state enters exception workflow |
| Initial deployment boundary | Modular subsystem in QR Haven through a platform-owned adapter; not a separate platform replacement |
| Initial invocation shape | In-process or platform worker using the canonical facade; service transport only when justified |
| Problem family | `securities_lending_inventory`; agency and prime families are opt-in |
| Agency owner pooling | Forbidden unless an approved transformation explicitly authorizes it |
| Agency fairness | Disabled; contractual rules are hard and approved preferences are explicit soft terms |
| Agency indemnification | Separately attributed when applicable; no implicit generic spread deduction |
| Prime client-inventory reuse | Unavailable without affirmative effective consent/legal/agreement authority |
| Prime settled short coverage | Hard equality; no silent unfilled quantity |
| Prime internal inventory cost | Explicit opportunity/funding/capital inputs; zero requires documented approval |
| External borrow quotes | Expiring, non-guaranteed source candidates unless contractually committed |

Before production use, business owners must approve fee perspective, utilization policy, reserve
hierarchy, transition-cost assumptions, legal eligibility mapping, and acceptable MIP incumbent
policy.

---

## 29. Final Acceptance Checklist

### Product behavior

- [ ] Balances lendable, reserved, committed, on-loan, and available shares exactly within tolerance.
- [ ] Maximizes attributable net lending economics under configured policy.
- [ ] Uses fee rates, utilization limits/targets, and elasticity-adjusted demand.
- [ ] Preserves or recalls existing loans according to economics and operational constraints.
- [ ] Handles proposed buys, sells, transfers, new loans, returns, recalls, rate shocks, and demand
      shocks.
- [ ] Compares every scenario against one immutable baseline.
- [ ] Selects only an approved problem family and rejects family/request/component mismatches.
- [ ] Agency mode reconciles by owner and prime mode reconciles by inventory source and client demand.

### Architecture

- [ ] Core package is independent of QR Haven and extractable.
- [ ] QR Haven invokes the optimizer through a one-way platform-owned adapter using canonical
      request/result contracts.
- [ ] In-process, worker, and service transports have equivalent model semantics when enabled.
- [ ] Configuration layers are deterministic, validated, frozen, and hashed.
- [ ] Domain, formulation, solver, scenario, service, reporting, and adapter boundaries are enforced.
- [ ] Objective/constraint/backend decorators publish a validated component manifest.
- [ ] Sparse construction avoids dense route-scale matrices.

### Data realism

- [ ] Vendor adapters preserve observed time, effective time, source/version, mapping version, and
      quality for every enriched value.
- [ ] Point-in-time tests prevent future observations and revisions from entering historical runs.
- [ ] Security IDs, corporate actions, market calendars/status, and entity hierarchies are
      effective-dated.
- [ ] Bloomberg fields are mapped in adapter configuration and no proprietary fixture is committed.
- [ ] Internal inventory, contracts, eligibility, and limits remain authoritative.
- [ ] Expected revenue distinguishes contractual rate from take-up, survival, repricing, event, and
      transition effects.
- [ ] Vendor liquidity inputs are benchmarked to internal realized costs and labeled as estimates.
- [ ] Eligibility and collateral schedules are approved, bitemporal, deterministically resolved, and
      traceable from source rule to model bound/row.
- [ ] Existing loans made newly ineligible retain operationally possible grandfather/recall timing.
- [ ] Collateral coverage, capacity, concentration, valuation freshness, wrong-way risk, and haircut
      convention pass independent verification when applicable.
- [ ] Agency mandates/indemnification and prime source/reuse/agreement/balance-sheet inputs retain
      observed/effective time, authority, approval, and source lineage.

### Solver and correctness

- [ ] HiGHS LP path passes capability and golden tests.
- [ ] MIP is opt-in and only used for discrete requirements.
- [ ] QP/NLP behavior is capability-gated and accurately labeled.
- [ ] All returned recommendations pass independent primal, bound, integrality, and objective checks.
- [ ] Feasible-limit, infeasible, unbounded, invalid, and error states are not mislabeled optimal.
- [ ] Relaxations are explicit and never weaken non-relaxable constraints.

### Handoff and operations

- [ ] Public Python API, CLI, example config, and minimal examples are documented.
- [ ] Unit, property, golden, integration, portability, and benchmark tests pass.
- [ ] `EXAMPLES.md` E1-E9 have executable synthetic fixtures with reviewed expected results.
- [ ] `TRACEABILITY.md` links every implemented requirement to exact code/test/CI evidence and the
      applicable release approval.
- [ ] Audit output contains lineage and hashes without leaking sensitive records.
- [ ] Objective attribution and structured reason codes explain material allocation changes.
- [ ] Production assumptions and remaining decisions are signed off by business, risk/control, and
      engineering owners.
- [ ] Platform authorization, correlation, schema, and idempotency references are retained without
      importing platform identity/session objects into the optimizer core.

---

## 30. Handoff Notes

Implementation should begin with T01-T06, T34-T35, and the golden fixtures before any solver-native
model code. The first vertical slice is T01-T12 plus T17/T34 using only the default LP and one-day
baseline, invoked through both the public facade and QR Haven adapter. Scenario support then reuses
the same request pipeline rather than creating a second formulation path.

Do not copy the current greedy locate allocator as the optimization engine; it can provide comparison
fixtures, but it does not jointly represent inventory balances, existing-loan churn, utilization,
counterparty limits, or scenarios. Likewise, reuse QR Haven borrow-demand outputs only through the
adapter contract. The modular optimizer owns allocation decisions and validation, while upstream
models own forecasts.

Agency and prime development begins only after the baseline family passes its golden and platform-
equivalence tests. Implement T36-T37 and T38-T39 as separate opt-in increments; neither family may
change baseline compiled rows, objective terms, verifier behavior, or results when disabled.

The implementation is considered faithful to this specification only if the mathematical balances,
unit conventions, strict-versus-repaired distinction, one-way platform dependency rule, and independent
verification remain intact. Internal class names may evolve if the same responsibilities and public
contracts are preserved.

# Engine Spec Integrated Delivery Roadmaps

## Document Purpose

This document turns the inventory-optimization specification into coordinated delivery roadmaps.
It is sequencing guidance, not a replacement for the requirements in `01_SPEC.md`.

| Document | Authority |
| --- | --- |
| `01_SPEC.md` | Product, mathematical, architectural, and acceptance requirements |
| `ROADMAPS.md` | Release sequencing, dependencies, gates, ownership, and prioritization |
| `DICTIONARY.md` | Canonical vocabulary, symbols, units, statuses, and reason codes |
| `WHITEPAPER.md` | Technical rationale, model narrative, and research context |
| `EXAMPLES.md` | Deterministic worked cases and golden-fixture expectations |
| `TRACEABILITY.md` | Requirement coverage, planned evidence, task, release, and gate mapping |

No calendar dates are committed here because team size, data entitlements, and deployment target
have not been fixed. Releases advance by evidence-based gates, not elapsed time.

---

## 1. North-Star Outcome

Deliver a modular, point-in-time-correct securities-lending optimizer integrated into the existing
platform that recommends how much inventory to retain, recall, source, or allocate; explains why;
evaluates trades and shocks; supports approved agency and prime desk profiles; and remains portable
to its own repository.

The desired progression is:

```text
correct balances
    -> economically rational LP
    -> existing-platform adapter and invocation contract
    -> immutable what-if scenarios
    -> point-in-time production data
    -> expected realized economics
    -> agency and prime desk problem families
    -> discrete operating rules
    -> uncertainty and multi-period timing
    -> approved substitution and joint pricing
```

The roadmap never trades away these invariants:

- exact inventory conservation;
- internal books/contracts/limits as authoritative;
- no backtest look-ahead;
- no silent constraint relaxation;
- normalized solver status and independent verification;
- attributable objective values;
- one-way QR Haven integration with core-package independence from QR Haven and vendor SDKs;
- owner-level conservation for agency mode and source/client-demand conservation for prime mode.

---

## 2. Release Roadmap

| Release | Outcome | Included spec tasks | Depends on | Release gate |
| --- | --- | --- | --- | --- |
| M0 | Approved design handoff | Documentation set | none | Business, quant, engineering, and control review |
| R0 | Portable package and platform-integration foundation | T01-T05, T19, T34-T35 | M0 | Contracts/config/lineage/adapter/portability tests pass |
| R1 | Verified baseline LP integrated into QR Haven | T06-T12, T17 | R0 | Golden, reconciliation, objective, and platform-invocation tests pass |
| R2 | Trade and shock scenarios | T13-T14 | R1 | Batch equals isolated solves; baseline stays immutable |
| R3 | Production data and schedule realism | T20-T24, T29-T31, T33 | R1, R2 | Point-in-time, eligibility, collateral, event, entity, and economics gates pass |
| D1 | Agency lending profile | T36-T37, T40 agency scope | R3, T34-T35 | Owner, mandate, indemnification, fairness, and attribution gates pass |
| D2 | Prime inventory financing profile | T38-T40 | R3, T34-T35 | Source/client conservation, authority, cost, and balance-sheet gates pass |
| R4 | Discrete operations and collateral allocation | T15, optional T32 | R1, selected R3 data | MIP logic, collateral conservation, and incumbent-quality tests pass |
| R5 | Risk-aware allocation | T18, T25-T26 | R3 | QP/robust model validation and downside evidence pass |
| R6 | Multi-period operations | T27 | R2, R3 | Daily conservation and settlement/recall timing tests pass |
| R7 | Transformation and pricing research | T28 plus approved NLP/PWL tasks | R4-R6 as applicable | Separate model-risk approval |
| R8 | Optional repository extraction/dedicated service | Packaging and deployment backlog | Stable R3 minimum | Existing-platform compatibility plus portability/recovery/security tests pass |

### Recommended production threshold

R1 is a valid research baseline inside the existing platform. R2 is a useful what-if tool.
Production decision support should not
begin before R3's point-in-time data, calendar/corporate-action, and expected-economics controls are
in place. D1/D2 and R4-R7 remain opt-in capabilities driven by desk requirements.

---

## 3. Milestone Details

### M0 — Design approval

Deliverables:

- reviewed use cases and non-goals;
- approved inventory definitions and units;
- approved source-of-truth hierarchy;
- agreed fee/rebate perspective and planning horizon;
- documented legal non-relaxable constraints;
- approved eligibility/collateral schedule authority, precedence, and conflict behavior;
- approved QR Haven/optimizer ownership and invocation boundary;
- initial agency/prime source, mandate, and hard-versus-soft policy definitions;
- initial fixture pack covering easy, scarce, term, and trade-driven cases.

Exit evidence:

- stakeholders resolve or accept V0 defaults in `01_SPEC.md` Section 28;
- every ambiguous source field has a named owner and mapping decision;
- no one interprets the optimizer as an execution or booking system.

### R0 — Portable package foundation

Build:

- nested standalone project and dependency groups;
- frozen Pydantic contracts and unit helpers;
- layered configuration and stable hashes;
- component decorators/registries and solver protocols;
- validation issue aggregation;
- bitemporal lineage contracts and vendor-neutral data ports;
- schedule envelopes and interfaces without mutable policy hidden in services;
- platform invocation context, canonical adapter contract, and problem-family registry;
- portability test with QR Haven removed from `PYTHONPATH`.

Exit evidence:

- invalid inventories fail before formulation;
- unknown config keys/components/capabilities fail closed;
- request/config serialization is deterministic;
- in-process and serialized platform fixtures produce equivalent canonical results;
- core imports do not load pandas, Bloomberg connectivity, HiGHS, or QR Haven unintentionally.

### R1 — Verified baseline LP

Build:

- elasticity-adjusted demand caps;
- route bounds, inventory equalities, utilization/reserve, demand, and counterparty constraints;
- fee, reinvestment, variable, increase, recall, and soft-policy objective terms;
- sparse compiler and HiGHS LP adapter;
- independent primal/objective verifier;
- allocation, balance, demand, attribution, and explanation outputs;
- Python facade and CLI; and
- QR Haven platform adapter using the canonical invocation/result contract.

Exit evidence:

- all Section 24 golden/property tests pass;
- no balance residual exceeds tolerance;
- objective attribution reconstructs solver value;
- corrupt synthetic solver outputs are rejected;
- small/desk benchmark compilation is sparse and deterministic.

### R2 — Scenario analysis

Build:

- BUY, SELL, TRANSFER_IN/OUT, NEW_LOAN, RETURN, and RECALL overlays;
- rate, demand, inventory, and policy shocks;
- effective-date ordering and settlement-aware eligibility hooks;
- baseline-versus-scenario comparison and reason codes;
- compatible matrix reuse across scenario batches.

Exit evidence:

- an empty scenario equals baseline;
- baseline object/hash remains unchanged;
- batch and isolated scenario results agree;
- a sale either identifies required recalls or returns a structured infeasibility;
- no trade price P&L is mixed into lending economics.

### R3 — Production data realism

Build in two sub-releases.

#### R3A — Data correctness

- versioned Bloomberg field mapping and adapter health check;
- effective-dated security identity, terms, market, currency, and status;
- market/settlement calendars and cutoffs;
- corporate-action lineage, amendments, cancellations, and quantity transformations;
- internal-versus-vendor reconciliation workflow;
- approved legal-entity/ultimate-parent mappings;
- deterministic eligibility resolution with deny/grandfather/recall-only actions;
- collateral schedule contracts, haircut convention, valuation freshness, and validate-only mode.

#### R3B — Expected economics

- take-up probability and expected active horizon;
- return, recall, and repricing hazards;
- manufactured-payment/event costs;
- dynamic availability buffers;
- liquidity-aware PWL transition costs;
- collateral-capacity and concentration constraints where collateral availability matters;
- fee, term, voting/event, settlement, and operating schedule compilation;
- calibration against realized loans, recalls, fails, and costs.

Exit evidence:

- historical runs use only information observed by their simulated as-of;
- security/corporate-action changes do not rewrite history;
- internal hard records cannot be silently overwritten by Bloomberg data;
- expected and contractual run-rate economics are reported separately;
- every predictive coefficient has version, calibration date, uncertainty, and fallback;
- every schedule-derived bound/row retains rule, version, approval, and effective-time lineage;
- existing term loans are not made immediately recallable by a new restrictive schedule;
- collateral coverage and haircut conversion verify independently when applicable.

### D1 — Agency lending profile

Build:

- beneficial-owner mandates and separate owner/pool/security balances;
- owner-specific borrower, collateral, term, voting, tax, utilization, and event rules;
- fee splits, minimum fees, benchmark policy, servicing and transition costs;
- indemnification exposure, capital/cost attribution, limits, and stress scenarios;
- contractual allocation rules, optional soft fairness, and MIP exclusives where approved;
- owner-level allocation, economics, opportunity-cost, compliance, and exception reporting; and
- platform adapter mappings for owner/account authority and approval context.

Exit evidence:

- no owner inventory is commingled or transformed without explicit authority;
- balances and objective attribution reconcile by owner, pool, security, borrower, and agreement;
- hard mandate rules and soft fairness preferences are distinguishable in results;
- indemnification economics are separately visible and independently reconstructed; and
- disabling agency components reproduces the baseline family.

### D2 — Prime inventory financing profile

Build:

- owned, client-reuse, affiliate, and external-borrow inventory sources;
- client short, locate, pre-borrow, settlement, return, recall, fail, and buy-in lifecycle states;
- internalization and external-source network flows with expiry, capacity, cost, and stability;
- client-consent/rehypothecation, agreement/netting-set, entity, collateral, and source rules;
- funding, leverage, capital, liquidity, encumbrance, and settlement budgets;
- client/source/legal-entity matched-book economics and replacement-cost attribution; and
- prime source/client scenarios and platform-facing reports.

Exit evidence:

- every inventory source and client demand conserves exactly;
- client and affiliate inventory are unavailable without affirmative effective authority;
- settled obligations cannot be silently unfilled;
- external quotes are freshness/expiry checked and not treated as guaranteed unless committed;
- all funding, collateral, capital, fail, and external-borrow economics reconstruct; and
- disabling prime components reproduces the baseline family.

### R4 — Discrete operations

Build only for approved business needs:

- all-or-none and minimum-active tickets;
- integer shares or lot multiples;
- fixed route activation costs;
- route cardinality/mutual exclusion;
- discrete fee-tier choice;
- whole collateral lots, minimum transfers, or discrete substitutions when joint collateral
  allocation is explicitly in scope;
- time/gap limits and incumbent acceptance policy.

Exit evidence:

- independent integrality and logical-rule checks pass;
- big-M values are derived from tight supply/demand bounds;
- `FEASIBLE_LIMIT` is never labeled `OPTIMAL`;
- disabling discrete components reproduces R1 behavior.

### R5 — Risk-aware allocation

Candidate increments:

- convex allocation-stability or concentration QP;
- censoring-aware hierarchical demand/elasticity forecasts;
- robust parameter budgets;
- scenario CVaR of revenue shortfall, recall cost, or settlement failure.

Exit evidence:

- PSD/capability/scaling checks pass for QP;
- forecast evaluation is walk-forward and point-in-time;
- robust result reports deterministic opportunity cost or “price of robustness”;
- downside improvement is shown out of sample, not only in training scenarios.

### R6 — Multi-period operations

Build:

- daily/time-bucket lendable, on-loan, available, reserve, and committed balances;
- settlement-date buys/sells/transfers;
- recall notice, expected returns, and corporate-action transformations;
- discounted daily economics and terminal conditions;
- decomposition/model-reuse benchmarks if required by scale.

Exit evidence:

- conservation holds for every pool/security/time bucket;
- no event settles on an invalid calendar date;
- single-period inputs reduce to the R1 result where assumptions match;
- future events do not affect earlier decisions unless explicitly modeled as known scenarios.

### R7 — Transformations and joint pricing

Research candidates:

- approved ADR/share-class/cross-list conversion network;
- ETF creation/redemption or other fungible inventory paths;
- basis, FX, tax, capacity, and settlement costs;
- continuous or discrete joint fee/quantity optimization;
- SCA, PWL MIP, or optional NLP backend.

Exit evidence:

- every transformation has legal/operational approval and effective-dated terms;
- common issuer identity is never treated as fungibility;
- local versus global optimality is labeled correctly;
- approximation and initialization sensitivity are quantified;
- an R1/R3 feasible fallback remains available.

### R8 — Optional extraction and dedicated production service

The existing platform remains the default deployment. Build this release only when independent
scaling, runtime isolation, ownership, or release requirements justify extraction:

- dedicated repository or independently released package;
- CI, dependency/security scanning, artifact signing, and release policy;
- API/batch service adapter, authentication/authorization, quotas, and timeouts;
- audit persistence, metrics, alerts, runbooks, backup/recovery, and rollback;
- QR Haven integration changed from in-platform adapter to external consumer without changing the
  canonical request/result contract.

Exit evidence:

- copied/extracted project passes the same conformance suite;
- existing in-platform and extracted transports produce equivalent canonical results;
- repeatable deployments and rollback are demonstrated;
- data entitlements and proprietary output controls are reviewed;
- optimizer failure cannot create an unverified downstream instruction.

---

## 4. Parallel Workstream Roadmaps

### 4.1 Mathematical model

```text
balance LP
  -> scenario LP
  -> expected-coefficient LP/PWL
  -> business-rule MIP
  -> convex QP / robust LP / CVaR LP
  -> multi-period LP/MIP
  -> transformation network and NLP/PWL pricing
```

Rule: no advanced formulation proceeds without a frozen small fixture where its incremental behavior
can be explained relative to the simpler formulation.

### 4.2 Data and Bloomberg enrichment

```text
business concepts
  -> versioned field mapping
  -> bitemporal raw-to-normalized adapter
  -> security/entity/event reconciliation
  -> point-in-time feature snapshots
  -> model coefficients with uncertainty
  -> realized-outcome calibration and monitoring
```

Rule: vendor access is healthy only when required concepts—not merely an API connection—are fresh,
entitled, mapped, and reconcilable.

### 4.3 Eligibility, collateral, and constraint schedules

```text
approved schedule contracts
  -> bitemporal version selection
  -> authority/specificity/priority resolution
  -> route bounds and group rows
  -> collateral validate-only mode
  -> collateral capacity constraints
  -> optional joint collateral allocation and substitutions
```

Rule: schedule data always retains authority, owner, approval, effective/observed time, rule ID, and
reason. A permissive lower-authority rule cannot override a safety denial or non-relaxable rule.

### 4.4 Desk operating models

```text
shared verified inventory kernel
  -> problem-family and desk-profile registry
  -> agency owner balances/mandates/indemnification
  -> prime source/client coverage network
  -> desk scenarios and attribution
  -> optional desk-specific MIP/QP/multi-period/pricing extensions
```

Rule: agency and prime families may add typed records and components but cannot alter shared unit,
eligibility, inventory-conservation, status, or verification semantics. Desk features remain opt-in.

### 4.5 Engineering platform

```text
portable package
  -> typed contracts/config
  -> QR Haven adapter/invocation context
  -> sparse compiler/solver adapter
  -> verifier/result schema
  -> batch scenario runner
  -> benchmark/observability
  -> service/deployment adapters
```

Rule: platform objects, solver-native objects, vendor clients, and dataframes do not cross into
domain contracts.

### 4.6 Validation and governance

```text
unit/golden cases
  -> property/conformance tests
  -> walk-forward shadow runs
  -> challenger comparison
  -> controlled recommendations
  -> monitored production use
```

Rule: model sophistication is promoted only when it improves a predeclared metric without breaking
correctness, stability, or interpretability guardrails.

### 4.7 Integration

```text
canonical facade/contracts
  -> in-platform QR Haven adapter
  -> internal book/limit/data adapters
  -> Bloomberg enrichment adapter
  -> reporting/terminal adapter
  -> optional worker/service transport
  -> optional later repository extraction
```

Rule: the optimizer never becomes the source of truth for inventory or contracts, and no integration
may bypass request validation or solution verification.

---

## 5. Dependency Map

```text
M0 approved definitions
        |
        v
R0 contracts/config/lineage/platform adapter -------------+
        |                                                   |
        v                                                   v
R1 LP/compiler/HiGHS/verifier ---> R2 scenarios ---> R3A point-in-time data
        |                             |                    |
        |                             +----------+---------+
        |                                        v
        +---------------------------> R3B expected economics
                                                 |
                    +----------------------------+------------------+
                    v                            v                  v
             D1 agency profile            D2 prime profile    R4 MIP
                    |                            |                  |
                    +---------------+------------+------------------+
                                    |
                           +--------+---------+
                           v                  v
                        R5 risk          R6 multi-period
                           |                  |
                           +--------+---------+
                                    v
                            R7 transformations/pricing
                                    |
                                    v
                       R8 optional extraction/service
```

Critical path for core production decision support: `M0 -> R0 -> R1 -> R2 -> R3A -> R3B`.
Agency and prime paths then proceed through D1 or D2 respectively; they do not block one another.

---

## 6. Evidence and KPI Roadmap

### 6.1 Correctness gates

| Metric | Required behavior |
| --- | --- |
| Inventory balance | No verified residual above configured tolerance |
| Bound/row feasibility | No unreported primal violation above tolerance |
| Objective reconstruction | Component sum agrees with unscaled objective within tolerance |
| Integrality | No MIP variable outside integrality tolerance |
| Point-in-time leakage | Zero known future-observation violations in conformance fixtures |
| Scenario isolation | Baseline hash/object unchanged after batch execution |
| Status integrity | No feasible-limit/error/infeasible result labeled optimal |
| Schedule resolution | Same bitemporal inputs always select the same approved rule set and row lineage |
| Collateral coverage | Recognized credit, capacity, concentration, and assignment conservation independently verify |
| Platform equivalence | In-process and serialized invocation fixtures return equivalent canonical results |
| Agency owner conservation | No unexplained residual or unauthorized cross-owner flow |
| Prime source/client conservation | Every sourced share maps once to eligible client demand and every hard obligation is covered or infeasible |

### 6.2 Economic evaluation

Establish baselines before setting production thresholds:

- expected and realized lending revenue;
- revenue per lendable dollar and per unit of scarce inventory;
- fee uplift net of recall/setup/event/liquidity cost;
- fill rate and unfilled high-value demand;
- utilization by security/pool without exceeding buffers;
- allocation churn and recall volume;
- settlement fails, buy-ins, and missed corporate-action elections;
- downside revenue/recall-cost quantiles under scenarios;
- delta versus current desk policy and a transparent greedy challenger;
- agency owner revenue/opportunity-cost distribution and indemnification-adjusted return;
- prime internalization, external replacement cost, matched-book margin, and balance-sheet return.

### 6.3 Operational evaluation

- compile, solve, verify, and end-to-end latency by problem shape;
- scenario throughput and matrix-reuse benefit;
- infeasible/invalid/stale-data rates;
- MIP incumbent gap and timeout rate;
- adapter freshness, mapping coverage, and reconciliation breaks;
- explanation coverage for material route changes;
- recommendation acceptance, override, and post-trade outcome rates;
- platform idempotency conflicts, duplicate-result reuse, cancellations, and transport-equivalence
  failures;
- agency mandate exceptions and prime source-expiry/reuse-authority/coverage exceptions.

No revenue uplift target is approved until the historical counterfactual methodology addresses
censored demand, fee endogeneity, selection bias, and transaction timing.

---

## 7. Decision Gates

| Gate | Required decision | Owner group |
| --- | --- | --- |
| G0 | Inventory and rate conventions | Business + operations + quant |
| G1 | Hard versus soft policies and non-relaxable constraints | Business + risk/control + legal |
| G2 | Bloomberg concepts, delivery, entitlements, and retention | Data owner + licensing + engineering |
| G2A | Eligibility schedule authorities, actions, precedence, and exceptions | Legal/control + operations + business |
| G2B | Collateral schedules, haircut convention, valuation, capacity, and wrong-way risk | Credit/collateral risk + operations + legal |
| G2C | Existing-platform ownership, invocation, authorization reference, idempotency, and result workflow | Platform + security + business + engineering |
| G2D | Agency mandates, owner pooling, fairness, indemnification, and reporting | Agency business + legal + risk/control + operations |
| G2E | Prime reuse authority, client coverage, sourcing, funding/capital, and reporting | Prime business + legal + credit/market risk + treasury/operations |
| G3 | Expected-economics model promotion | Quant research + model risk + business |
| G4 | Acceptable MIP gap/time-limit incumbent | Business + risk/control + engineering |
| G5 | QP/robust/CVaR objective and risk appetite | Model risk + business |
| G6 | Multi-period horizon and scenario probabilities | Quant + operations + model risk |
| G7 | Security transformations/fungibility | Legal + operations + risk + business |
| G8 | Production deployment and downstream use | Technology risk + business owner |

An unresolved gate defaults to the simpler, stricter behavior defined in `01_SPEC.md`.

---

## 8. Ownership Matrix

| Capability | Accountable | Responsible contributors | Required reviewers |
| --- | --- | --- | --- |
| Inventory semantics | Securities-lending business owner | Operations/data engineering | Quant, control |
| Mathematical formulation | Quant lead | Optimization engineers | Business, model risk |
| Solver/compiler/verifier | Engineering lead | Optimization engineers | Quant, platform engineering |
| Legal/eligibility rules | Control/legal owner | Operations/config owners | Engineering, business |
| Collateral schedules and valuation | Collateral/credit risk owner | Collateral operations + data engineering | Legal, quant, business |
| Demand/elasticity/hazards | Quant research owner | Data scientists | Model risk, business |
| Bloomberg mapping/lineage | Data product owner | Data engineering | Licensing, quant, operations |
| Corporate actions/calendars | Operations owner | Data engineering | Business, control |
| Scenario framework | Product/business owner | Quant engineering | Risk/control |
| QR Haven integration | Platform owner | Platform + optimization engineering | Security, business, technology risk |
| Agency problem family | Agency lending owner | Quant engineering + operations | Legal, collateral/credit risk, model risk |
| Prime problem family | Prime financing owner | Quant engineering + treasury/operations | Legal, credit/market risk, model risk |
| Optional dedicated service/extraction | Platform owner | Software/SRE/security | Business, technology risk |

Named people and escalation paths belong in the implementation project runbook, not this portable
specification.

---

## 9. Release and Change Control

Each release must include:

1. frozen config/component manifest and dependency lock;
2. schema migration and compatibility note;
3. golden/conformance results;
4. benchmark comparison against the previous release;
5. model/data change note and affected metrics;
6. rollback instructions;
7. known limitations and disabled capabilities;
8. approvals required by its decision gate.
9. updated `TRACEABILITY.md` status/evidence links for requirements completed or changed.

Changes to inventory equations, units, source authority, status semantics, non-relaxable constraints,
or point-in-time rules require an architecture/model decision record and updates to the complete
Engine Spec document set.

---

## 10. Immediate Next Actions

1. Approve M0 definitions, especially `total_lendable`, fee perspective, horizon, hard policies, and
   eligibility/collateral schedule authority.
2. Approve the QR Haven/optimizer responsibility table and initial in-process or worker invocation.
3. Select four to six anonymized core golden cases and at least one agency and one prime case.
4. Confirm Bloomberg business concepts and entitlements; do not begin with field mnemonics.
5. Scaffold R0 and implement contracts/config/lineage, platform invocation, and schedule envelopes
   before HiGHS code.
6. Build R1 as one vertical slice with independent verification.
7. Run R1 beside the current allocation process before enabling advanced objectives.
8. Implement R2 proposed-sale and fee/demand shock scenarios.
9. Promote R3A before any historical performance claim or production recommendation.
10. Enable D1 and D2 independently after their desk-specific authority and golden cases are approved.

The recommended first implementation pull request should contain only the R0 scaffold, contracts,
configuration loader, platform invocation contract, problem-family registries, and validation tests.
The first solver pull request should then be small enough to prove the golden LP end to end through
both the public facade and QR Haven adapter.

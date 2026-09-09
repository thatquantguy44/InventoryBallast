# Engine Spec Canonical Dictionary

## Purpose

This dictionary is the terminology and notation authority for the inventory-optimization project.
Code, configuration, APIs, reports, tests, and other Engine Spec documents should use these definitions.
When an upstream system uses a conflicting term, its adapter must map that term explicitly rather
than changing this dictionary implicitly.

Related documents:

- `01_SPEC.md` defines requirements and equations.
- `ROADMAPS.md` defines delivery sequence and gates.
- `WHITEPAPER.md` explains the technical rationale.
- `EXAMPLES.md` defines hand-calculable golden expectations.
- `TRACEABILITY.md` maps requirements to implementation and evidence.

---

## 1. Canonical Inventory Identities

For one inventory pool and security at one effective time:

```text
total_lendable
  = gross_inventory - ineligible_inventory - policy_exclusions

available_to_lend
  = total_lendable - on_loan - reserved - committed_out

utilization
  = on_loan / total_lendable                 when total_lendable > 0
  = null                                     when total_lendable = 0
```

After a scenario:

```text
post_total_lendable
  = baseline_total_lendable
    + settled_buys
    - settled_sells
    + eligible_transfers_in
    - eligible_transfers_out
    + effective_corporate_action_delta

post_on_loan
  = sum(post_route_quantity)

post_available_to_lend
  = post_total_lendable - post_on_loan - post_reserved - post_committed_out
```

These are equalities. “Available” and “lendable” are not interchangeable.

---

## 2. Units and Representations

| Concept | Canonical internal representation | Display examples |
| --- | --- | --- |
| Quantity | finite `float64` shares | `125,000 shares` |
| Price | USD per share in V0 | `$42.50/share` |
| Notional | quantity x price, USD | `$5,312,500` |
| Annual rate | decimal | `0.0175` = 175 bps = 1.75% |
| Basis point | `0.0001` in decimal-rate units | 25 bps = `0.0025` |
| Utilization/fraction | decimal in `[0,1]` | `0.92` = 92% |
| Elasticity | non-negative dimensionless magnitude | `0.6` |
| Transition cost | USD/share unless explicitly annual-rate based | `$0.003/share` |
| Timestamp | timezone-aware UTC | ISO 8601 |
| Business date | local-market date plus calendar identifier | `2026-09-03 / XNYS` |
| Day fraction | horizon days divided by configured basis | ACT/360 or configured basis |

Rules:

- APIs do not infer bps versus decimals from magnitude.
- Adapters convert currency before V0 optimization and preserve the FX observation lineage.
- Reports may round; calculations and verification use unrounded values.
- Integer or lot-constrained shares require MIP or an explicit rounding/repair pass.

---

## 3. Alphabetical Business and Data Glossary

### A

| Term | Canonical definition |
| --- | --- |
| Active route | A route whose post quantity exceeds the configured activity tolerance; in MIP it may additionally require an activation binary equal to one. |
| Agent lender | An intermediary that lends securities for beneficial owners. It may supply internal book data but is not assumed to be the beneficial owner. |
| Agency lending | Lending performed for beneficial owners under owner-specific mandates, economics, collateral rules, and reporting. The problem family preserves each owner's inventory and attribution. |
| Allocation | Shares assigned to a route. “Current allocation” is the baseline; “post allocation” is the optimized quantity. |
| Allocation decrease | `max(current_quantity - post_quantity, 0)`; generally a return, recall, or route reduction. |
| Allocation increase | `max(post_quantity - current_quantity, 0)`; a new or expanded loan. |
| Announcement time | Time a corporate event first became known to the firm. It differs from the event effective date. |
| As-of time | The decision cutoff. A run may use only observations known at or before this time, subject to explicit future-effective rules. |
| Available-to-lend (ATL) | Residual lendable shares after on-loan, reserved, and committed-out quantities. It cannot be negative in a verified result. |

### B

| Term | Canonical definition |
| --- | --- |
| Backtest | A historical simulation that reconstructs inputs using only information observable at each simulated as-of time. |
| Balance-sheet budget | Approved hard limit or soft cost curve for a named funding, leverage, capital, liquidity, encumbrance, or settlement-exposure measure. |
| Baseline | The immutable, validated state against which scenarios are compared. It may also mean the unchanged current allocation when calculating economic delta. |
| Beneficial owner | The economic owner whose inventory, restrictions, revenue share, voting preferences, and risk policy apply to a pool. |
| Best bound | A solver bound on the best possible objective for an unfinished MIP; used with the incumbent to calculate a gap. |
| Bid/offer spread | A market-liquidity input. It is not a securities-lending fee. |
| Big-M | A finite coefficient linking continuous and binary variables. It must be derived from tight supply/demand bounds, not an arbitrary huge number. |
| Bitemporal | Tracking both when a value applies economically and when it was observed/known. |
| Bloomberg adapter | Optional boundary code that maps licensed Bloomberg data into vendor-neutral project contracts. It is not part of the mathematical domain model. |
| Borrower | The approved counterparty receiving securities on a loan route. IDs are pseudonymous internal identifiers. |
| Borrower demand | Desired loan quantity before the optimizer applies firm inventory, eligibility, or limits. |
| Borrow fee | The economic rate charged for borrowing. Source conventions vary; adapters map it into the canonical lender-side `fee_rate`. |
| Bps | Basis points. One basis point is one ten-thousandth of an annual rate. |

### C

| Term | Canonical definition |
| --- | --- |
| Candidate route | An eligible potential allocation path, often with zero current quantity. |
| Capability | A formulation feature a solver/backend explicitly supports, such as LP, MIP, or continuous QP. |
| Cash collateral reinvestment | Income or cost from cash collateral after rebates and approved adjustments. In validate/capacity mode it may be a schedule-derived route coefficient; joint mode derives it from assigned cash collateral and may not also use the route coefficient. |
| Censored demand | True demand that is only partially observed because supply, limits, approval, or policy prevented a full request/loan outcome. |
| Chance constraint | A probabilistic requirement intended to hold with a specified confidence. Any approximation must be labeled. |
| Classification | Effective-dated sector, industry, country, asset, or risk grouping used for limits, peers, or scenarios. |
| Client inventory reuse | Prime use of client assets as an inventory source. It requires affirmative effective consent, legal/agreement authority, eligibility, and operational availability; it defaults to unavailable. |
| Client short demand | Prime-client requested, located, pre-borrowed, committed, or settled demand for security coverage with explicit timing and service semantics. |
| Collateral asset | Cash or security offered/assigned to support a loan exposure under an approved collateral schedule. |
| Collateral capacity | Maximum haircut-adjusted or market-value collateral available to support one or more routes. |
| Collateral coverage | Recognized collateral credit compared with required margin-adjusted loan exposure. |
| Collateral credit | Market value recognized after haircut, FX, concentration, and other approved adjustments. |
| Collateral schedule | Effective-dated approved rules for eligible collateral, margin, haircuts, valuation, concentration, capacity, substitution, settlement, reuse/segregation, and exceptions. |
| Committed-out quantity | Inventory promised or pending settlement and therefore unavailable for a new allocation, even if it is not yet on loan. |
| Component | A registered, stateless contributor to an objective or constraint set. |
| Component manifest | Deterministic list of problem family, components, versions, capabilities, variables, and rows used by a run. |
| Configuration hash | Stable digest of the fully merged, validated, canonical configuration. |
| Constraint | A mathematical restriction on decisions. It may be hard or explicitly soft. |
| Constraint schedule | Common versioned schedule envelope for eligibility, collateral, fee, term, settlement, event, capital, or operating constraints. |
| Contractual run-rate revenue | Revenue implied by current quantity, rate, share, and horizon without take-up/survival adjustments. |
| Corporate action | Effective-dated issuer/security event that may alter identity, quantity, cash flows, elections, voting needs, or tradability. |
| Counterparty | Legal entity or approved aggregate to which borrower exposure is attributed. |
| Counterparty limit | Internal credit/legal maximum by borrower, entity, parent, security, quantity, or notional. Bloomberg relationships may enrich mappings but do not authorize limits. |
| CVaR | Conditional Value-at-Risk, also called expected shortfall in many contexts; here a scenario-tail loss measure used only under an approved formulation. |

### D

| Term | Canonical definition |
| --- | --- |
| Data quality | Structured state describing validity, completeness, freshness, conflicts, and fallback of an input. |
| Day-count basis | Convention converting calendar days into a year fraction, such as ACT/360. |
| Decision variable | Quantity selected by the optimization model. |
| Demand cap | Maximum post-state quantity a demand group can absorb after fee elasticity, uncertainty haircut, and hard cap. |
| Demand elasticity | Non-negative magnitude describing how demand changes as fee changes. Under the default curve, positive elasticity means higher fee lowers demand. |
| Demand forecast | Point-in-time estimate of unconstrained demand with reference rate, uncertainty, model lineage, and optional cap. |
| Demand group | Routes that compete to fulfill the same borrower/security demand. Its semantic must be total post-state demand or explicitly incremental demand. |
| Demand shock | Scenario overlay multiplying, shifting, replacing, or re-quantiling demand assumptions. |
| Desk context | Problem family, platform tenant, booking/legal entity, desk, region, base currency, attribution scope, and effective time for a request. |
| Desk profile | Validated configuration selecting one registered problem family and its required components, inputs, outputs, and solver capabilities. |
| Deterministic | Repeated runs with identical inputs/config/backend controls produce the same ID-keyed result within tolerance. |
| Discrete fee tier | One candidate rate/quantity pair selected with binary variables in a pricing MIP. |
| Dual value | LP sensitivity value associated with a constraint under a stated sign/scaling convention. |

### E

| Term | Canonical definition |
| --- | --- |
| Economic effective time | Time from which a value/event applies to the modeled state. |
| Effective date | Date on which a scenario or policy affects the solve; not necessarily the trade or announcement date. |
| Eligibility | Legal, beneficial-owner, market, counterparty, and operational permission for a route or transformation. |
| Eligibility action | Resolved `ALLOW`, `DENY`, `GRANDFATHER`, `RECALL_ONLY`, or `REVIEW` decision for a route. |
| Eligibility schedule | Effective-dated approved rules that determine route permissions, bounds, reserves, minimum fees, terms, and required collateral schedules. |
| Entitlement | Licensed permission to access/use a vendor concept or dataset. An API connection alone does not prove entitlement. |
| Event risk | Expected or scenario risk arising from corporate actions, earnings, meetings, index changes, status changes, or other dated events. |
| Expected active fraction | Take-up probability times expected active days conditional on take-up, divided by planning-horizon days. |
| Expected realized revenue | Contractual economics adjusted for take-up, survival/return, repricing, event, and transition assumptions. It remains an estimate. |
| Explainability reason | Structured code derived from bounds, coefficients, slacks, duals, and allocation deltas. |
| External borrow quote | Effective, expiring candidate capacity from an approved lender/agreement with fee, collateral, term, settlement, stability, and all-in cost terms. It is not guaranteed unless contractually committed. |

### F

| Term | Canonical definition |
| --- | --- |
| Fee rate | Canonical annual decimal gross lender-side route rate before revenue share and modeled costs. |
| Fee shock | Scenario change to a route/group rate; it may also change demand through elasticity. |
| Feasible | Satisfies all compiled hard constraints and verified numerical tolerances. It does not imply optimal. |
| FIGI | Financial Instrument Global Identifier when licensed/available. It is an identifier mapping, not by itself proof of economic fungibility. |
| Fill ratio | Allocated quantity divided by effective demand cap, with null behavior defined when cap is zero. |
| Fixed activation cost | One-time cost incurred only when a route becomes active; normally requires MIP. |
| Forecast standard deviation | Demand uncertainty scale used by an approved haircut or scenario model. |
| Fungibility | Approved ability to use or convert one inventory form to satisfy another obligation. Common issuer or related identifiers alone do not establish it. |

### G–I

| Term | Canonical definition |
| --- | --- |
| GC / general collateral | Market label for relatively available, lower-fee inventory. It is descriptive and does not bypass model economics or limits. |
| Gross inventory | Shares economically recorded in a pool before ineligible inventory and policy exclusions. |
| Grandfather policy | Explicit treatment allowing an existing but no-longer-newly-eligible loan to remain or unwind under controlled bounds. |
| Haircut | Schedule-defined reduction from collateral market value to recognized collateral credit under the canonical convention. Source conventions must be converted explicitly. |
| Hard constraint | Rule that the normal solve cannot violate. Non-relaxable hard constraints remain hard in repair mode. |
| Hard maximum | Absolute cap applied after all transformations/elasticity. |
| HiGHS | Primary open-source backend for V0 LP and linear MIP, accessed only through the solver adapter. Other capabilities remain version/capability gated. |
| HTB / hard to borrow | Market label for scarce inventory, typically with higher/search-sensitive fees. It is an input classification, not a mathematical rule. |
| IIS | Irreducible infeasible subsystem: a minimal or irreducible set of mutually inconsistent constraints, if supported by diagnostics. |
| Incumbent | Best feasible MIP solution found so far. It may be returned as `FEASIBLE_LIMIT`, not `OPTIMAL`. |
| Indemnification policy | Approved definition of covered agency risks, beneficiary, exposure, limit, exclusions, stress method, and attributable capital/cost. |
| Ineligible inventory | Gross inventory excluded from lendable supply by legal, account, asset, event, or operational rules. |
| Instrument status | Effective-dated trading/listing state such as active, halted, suspended, or delisted. Treatment is policy-driven. |
| Integrality gap | Relative or absolute distance between incumbent objective and best bound in MIP. |
| Inventory ID | Unique identifier for one request's pool/security inventory record. |
| Inventory pool | Legal/operational source of lendable inventory, often a beneficial-owner account or aggregation allowed by policy. |
| Inventory source | Owned, beneficial-owner, client-reuse, affiliate, or external capacity that may supply a prime/agency route under explicit authority, timing, cost, and conservation rules. |
| Inventory transformation | Approved conversion or flow between securities/pools with ratio, capacity, cost, lag, and eligibility. |
| Internalization | Use of permitted internally controlled inventory to cover prime-client demand rather than acquiring an external borrow. Internal inventory still carries opportunity and balance-sheet costs. |

### L–N

| Term | Canonical definition |
| --- | --- |
| LEI | Legal Entity Identifier when available. It helps map entities but does not define an internal legal netting set. |
| Legal netting/aggregation set | Internally approved entity grouping for exposure/limits. Vendor hierarchy may propose relationships only. |
| Lendable-supply convention | Declaration of whether an upstream quantity includes or excludes on-loan/reserved shares. Ambiguous feeds are rejected. |
| Linear program (LP) | Optimization with continuous variables, linear objective, and linear constraints. Default formulation. |
| Lineage | Source, version, field mapping, observation/effective times, and transformation history for a value/result. |
| Liquidation horizon | Estimated time required to transact a quantity under stated market assumptions. It is not a guarantee. |
| Liquidity buffer | Available quantity retained to cover uncertainty, events, pending settlements, recalls, or unwind capacity. |
| Loan route | Possible post-state allocation from one inventory record to one borrower/demand group under specified terms. |
| Loan survival | Probability/distribution that an active loan remains outstanding over the horizon. |
| Locate | Borrower request or indication seeking confirmation of borrow availability. A locate is not necessarily an executed loan. |
| Lot size | Permitted quantity increment. Exact enforcement normally uses an integer lot variable. |
| Margin factor | Required collateral-credit multiple applied to loan exposure under the resolved collateral schedule. |
| Matched book | Prime financing view attributing client revenue against the specific internal or external inventory, funding, collateral, capital, and operating costs supporting it. |
| Manufactured payment | Payment compensating for an economic distribution while securities are on loan; tax/operational treatment comes from approved rules. |
| Market state | Point-in-time price, FX, volume, spread, volatility, depth/status, and quality snapshot. |
| MIP / MILP | Linear objective/constraints with one or more integer or binary variables. |
| Model version | Immutable identifier for prediction/formulation behavior and artifacts. |
| Multi-period model | Optimization with balances and decisions indexed by time bucket. |
| NLP | Nonlinear program with nonlinear objective or constraints; optional future capability. |
| Non-relaxable | Constraint category that explicit repair mode is forbidden to soften. |
| Notional | Shares multiplied by approved price, normally USD in V0. |

### O–P

| Term | Canonical definition |
| --- | --- |
| Objective | Scalar economic/policy criterion optimized by the solver. Component attribution must reconstruct it. |
| Objective attribution | Unscaled value of each objective term calculated independently from verified allocations. |
| Observed at | Timestamp when the firm received/knew a value or event version. |
| On-loan quantity | Shares currently or post-optimization allocated on routes. It is part of total lendable, not additional to it. |
| Opportunity cost | Value forgone by reserving, selling, transferring, or allocating inventory elsewhere. |
| Parent limit | Exposure limit aggregated over an internally approved parent hierarchy. |
| Planning horizon | Period over which objective economics are valued. It is distinct from solver runtime. |
| Platform adapter | QR Haven-owned integration module that assembles canonical requests and consumes canonical results without being imported by the optimizer core. |
| Platform invocation context | Opaque tenant, actor/authorization reference, correlation ID, idempotency key, schema version, and requested problem family supplied by the host platform. |
| Point-in-time correct | Uses only values observable as of the decision cutoff and economically applicable under defined rules. |
| Policy exclusion | Inventory removed from lendability by approved policy beyond intrinsic eligibility. |
| Post state | Optimized state after effective scenario changes. |
| Price of robustness | Nominal-objective sacrifice from a robust solution relative to the deterministic solution, reported with downside benefit. |
| Primal solution | Solver vector of decision-variable values. It becomes a recommendation only after independent verification. |
| Prime inventory financing | Problem family that sources permitted owned, client, affiliate, or external inventory to cover prime-client demand and attributes full financing economics. |
| Problem family | Registered request/result, component, verifier, and capability definition for one optimization domain. Families include the baseline `securities_lending_inventory` and opt-in `agency_lending` and `prime_inventory_financing`. |
| Pseudonymous ID | Stable internal code that avoids exposing a raw counterparty or owner name. |
| PWL | Piecewise-linear approximation or exact piecewise-linear representation using defined breakpoints. |

### Q–R

| Term | Canonical definition |
| --- | --- |
| QP | Quadratic program. The planned continuous QP uses a convex quadratic objective and linear constraints. |
| Rate ladder | Discrete candidate fees and their demand capacities. One-price behavior requires selection logic. |
| Rate shock | Scenario change to fee, rebate, reinvestment, funding, or other explicitly named rate. |
| Rebate rate | Cash-collateral convention-dependent rate returned to the borrower. Adapters convert it to canonical fee/reinvestment terms. |
| Recall | Lender-initiated request to return loaned securities. The model represents quantity, timing, cost, and feasibility. |
| Recall failure probability | Estimated probability shares are not returned by required time; a risk input, not a deterministic fact. |
| Reduced cost | LP sensitivity measure for changing a variable from its bound under local assumptions. |
| Reference fee | Fee at which reference demand was estimated. |
| Reference quantity | Unconstrained demand estimate at the reference fee. |
| Reinvestment rate | Net annual collateral reinvestment spread credited to route economics. |
| Repair mode | Explicit secondary solve that may soften only allow-listed constraints and reports every relaxation. |
| Repricing hazard | Probability/distribution of a change in an open-loan fee during the horizon. |
| Rehypothecation | Contractually and legally permitted reuse of collateral or client assets. It is never inferred merely from possession or control. |
| Reserve | Hard or policy-retained inventory unavailable for allocation. It must not be double-deducted upstream and in the model. |
| Return | Borrower-initiated or scheduled reduction of an outstanding loan. |
| Return hazard | Probability/distribution of borrower return timing. |
| Revenue share | Fraction of gross route fee economics credited to the optimized book/beneficial owner. |
| Robust optimization | Optimization designed to retain feasibility/performance over an explicit uncertainty set. |
| Route bound | Minimum/maximum feasible post quantity after eligibility, contract, demand, timing, and policy compilation. |
| Rule authority | Approved hierarchy determining which source/owner can issue or override a schedule rule. |
| Run trace | Stage timings, counts, hashes, warnings, versions, and diagnostics for one call. |

### S

| Term | Canonical definition |
| --- | --- |
| SCA | Sequential convex approximation: iterative solution of local convex subproblems for a nonlinear model. It provides local/KKT-style evidence, not automatic global optimality. |
| Scenario | Immutable named overlay on a baseline request or allowed policy. |
| Scenario hash | Stable digest of normalized scenario contents and relevant versions. |
| Schedule precedence | Deterministic safety-authority, specificity, explicit-priority, and hard-limit-intersection process used to resolve matching rules. |
| Schedule rule | Stable-ID, scoped, effective-dated instruction within a schedule, including action/limit, authority, owner, approval, priority, and reason. |
| Schedule version | Immutable bitemporal version of a schedule; revisions supersede rather than rewrite history. |
| Security ID | Canonical internal instrument identifier. Tickers are display labels, not primary join keys. |
| Settlement date | Date a trade/loan/recall movement becomes operationally effective under its market calendar and terms. |
| Shadow price | Interpreted LP dual sensitivity on a named constraint. It is local and is not a guaranteed transaction price. |
| Slack | Distance from a constraint bound, or an explicit violation variable for a soft constraint. The two meanings must be labeled. |
| Soft constraint | Target allowed to deviate through an explicit variable with a documented USD penalty and priority. |
| Solver backend | Adapter translating `CompiledProblem` to a native solver and returning normalized results. |
| Source of truth | System authorized for a data domain. Vendor enrichment does not silently supersede it. |
| Sparse matrix | Matrix storing nonzero coefficients rather than all possible cells; required for route-scale formulation. |
| Strict result | Result produced without relaxing configured hard policy. |
| Stochastic optimization | Model with decisions and outcomes across calibrated scenarios, often with first/second stages. |
| Substitution | Contractually permitted replacement of one collateral asset with another, subject to schedule, timing, coverage, and settlement rules. |

### T–Z

| Term | Canonical definition |
| --- | --- |
| Take-up probability | Probability that located/indicated or approved quantity becomes an active loan. |
| Term loan | Loan with contractual maturity or reduction restrictions represented in route bounds. |
| Total lendable | Eligible supply including shares already on loan. It excludes ineligible inventory and policy exclusions. |
| Trade event | Typed BUY, SELL, TRANSFER_IN/OUT, NEW_LOAN, RETURN, or RECALL scenario event. Input quantity is non-negative; direction comes from type. |
| Trade price P&L | Investment gain/loss on buying or selling the security. It is outside the lending objective. |
| Transition cost | One-time cost of increasing, decreasing, recalling, returning, or activating allocation. |
| Ultimate parent | Top approved entity in an effective-dated hierarchy used only after internal credit/legal validation. |
| Uncertainty haircut | Explicit reduction from mean demand/supply using a configured uncertainty measure. |
| Unfilled demand | `max(effective_demand_cap - allocated_quantity, 0)`. |
| Utilization | On-loan divided by total lendable for a nonzero lendable balance. |
| Utilization cap | Maximum permitted utilization, usually hard. |
| Utilization floor | Minimum required utilization, hard only when explicitly approved. |
| Utilization target | Preferred utilization. Default is informational unless a USD-valued soft penalty is enabled. |
| Validation issue | Structured code, severity, location, and context emitted before or after solve. |
| Variable index | Reversible mapping between domain variable keys and solver column numbers. |
| Vendor field mapping | Versioned configuration translating licensed source fields, units, nulls, and times into business concepts. |
| Verified solution | Primal result that independently passes bounds, rows, integrality, balances, and objective reconstruction. |
| Warm start | Prior primal/basis/incumbent information supplied to a compatible solve. It must not alter mathematical meaning. |
| What-if | Scenario result compared with an immutable baseline; not a booked action. |
| Wrong-way risk | Risk that collateral value/quality deteriorates together with counterparty or loan exposure; controlled by exclusions, add-ons, concentration, or scenarios. |

---

## 4. Mathematical Symbols

| Symbol | Meaning | Unit/domain |
| --- | --- | --- |
| `i in I` | Inventory record (pool/security) | index |
| `j in J` | Loan route | index |
| `g in G` | Demand group | index |
| `b in B` | Borrower or approved aggregate | index |
| `o in O` | Beneficial owner in agency mode | index |
| `s in S` | Permitted inventory source in prime mode | index |
| `d in D` | Prime-client demand/coverage obligation | index |
| `t in T` | Time bucket in multi-period extension | date/index |
| `J(i)` | Routes drawing from inventory `i` | set |
| `J(g)` | Routes serving demand group `g` | set |
| `J(b)` | Routes attributed to borrower `b` | set |
| `L_i` | Post-scenario total lendable | shares |
| `R_i` | Reserved quantity | shares |
| `C_i` | Committed-out quantity | shares |
| `P_i` | Approved price | USD/share |
| `O_i` | Post on-loan quantity | shares |
| `a_i` | Post available-to-lend decision | shares |
| `q0_j` | Current route quantity | shares |
| `q_j` | Post route quantity decision | shares |
| `inc_j` | Positive route change | shares |
| `dec_j` | Negative route change | shares |
| `lb_j`, `ub_j` | Post route bounds | shares |
| `f_j` | Annual route fee rate | decimal/year |
| `s_j` | Revenue share | fraction |
| `r_j` | Reinvestment rate | decimal/year |
| `h_j` | Collateral factor | fraction/multiplier |
| `c_j` | Annual variable cost rate | decimal/year |
| `k+_j`, `k-_j` | Increase/decrease cost | USD/share |
| `D_g` | Effective demand cap | shares |
| `Q_ref_g` | Reference demand | shares |
| `F_ref_g` | Reference fee | decimal/year |
| `epsilon_g` | Constant-elasticity magnitude | non-negative |
| `tau` | Objective horizon year fraction | years |
| `u_min`, `u_target`, `u_max` | Utilization policy levels | fraction |
| `z_j` | Route activation | binary |
| `m_g` | Unfilled demand auxiliary | shares |
| `c in C` | Eligible collateral asset/lot/type | index |
| `y_jc` | Collateral market value assigned from `c` to route `j` | USD |
| `H_jc` | Total canonical haircut for collateral `c` on route `j` | fraction |
| `A_c` | Available collateral market value | USD |
| `margin_factor_j` | Required collateral credit per loan exposure | multiplier |
| `x_sd` | Quantity sourced from inventory source `s` to client demand `d` | shares |
| `unfilled_d` | Explicit uncovered indicative demand; fixed to zero for hard settled obligations | shares |

Core equations:

```text
q_j - q0_j = inc_j - dec_j

sum(q_j for j in J(i)) + a_i = L_i - R_i - C_i

sum(q_j for j in J(g)) <= D_g

D_g(f) = Q_ref_g * (max(f, fee_floor) / F_ref_g) ** (-epsilon_g)
```

---

## 5. Normalized Solver Status Dictionary

| Status | Meaning | May include allocation recommendation? |
| --- | --- | --- |
| `OPTIMAL` | Backend proved optimality to configured tolerances and verifier passed. | Yes |
| `FEASIBLE_LIMIT` | Verified feasible incumbent exists, but time/node/gap/iteration limit stopped proof. | Yes, only under explicit incumbent policy |
| `INFEASIBLE` | No feasible solution exists for the submitted strict model according to backend/diagnostics. | No |
| `UNBOUNDED` | Objective can improve without finite bound. Usually signals formulation/config error. | No |
| `INFEASIBLE_OR_UNBOUNDED` | Backend cannot distinguish without additional analysis. | No |
| `INVALID_MODEL` | Input/formulation violates structural or capability requirements. | No |
| `NUMERICAL_ERROR` | Numerical failure prevents trusted result. | No |
| `INTERRUPTED` | External cancellation/interruption before accepted result. | Only if separately verified and policy allows |
| `SOLVER_ERROR` | Backend/API failure. | No |

`repaired` is an orthogonal result flag, not a solver status. A repaired optimum is not the strict
model optimum.

---

## 6. Scenario Event Codes

| Code | Supply effect | Route effect |
| --- | --- | --- |
| `BUY` | Adds eligible settled supply | None directly |
| `SELL` | Removes settled supply | May force decreases/recalls |
| `TRANSFER_IN` | Adds eligible destination-pool supply | None directly |
| `TRANSFER_OUT` | Removes source-pool supply | May force decreases/recalls |
| `NEW_LOAN` | None | Adds/changes candidate route and demand |
| `RETURN` | None unless feed semantics also alter commitments | Reduces specified current route baseline |
| `RECALL` | None directly | Requires/restricts reduction by effective time |

Signed input quantities are invalid. Direction is encoded by the event code.

---

## 7. Explanation Reason Codes

| Code | Meaning |
| --- | --- |
| `HIGHER_NET_FEE` | Allocation favored because verified incremental net economics were higher. |
| `DEMAND_CAP_BINDING` | No additional allocation was possible because effective demand was exhausted. |
| `INVENTORY_SCARCE` | Inventory equality/availability limited competing allocations. |
| `UTILIZATION_CAP_BINDING` | Configured maximum utilization limited on-loan quantity. |
| `RESERVE_BINDING` | Required availability/reserve buffer limited allocation. |
| `COUNTERPARTY_LIMIT_BINDING` | Approved borrower/entity exposure limit constrained allocation. |
| `INELIGIBLE_ROUTE` | Legal/owner/market/operational rule removed route capacity. |
| `TERM_OR_RECALL_RESTRICTION` | Contract/timing prevented a route decrease. |
| `TRANSITION_COST_EXCEEDS_UPLIFT` | Fee improvement did not cover increase/decrease costs. |
| `TRADE_REDUCED_SUPPLY` | Settled sell/transfer reduced lendable supply. |
| `ELASTICITY_REDUCED_DEMAND` | Higher evaluated fee or changed elasticity lowered demand cap. |
| `SOFT_TARGET_TRADEOFF` | Objective accepted an explicit soft-target deviation for better net value. |
| `EVENT_RISK_BUFFER` | Corporate/event risk increased reserve or cost. |
| `LIQUIDITY_BUFFER_BINDING` | Dynamic market-liquidity buffer limited allocation. |
| `EXPECTED_ACTIVITY_ADJUSTMENT` | Take-up/survival/repricing changed expected revenue ranking. |
| `ENTITY_AGGREGATION_BINDING` | Parent/affiliate aggregation caused a limit to bind. |
| `ELIGIBILITY_SCHEDULE_BOUND` | A resolved eligibility schedule denied, grandfathered, recalled, or capped a route. |
| `COLLATERAL_SCHEDULE_MISMATCH` | Route could not use the offered/required collateral under the effective schedule. |
| `COLLATERAL_CAPACITY_BINDING` | Haircut-adjusted collateral capacity limited lending exposure. |
| `COLLATERAL_CONCENTRATION_BINDING` | Collateral issuer/country/currency/asset concentration limited assignment. |
| `OWNER_MANDATE_BOUND` | An agency beneficial-owner mandate restricted or required the allocation. |
| `AGENCY_FAIRNESS_TRADEOFF` | An explicit soft agency fairness term changed allocation or incurred deviation. |
| `INDEMNIFICATION_COST` | Separately attributed indemnification exposure/cost affected route value. |
| `SOURCE_CAPACITY_BINDING` | A prime inventory source had no remaining authorized capacity. |
| `EXTERNAL_BORROW_SELECTED` | An approved external source was selected based on verified all-in economics and constraints. |
| `CLIENT_REUSE_NOT_AUTHORIZED` | Client inventory could not be used because effective consent/legal/agreement authority did not resolve. |
| `HARD_COVERAGE_REQUIREMENT` | A settled short, delivery, or committed pre-borrow required full coverage. |
| `BALANCE_SHEET_LIMIT_BINDING` | Funding, leverage, capital, liquidity, encumbrance, or settlement budget limited sourcing. |

Reason codes describe model evidence, not causal certainty about borrower behavior.

---

## 8. Ambiguous or Prohibited Usage

| Avoid | Use instead |
| --- | --- |
| “Lendables” without definition | `total_lendable` or `available_to_lend` |
| “Inventory” when balance stage matters | gross, total lendable, on-loan, reserved, committed, or available |
| “Rate” without perspective/unit | fee/rebate/reinvestment/funding rate plus annual decimal/bps |
| “Demand” based on approved loans | requested/unconstrained demand, or label it censored realized quantity |
| “Optimal” for a timed-out incumbent | `FEASIBLE_LIMIT` with gap/bound |
| “MIQP” for MIP selection followed by QP | two-stage MIP-to-QP heuristic/decomposition |
| “Real-time” without timestamp/SLA | observed-at time, delivery cadence, and freshness policy |
| “Bloomberg says” | named normalized concept, source/version, observation/effective time |
| “Same security” from ticker/issuer | approved effective-dated security identity or transformation |
| “Fungible” from common issuer | approved conversion/transformation contract |
| “Expected revenue” using only fee x quantity | contractual run-rate revenue, unless activity/cost adjustments are included |
| “Backtest” using revised current data | point-in-time backtest or label it retrospective reconstruction |
| “Constraint relaxed” without detail | named repaired constraint, slack amount, penalty, and approval |
| “Eligible” without schedule/time/scope | resolved eligibility action plus schedule/rule/version/effective time |
| “Fully collateralized” without convention | recognized collateral credit, required exposure, margin factor, haircut convention, and valuation time |
| “Standalone” to imply a separate initial platform | modular/extractable optimizer core integrated into the existing QR Haven platform |
| “Agency inventory” without owner | beneficial owner, pool/account, mandate, and effective availability |
| “Internal inventory is free” | explicit scarcity opportunity, funding, capital, collateral, and alternative-use cost assumptions |
| “Client inventory is available” | effective consent, reuse/rehypothecation authority, agreement, eligibility, location, and settlement capacity |
| “Prime demand” without lifecycle state | locate, pre-borrow, committed/settled short, forecast, return, or cover demand with effective time |

---

## 9. Naming Conventions

- IDs end in `_id`; opaque IDs are strings.
- Share quantities end in `_shares`.
- Annual decimal rates end in `_rate`; display-only basis points end in `_bps`.
- USD quantities end in `_usd`; per-share costs end in `_usd_per_share`.
- Fractions/probabilities are explicit (`_fraction`, `_probability`, `_utilization`).
- Timestamps end in `_at`; business/effective dates end in `_date`.
- Scenario-adjusted values use `post_` or `scenario_`; baseline values use `current_` or `baseline_`.
- Raw vendor fields stay inside adapter payloads. Domain names describe normalized business concepts.
- Config/component/status/reason names use lowercase snake case in serialized values unless the
  public enum explicitly specifies uppercase codes.

Any new public term must be added here in the same change that adds its contract or report field.

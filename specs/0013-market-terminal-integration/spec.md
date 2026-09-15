# Spec: Market Terminal Inventory Optimizer integration

- **ID:** 0013-market-terminal-integration
- **Status:** Approved for local and protected-staging implementation; production separately gated
- **Author:** Joshua Lutkemuller, CFA
- **Approver:** Joshua Lutkemuller, CFA (approved 2026-09-14)
- **Last updated:** 2026-09-14

> WHAT and WHY only. Implementation details and the QuantMeridian file-level handoff are in
> `plan.md`.

## Problem & Context

InventoryBallast is a portable Python optimization engine, but it has no interactive application
surface. Its public boundary accepts a validated `OptimizationRequest` and returns an
`OptimizationResult`; users currently need to construct JSON or Python objects and invoke the
facade or CLI themselves.

QuantMeridian's separate `market_terminal` repository already presents a dense, Bloomberg-style
operating environment for securities finance. It has an `OPT` Optimization Center, but that page
currently displays broad, simulated cross-domain run data. It does not execute InventoryBallast,
validate InventoryBallast inputs, or display InventoryBallast results. Replacing that page would
mix two distinct product concepts and create unnecessary blast radius.

The initial integration therefore needs its own module: a focused securities-lending Inventory
Optimizer workspace that calls InventoryBallast as the only optimization authority. It must work
before governed book feeds are connected. A user may deliberately create a reproducible synthetic
book, controlling its scale, concentration, utilization, fee regime, constraints, and random
variation, or deliberately upload their own data using downloadable, versioned templates.

The source choice must always be explicit. A failed upload must never turn into a plausible-looking
synthetic solve, and a synthetic run must never look like a live or uploaded book. Uploaded data may
be confidential, so the initial release processes it transiently, does not persist raw rows, and
does not put payload values in logs.

This handoff is grounded in these repository states:

- InventoryBallast `main` at `74737e53bf9821089c6aa2aeca5dffc4e67c81b7`, package version
  `0.1.0`, assessed 2026-09-14.
- QuantMeridian `origin/main` at `ec274543346d82c56c149168dd31f4371111df21`, with the current
  Vite/React route registry, navigation configuration, provenance vocabulary, and server API
  patterns assessed 2026-09-14.
- `0012-expected-economics-realism` is only partially implemented. Expected-economics inputs exist,
  but they must not be exposed as allocation-driving controls until that spec's T-007 through T-010
  are complete and advertised by a capability check.

## Goals

- Add a distinct, feature-flagged Inventory Optimizer module to QuantMeridian without changing the
  meaning or behavior of the existing `OPT` module.
- Preserve InventoryBallast as the sole owner of request validation, optimization mathematics,
  solver status, objective attribution, reason codes, and result verification.
- Give users an explicit choice between reproducible synthetic data and uploaded data.
- Let users shape synthetic books through understandable presets and bounded advanced controls,
  while guaranteeing the generated request satisfies structural and reconciliation invariants.
- Provide downloadable, versioned workbook and JSON templates with a complete data dictionary,
  examples, units, required/optional status, and field constraints.
- Validate and preview all data before solve, with actionable locations for every detectable issue.
- Present allocations, balances, demand fill, economics, binding constraints, warnings, solver
  diagnostics, and verification evidence in the terminal's existing dense visual language.
- Make every run reproducible and auditable through engine version, schema version, source mode,
  seed or upload hash, request hash, config hash, timestamps, and exportable normalized inputs.
- Ship with an explicit production kill switch, health reporting, resource limits, and no hidden
  synthetic fallback.

## Non-Goals

- Replacing or redesigning QuantMeridian's existing `OPT` Optimization Center.
- Connecting production books, Bloomberg, custodians, loan platforms, or any other live upstream
  source in the initial release.
- Adding authentication or entitlements to QuantMeridian. Production enablement is blocked unless
  an existing trusted deployment boundary or platform authorization reference is available.
- Reimplementing any InventoryBallast objective, constraint, validation, attribution, or
  verification calculation in TypeScript or in a QuantMeridian adapter.
- Training or calibrating elasticity, expected-economics, availability, or risk models.
- Exposing expected-economics direct mode, dynamic buffers, or other unfinished `0012` behavior.
- Multi-period optimization, scenario comparison, stress testing, fee-tier authoring, or arbitrary
  component configuration in the first module release.
- Inline spreadsheet editing, persistent portfolio storage, cross-user run history, scheduled runs,
  job queues, or asynchronous large-book solves.
- Executing recommended trades or writing results back to any source system.
- Treating generated data, uploaded data, or optimizer output as investment advice or an execution
  instruction.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | QuantMeridian shall expose a separate Inventory Optimizer module with its own mnemonic, navigation item, route, feature flag, page state, and API namespace; the existing `OPT` module shall remain unchanged. | must |
| REQ-002 | The integration shall invoke a pinned InventoryBallast package through its public contracts and facade; no QuantMeridian client, proxy, or service adapter shall duplicate optimization, validation, attribution, or verification logic. | must |
| REQ-003 | The workspace shall require an explicit `SYNTHETIC` or `UPLOAD` source selection and shall never automatically substitute one mode for the other after a generation, parse, validation, network, or solve failure. | must |
| REQ-004 | Synthetic generation shall accept and display a stable integer seed, fixed as-of timestamp, effective date, schema version, and generator version; identical inputs shall produce the same normalized request and request hash. | must |
| REQ-005 | Synthetic generation shall provide scale and market-shape presets plus bounded custom controls for universe size, inventory pools, borrowers and parent groups, route connectivity, supply and demand distributions, starting utilization, borrower concentration, fee regime and dispersion, elasticity, eligibility, reserves, current allocations, counterparty limits, and supported discrete-route features. | must |
| REQ-006 | Synthetic generation shall create internally consistent identifiers, foreign keys, currencies, balances, route quantities, demand groups, fee assumptions, effective dates, and hierarchy relationships by construction; generation shall return a preview and validation evidence before solve. | must |
| REQ-007 | The module shall offer downloadable, versioned starter workbook, blank advanced workbook, and canonical JSON templates. Templates shall identify every supported field's sheet/path, type, unit, required status, default, constraint, description, and valid example. | must |
| REQ-008 | Upload mode shall accept `.xlsx` workbooks matching the template and exact `OptimizationRequest` JSON. It shall enforce file type, size, row-count, sheet, column, formula, and schema-version rules before constructing engine contracts. | must |
| REQ-009 | Upload validation shall aggregate file, cell, field, and cross-record issues with stable codes and actionable sheet/row/column or JSON-path locations; it shall not silently infer units, repair balances, drop unknown columns, or ignore non-empty unknown sheets. | must |
| REQ-010 | Both source modes shall produce the same normalized dataset envelope containing the exact request, source disclosure, summary statistics, validation state, and canonical request hash, and shall show a pre-solve preview of the records that will be submitted. | must |
| REQ-011 | The module shall expose only an allowlisted initial run configuration: planning horizon, day-count basis, solver time limit, relative gap, threads, solver seed, validation staleness threshold, entity-confidence threshold, and allocation-stability penalty where supported. Unsupported or conflicting combinations shall fail closed. | must |
| REQ-012 | A solve shall be enabled only for a valid normalized request and healthy compatible backend. The service shall revalidate the request and configuration immediately before invoking the optimizer. | must |
| REQ-013 | Every solve shall pass an opaque platform invocation context, preserve InventoryBallast's normalized solver status and verification result, and return structured validation, configuration, timeout, solver, and internal-error responses without relabeling failures as successful runs. | must |
| REQ-014 | The result workspace shall display run identity/status, objective totals, allocation changes, inventory balances/utilization, demand fill, component economics, pricing selections when present, constraint activity/slack/duals, warnings, solver diagnostics, and verification evidence directly from `OptimizationResult`. | must |
| REQ-015 | The result workspace shall support route and inventory inspection, sorting/filtering, before-versus-after quantities, reason codes and evidence, and a binding-constraint view without manufacturing fields absent from the engine result. | must |
| REQ-016 | Users shall be able to download the normalized input JSON, raw result JSON, validation report, and the engine-owned tabular result projections as CSV files in a ZIP archive. | must |
| REQ-017 | The module shall keep the current prepared dataset and completed runs only in the user's browser session for the initial release, support reset and rerun, and require confirmation before replacing an unsaved prepared dataset. | should |
| REQ-018 | A versioned capability response shall disclose API schema version, generator version, pinned engine commit/version, backend/version, supported problem families, formulations, input features, output sections, upload formats, and limits; the UI shall hide or disable capabilities the service does not advertise. | must |
| REQ-019 | QuantMeridian Data Ops and the module shall report optimizer service reachability, compatibility, backend readiness, package version, and last error category without exposing uploaded payload values. | must |
| REQ-020 | Local, staging, and production enablement shall be independently controlled. Production shall default off, use a server-held service credential, enforce upload and solve limits, and have a documented kill switch and rollback path. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | Reproducibility | Same synthetic config, seed, timestamps, generator version, engine pin, and run config produce byte-identical normalized request JSON and identical deterministic result fields; only documented identity/runtime fields may differ. |
| NFR-002 | Calculation integrity | Browser and TypeScript server code perform presentation and transport only; all domain validation and result calculations come from the pinned Python contracts and engine helpers. |
| NFR-003 | Interactive performance | Synthetic preview and valid workbook parsing complete in <= 2 seconds at p95 for the medium reference dataset; a medium LP solve completes in <= 10 seconds at p95 on the documented reference runtime, excluding network transit. |
| NFR-004 | Capacity bounds | Initial synchronous service accepts at most 10 MiB per upload, 500 inventory rows, 10,000 route rows, 5,000 demand rows, and 5,000 rows across optional sheets; larger inputs are rejected before solve with a stable limit code. |
| NFR-005 | Security and privacy | Raw uploads, normalized rows, identifiers, and allocations are neither persisted server-side nor logged; service credentials remain server-side; macros, formulas, and unsupported archive content are rejected. |
| NFR-006 | Failure semantics | Network, parse, validation, configuration, timeout, incompatibility, infeasibility, numerical, and internal failures are visibly distinct and never trigger fallback data or a false `optimal` display. |
| NFR-007 | Usability and accessibility | The module supports keyboard operation, visible focus, labeled controls, error association, non-color status cues, and coherent layouts at 375x812, 768x1024, and 1440x900 without overlap or clipped control text. |
| NFR-008 | Contract compatibility | API and template contracts are versioned; breaking changes require a new major schema version, while additive engine fields are tolerated or capability-gated. |
| NFR-009 | Observability and testability | Every request has correlation/idempotency identifiers, structured metadata-only logs, latency/error counters, health checks, contract fixtures, deterministic unit tests, and an end-to-end browser-to-solver test. |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given the module flag is enabled, when QuantMeridian loads, then `IBAL` appears in the Optimization navigation group at `/inventory-optimizer`, while `/optimization` and `OPT` retain their prior behavior. | REQ-001 |
| AC-002 | Given a golden normalized request, when it is solved through the service and directly through the same pinned InventoryBallast facade/config, then all deterministic `OptimizationResult` fields match. | REQ-002, NFR-002 |
| AC-003 | Given upload mode and an invalid workbook, when validation fails, then no synthetic generation or solve occurs and the UI remains in upload mode with the upload errors visible. | REQ-003, NFR-006 |
| AC-004 | Given the same complete synthetic config twice, when generated twice, then normalized request bytes and canonical request hashes match; changing only the seed changes the generated observations while preserving schema validity. | REQ-004, NFR-001 |
| AC-005 | Given each named synthetic profile and minimum/maximum bounded custom settings, when generated, then the preview reflects the chosen scale, concentration, utilization, fee mix, and variation within declared tolerances. | REQ-005 |
| AC-006 | Given 100 seeded synthetic configurations, when each request is constructed and engine-validated, then every request has valid balances, foreign keys, group consistency, effective dates, hierarchy mappings, and finite bounded values. | REQ-006 |
| AC-007 | Given each download action, when the artifact is opened, then its declared schema version, data dictionary, required/optional markers, units, constraints, and examples agree with the service contract; the starter workbook and JSON example validate unchanged. | REQ-007, NFR-008 |
| AC-008 | Given a valid `.xlsx` template and equivalent JSON, when each is uploaded, then both normalize to the same request hash; unsupported types, oversize files, formulas, unknown columns, and incompatible schema versions are rejected with distinct codes. | REQ-008, NFR-004, NFR-005 |
| AC-009 | Given a workbook with multiple independent defects, when parsed, then one response reports every detectable issue with the correct sheet/row/column and no input row is silently repaired or discarded. | REQ-009 |
| AC-010 | Given either source mode, when preparation succeeds, then the preview shows source disclosure, row counts, key totals, request hash, as-of/effective dates, and representative records matching the normalized request sent to solve. | REQ-010 |
| AC-011 | Given each allowlisted run setting, when changed, then the normalized config reflects only that setting; an unknown setting or a MIP/QP conflict is rejected before solver invocation. | REQ-011 |
| AC-012 | Given a stale or subsequently invalidated prepared request, when solve is attempted, then service-side validation blocks the solve even if client-side state previously marked it valid. | REQ-012 |
| AC-013 | Given optimal, feasible-limit, infeasible, timeout, numerical-error, and internal-error fixtures, when returned, then the API and UI preserve their distinct statuses, verification evidence, and HTTP/error envelopes. | REQ-013, NFR-006 |
| AC-014 | Given an optimal golden result, when displayed, then every result tab and KPI can be traced field-for-field to the raw `OptimizationResult`, and the economics total reconciles to its component rows. | REQ-014 |
| AC-015 | Given a changed route and a binding constraint, when inspected, then the UI shows the engine's before/after quantities, reason codes/evidence, activity, slack, and dual without deriving an unsupported trade instruction. | REQ-015 |
| AC-016 | Given a completed run, when each export is downloaded, then normalized input and raw result round-trip through their Pydantic contracts and every CSV file matches `reporting.tables.result_tables()` names, columns, order, and values. | REQ-016 |
| AC-017 | Given an unsaved prepared dataset, when the user resets or selects a replacement file/profile, then confirmation is required; after confirmation, prior session data is removed and no server-side retrieval endpoint can recover it. | REQ-017 |
| AC-018 | Given a service that omits or disables a capability, when the UI loads its capability response, then the related control/template is absent or disabled and cannot be submitted by manually altering client state. | REQ-018, NFR-008 |
| AC-019 | Given healthy, unreachable, incompatible, and solver-unready services, when health is viewed in the module and Data Ops, then each state is distinct and includes version/readiness metadata but no uploaded values. | REQ-019, NFR-009 |
| AC-020 | Given production defaults, when the app is deployed without explicit enablement and credentials, then no navigation or solve endpoint is available; disabling the flag after launch removes access without an engine redeploy. | REQ-020 |
| AC-021 | Given the medium reference dataset, when generation, parsing, and LP solve benchmarks run on the documented reference runtime, then NFR-003's p95 thresholds pass and the exact runtime profile is recorded. | NFR-003 |
| AC-022 | Given an upload containing representative confidential identifiers, when requests and errors are exercised under log capture, then none of those values appear in application, proxy, or service logs. | NFR-005, NFR-009 |
| AC-023 | Given desktop, tablet, and mobile Playwright viewports plus keyboard-only navigation, when the complete synthetic and upload workflows are exercised, then all actions and errors remain reachable, labeled, non-overlapping, and readable without relying on color alone. | NFR-007 |
| AC-024 | Given the target repositories' CI commands, when the implementation is complete, then InventoryBallast contract tests, QuantMeridian Python service tests, TypeScript tests/typecheck, and the browser-to-solver flow all pass from clean checkouts using pinned dependencies. | NFR-009 |

## Data & Dependencies

- InventoryBallast is the source of truth for `OptimizationRequest`, `InventoryOptimizerConfig`,
  `PlatformInvocationContext`, `OptimizationResult`, validation, solve orchestration, and tabular
  projections. QuantMeridian pins an immutable commit or release including the `highs` extra.
- QuantMeridian is the source of truth for module registration, feature flags, UI state, server
  proxy conventions, provenance presentation, Data Ops, deployment configuration, and user-facing
  downloads.
- The initial upload contract supports USD-only inventory because `SecurityInventory` currently
  rejects all other currencies. The template states this explicitly; adapters must not imply FX
  conversion exists.
- Uploaded files and normalized requests may contain confidential position, borrower, and limit
  data. They are transient request data, never repository fixtures, analytics events, or logs.
- Synthetic data is generated inside the QuantMeridian-side Python service and is always labeled
  synthetic. Test/example identifiers must be obviously fictitious.
- The initial browser workflow depends on a separately deployable Python service because the
  optimizer and HiGHS backend are Python/native dependencies and must not be bundled into the Vite
  client or recreated in TypeScript.
- Exact target paths, contracts, templates, and dependency additions are pinned in `plan.md`.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | QuantMeridian duplicates optimizer calculations for convenient UI summaries. | Displayed values drift from verified engine results and users cannot reconcile decisions. | TypeScript is transport/presentation only; parity and field-lineage tests compare against the pinned facade and table builders. |
| RISK-002 | A failed upload silently falls back to synthetic data. | A plausible demo book may be mistaken for the user's book. | Source mode is explicit and sticky; every failure is terminal for that attempt; provenance is carried in every envelope and result view. |
| RISK-003 | Unseeded or time-dependent generation makes a synthetic run irreproducible. | A user cannot explain or recreate a result. | Seed, fixed timestamps, generator version, normalized request, and hashes are mandatory and exportable. |
| RISK-004 | Spreadsheet conveniences guess percentages, dates, units, or balance fields. | Inputs are materially changed before optimization without user approval. | Exact units and ISO formats; no unit inference, formula evaluation, row dropping, or balance repair. |
| RISK-005 | Uploaded book data reaches logs or durable storage. | Confidentiality breach. | Transient memory processing, metadata-only logs, payload redaction tests, no server run-history endpoint, strict upload controls. |
| RISK-006 | A public synchronous solve endpoint is abused or exhausts CPU/memory. | Service outage or cost spike. | Production off by default, server-held credential, request/row/time limits, concurrency limit, rate limiting at the trusted edge, kill switch. |
| RISK-007 | Engine and UI schemas drift across repositories. | Controls appear to work but fields are rejected or ignored. | Immutable engine pin, versioned capabilities/templates, generated OpenAPI/JSON Schema artifacts, startup compatibility check, contract CI fixtures. |
| RISK-008 | The initial UI exposes unfinished expected-economics inputs because the domain class already exists. | Users believe estimates affect allocation when they do not. | Capability gate is based on completed behavior, not class presence; expected economics remains hidden until `0012` T-007 through T-010 pass. |
| RISK-009 | Large or discrete models exceed a synchronous request window. | Timeouts and poor interaction. | Initial bounded sizes, explicit time limit, medium benchmark, visible timeout result; queue/worker architecture is a tracked follow-up. |
| RISK-010 | The existing generic `OPT` page and the new module are confused. | Users cannot tell simulated dashboard content from real engine runs. | Separate `IBAL` mnemonic/route, explicit source badges, no replacement or cross-link claiming shared run state. |
| RISK-011 | Synthetic settings accidentally generate impossible records. | Demo mode fails unpredictably or teaches invalid data conventions. | Construct dependent values in invariant-preserving order, validate every output with engine contracts, and property-test broad seed/config combinations. |
| RISK-012 | Infeasible or feasible-limit results are visually promoted to optimal. | Material model-risk misstatement. | Preserve status verbatim, use non-color labels, display verification, and test every status class end to end. |

## Approved Decisions & Remaining Production Gates

- Approved: the module mnemonic is `IBAL`, its route is `/inventory-optimizer`, and its navigation
  group is `OPTIMIZATION`. It remains separate from `OPT`.
- Approved: the initial InventoryBallast dependency is pinned to immutable commit
  `74737e53bf9821089c6aa2aeca5dffc4e67c81b7` with the `highs` extra.
- Approved: the first release supports single-period `securities_lending_inventory` solves only.
  Scenarios and multi-period workflows remain follow-ups even though InventoryBallast has lower-level
  support for them.
- Approved: `.xlsx` and exact JSON are the two input formats. CSV output is a ZIP of the engine's
  existing tabular projections; multi-file CSV input is deferred to avoid ambiguous partial uploads.
- Approved: the Python service is deployed separately from the Vite/Node process and is reachable
  only through QuantMeridian's server API proxy in normal use.
- Approved: uploaded and generated datasets are session-scoped and transient. A later persistence
  design requires a new data-retention and authorization spec.
- Approved scope: implementation may proceed locally and in protected staging. Production remains
  disabled until the following gates receive separate owner approval.
- Production gate: select the deployment that owns the Python service and document its CPU, memory,
  concurrency, rate-limit, and timeout budgets.
- Production gate: identify and verify the trusted user-access/authentication boundary that protects
  QuantMeridian's browser-facing proxy endpoints.

## Exceptions

None.

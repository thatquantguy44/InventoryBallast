# Tasks: Market Terminal Inventory Optimizer integration

- **Spec:** 0013-market-terminal-integration (`spec.md`, `plan.md`)
- **Last updated:** 2026-09-14

> Ordered, testable units of work for the separate QuantMeridian repository. Every task cites the
> requirement(s) it advances and carries a Definition of Done. InventoryBallast code changes are
> made only if a missing public integration primitive is proven and separately reviewed.

## Status Note

The owner approved local and protected-staging implementation on 2026-09-14 with the `IBAL`
mnemonic, separate Python service, InventoryBallast commit `74737e5`, XLSX/JSON input, session-only
data, and production disabled pending separate hosting/authentication approval. All tasks remain
`todo`; T-001 is ready to begin. The implementation branch must start from the latest QuantMeridian
`main`; unrelated changes in any existing checkout are not part of this work.

## Definition of Done (applies to every task)

- Code matches `spec.md` and `plan.md`; material deviations are approved and recorded before merge.
- Every production behavior traces to a requirement and every completed acceptance criterion has
  deterministic evidence named below.
- InventoryBallast remains the sole owner of optimization, domain validation, attribution,
  verification, and tabular result calculations.
- Random generation is seeded, versioned, timestamp-pinned, and free of hidden/global state.
- Uploads and result rows are not logged, persisted, committed, or placed in test snapshots.
- No secret, service token, confidential identifier, or real book data enters either repository.
- New Python dependencies and Node dev/runtime dependencies are pinned consistently with
  QuantMeridian conventions and included in clean-checkout tests.
- Typecheck, lint, unit, contract, build, and applicable end-to-end tests pass.
- Feature flags, health, observability, rollback, environment examples, and operating docs are
  updated with the code they describe.
- UI is verified with Playwright at the required desktop/tablet/mobile viewports, including
  keyboard flow, loading/error/empty states, browser console errors, and non-overlap.

## Task List

### Slice A - freeze the cross-repository contract

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-001 | At implementation start, record latest QuantMeridian `main`, pin owner-approved immutable InventoryBallast commit `74737e53bf9821089c6aa2aeca5dffc4e67c81b7` with the `highs` extra, and add a checked capability manifest plus package/version/startup compatibility test. | REQ-002, REQ-018, NFR-008 | todo | Approved 2026-09-14. Verify the exact installed SHA/version at startup; never pin a branch. |
| T-002 | Scaffold `services/inventory_optimizer_api` with FastAPI, strict API contracts, bearer auth, correlation/idempotency headers, metadata-only logging, `/health`, `/v1/capabilities`, redacted exception handling, and clean Docker/local entry points. | REQ-002, REQ-010, REQ-018, REQ-019, NFR-005, NFR-008, NFR-009 | todo | Health is unauthenticated but discloses no secret/config path; other endpoints require service auth. |

### Slice B - templates and data preparation

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-003 | Implement the shared V1 field registry and generate `starter-xlsx`, `advanced-xlsx`, and `request-json` downloads with README/data-dictionary content, exact units, examples, constraints, and schema version. | REQ-007, REQ-008, NFR-008 | todo | Parser and templates consume one registry. Starter artifacts must validate unchanged. |
| T-004 | Implement strict JSON/XLSX upload parsing, byte/row/content controls, duplicate-key and formula/macro/external-link rejection, row-level Pydantic construction, nested-record assembly, capability-scope checks, cross-record validation, and located issue aggregation. | REQ-008, REQ-009, REQ-010, NFR-004, NFR-005, NFR-006 | todo | Never infer units, recompute uploaded balances, ignore unknown data, or retain raw files. |
| T-005 | Implement `SyntheticConfig`, stable profile/scale registries, PCG64 generation in dependency order, deterministic IDs/timestamps, explicit resolved config disclosure, request summary/hash, property tests, and engine validation of every generated request. | REQ-003, REQ-004, REQ-005, REQ-006, REQ-010, NFR-001, NFR-003 | todo | `Reroll` means a visible seed change. Default profiles target structurally valid, feasible books. |

### Slice C - validation, solve, and exports

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-006 | Implement the strict `RunConfig` allowlist, formulation/conflict precheck, canonical hash verification, solve-time revalidation, `PlatformInvocationContext`, pinned facade invocation, and exact status/error mapping. | REQ-002, REQ-011, REQ-012, REQ-013, NFR-002, NFR-004, NFR-006 | todo | Infeasible and feasible-limit are result statuses, not HTTP transport failures and never `optimal`. |
| T-007 | Implement transient normalized-input, raw-result, validation-report, and engine-owned result-table CSV ZIP exports with round-trip and byte/content parity tests. | REQ-016, NFR-002, NFR-005, NFR-008 | todo | CSVs must come from `reporting.tables.result_tables()`, not a service/frontend copy. |

### Slice D - QuantMeridian proxy and module shell

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-008 | Add generated TypeScript API types, one server-only proxy helper, and the `/api/inventory-optimizer/*` handlers with feature/auth gates, body/time/concurrency limits, correlation headers, abort behavior, and unchanged response/status pass-through. | REQ-008, REQ-012, REQ-013, REQ-018, REQ-020, NFR-004, NFR-005, NFR-006, NFR-008, NFR-009 | todo | Browser never receives the service URL/token. Altered client state cannot submit a disabled capability. |
| T-009 | Register feature-flagged `IBAL` in module config, navigation, React routing, badge coverage, README module catalogue, and screenshot route inventory; add a separate page shell using existing terminal components and prove `OPT` is unchanged. | REQ-001, REQ-020, NFR-007 | todo | No behavior or data changes in `src/app/optimization/page.tsx`. |

### Slice E - interactive workflow

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-010 | Build the reducer/state machine, explicit Synthetic/Upload segmented control, bounded synthetic controls/presets/reroll, upload and template actions, run-config controls, normalized summary/record preview, located issue grid, dirty confirmation, readiness gates, and reset flow. | REQ-003, REQ-005, REQ-006, REQ-007, REQ-009, REQ-010, REQ-011, REQ-012, REQ-017, REQ-018, NFR-006, NFR-007 | todo | Abort stale requests and require confirmation before replacing prepared unsaved data. No automatic source switch. |
| T-011 | Build result overview and Allocations/Balances/Demand/Economics/Constraints/Diagnostics/Raw tabs from `OptimizationResult`, including sorting/filtering, evidence drill-down, source/version/status badges, loading/empty/error states, and field-lineage presentation tests. | REQ-013, REQ-014, REQ-015, NFR-002, NFR-006, NFR-007 | todo | Never invent recommended trades or promote non-optimal statuses. Raw result remains inspectable. |
| T-012 | Wire session-only completed-run state, rerun/reset behavior, replacement confirmation, and all four downloads; prove page reload clears private data and no server retrieval endpoint exists. | REQ-016, REQ-017, NFR-005 | todo | Do not use localStorage, IndexedDB, a database, or committed fixtures for user data/results. |

### Slice F - operate and verify

| ID | Task | Covers | Status | Notes |
| --- | --- | --- | --- | --- |
| T-013 | Add Inventory Optimizer health to Data Ops, structured metadata-only timing/error metrics, owner/threshold documentation, verification-failure escalation, and log-redaction tests across browser proxy and Python service. | REQ-019, NFR-005, NFR-009 | todo | Log validation codes/counts, not messages that may embed IDs. |
| T-014 | Add `.env.example`, local runbook, service Docker/deploy configuration, protected-staging checklist, production-off defaults, resource/rate controls, kill switch, rollback steps, retention statement, and engine-upgrade procedure. | REQ-020, NFR-004, NFR-005, NFR-008, NFR-009 | todo | Production enablement requires explicit owner approval and a trusted access boundary. |
| T-015 | Run and retain complete evidence: Python tests, TypeScript tests/typecheck/build, architecture/contract parity, status matrix, security/redaction, limits, performance methodology, real browser-to-solver flows, downloads, service-outage behavior, and Playwright desktop/tablet/mobile/keyboard screenshots. | REQ-001, REQ-002, REQ-003, REQ-006, REQ-008, REQ-009, REQ-012, REQ-013, REQ-014, REQ-015, REQ-018, REQ-019, REQ-020, NFR-001, NFR-002, NFR-003, NFR-004, NFR-005, NFR-006, NFR-007, NFR-008, NFR-009 | todo | Final handoff records exact commits/images, versions, fixture hashes, commands, pass counts, benchmark runtime profile, screenshots, known limits, and open follow-ups. |

Status values: `todo` | `in-progress` | `blocked` | `done`.

## Test Coverage Map

| Acceptance criterion | Test(s) | Status |
| --- | --- | --- |
| AC-001 | `src/tests/inventory-optimizer.e2e.spec.ts::IBAL route is independently gated and OPT is unchanged`; nav/module unit assertions | todo |
| AC-002 | `services/inventory_optimizer_api/tests/test_contract_parity.py::test_service_and_direct_facade_match_deterministic_fields` | todo |
| AC-003 | reducer no-fallback test; `inventory-optimizer.e2e.spec.ts::invalid upload never switches to synthetic or solves` | todo |
| AC-004 | `test_synthetic.py::test_same_complete_config_is_byte_identical`; `::test_seed_change_changes_observations_not_schema` | todo |
| AC-005 | parameterized profile/boundary tests in `test_synthetic.py`; component control-to-preview test | todo |
| AC-006 | Hypothesis/property test `test_generated_requests_pass_domain_and_reconciliation_validation` across at least 100 examples | todo |
| AC-007 | `test_templates_are_registry_complete`; `test_starter_xlsx_and_json_validate_unchanged`; template download E2E | todo |
| AC-008 | `test_equivalent_xlsx_and_json_hash_match`; parser rejection matrix for type/size/formula/column/version | todo |
| AC-009 | `test_upload_aggregates_located_independent_errors_without_repair_or_row_drop`; issue-grid component assertion | todo |
| AC-010 | `test_dataset_envelope_summary_matches_normalized_request`; preview-to-run payload E2E assertion | todo |
| AC-011 | `test_run_config_allowlist_maps_one_to_one`; unknown-setting and MIP/QP conflict tests | todo |
| AC-012 | `test_run_revalidates_after_prepare`; proxy/UI solve-readiness tests | todo |
| AC-013 | service and UI parameterized status/error matrix covering optimal, feasible-limit, infeasible, timeout, numerical, internal | todo |
| AC-014 | result-field lineage component tests; `test_economics_components_reconcile_to_total`; golden result E2E | todo |
| AC-015 | allocations evidence and binding-constraint inspection component/E2E tests; unsupported trade-field absence assertion | todo |
| AC-016 | `test_all_exports_round_trip_and_tables_match_engine`; browser download content E2E | todo |
| AC-017 | reducer dirty-confirmation/session-reset tests; page-reload/no-retrieval E2E | todo |
| AC-018 | capability omission component test; service disabled-feature rejection; altered-client-state E2E | todo |
| AC-019 | health response/service mock matrix; Data Ops presentation test; outage E2E | todo |
| AC-020 | module-disabled build/runtime tests; unauthenticated proxy test; kill-switch smoke test | todo |
| AC-021 | generation/parsing/solve benchmark suite with retained p50/p95/max artifact and runtime manifest | todo |
| AC-022 | `test_security.py::test_confidential_sentinels_absent_from_service_logs`; proxy log-capture equivalent | todo |
| AC-023 | Playwright keyboard and screenshot suite at 375x812, 768x1024, 1440x900 with overflow/overlap/console assertions | todo |
| AC-024 | clean-checkout CI job running service tests, generated-contract diff, TypeScript tests/typecheck/build, and real local end-to-end solve | todo |

## Follow-ups

Tracked work intentionally deferred:

- Complete InventoryBallast `0012` T-007 through T-010, then explicitly advertise and design
  expected-economics shadow/direct controls and disclosure in a new integration slice.
- Dynamic buffers after `0012` T-011 and reporting support are implemented.
- Multi-period projection/joint solve UI and known-future-event workbook tabs.
- Scenario builder, rate/demand shocks, trade events, comparisons, and stress reports.
- Fee-tier authoring with a normalized child sheet and MIP-specific UX.
- CSV-bundle input if users demonstrate a need that justifies multi-file transaction semantics.
- Governed production feed adapters and point-in-time lineage from approved systems.
- Encrypted, tenant-scoped dataset/result persistence with retention/deletion policy and RBAC.
- Asynchronous queue/workers, cancellation, progress, and larger model capacity.
- Cross-module links from `SLAB` or `OPT` after semantics and run identity are agreed; no link should
  imply shared data before then.

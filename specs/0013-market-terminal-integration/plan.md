# Plan: Market Terminal Inventory Optimizer integration

- **Spec:** 0013-market-terminal-integration (`spec.md`)
- **Status:** Approved for local and protected-staging implementation; production separately gated
- **Author:** Joshua Lutkemuller, CFA
- **Last updated:** 2026-09-14

> HOW. This document is written for the engineer implementing the feature in the separate
> QuantMeridian repository. InventoryBallast remains the model source of truth.

## Approach

Build a distinct `IBAL` workspace in QuantMeridian and place a narrow Python API between the
terminal and InventoryBallast. The browser talks only to QuantMeridian's existing Web-standard
`/api/*` route layer. Those handlers proxy to the Python API using a server-held credential. The
Python service owns upload parsing, deterministic synthetic generation, conversion into the exact
Pydantic contracts, validation, facade invocation, and engine-owned exports.

This deployment boundary is intentional. InventoryBallast depends on Python, NumPy/SciPy, and the
native HiGHS backend. Rebuilding those calculations in TypeScript would create a second optimizer;
spawning a local CLI from Vercel handlers would be deployment-specific and unsafe; bundling native
solver dependencies into the Vite client is impossible. A small FastAPI companion follows
QuantMeridian's existing Python-service pattern while keeping browser/API contracts explicit.

The initial workflow is synchronous and bounded:

```text
Choose SYNTHETIC or UPLOAD
        |
        v
Generate or parse -> normalize -> validate -> preview
        |                                  |
        | invalid                          | valid
        v                                  v
Located issues; stop                 Run configuration
                                            |
                                            v
                                      revalidate -> solve
                                            |
                                            v
                          result tabs + provenance + downloads
```

Source mode is state, not fallback order. A source change clears the prepared request after user
confirmation. Every generate/upload action creates a `DatasetEnvelope`; every solve consumes that
exact normalized request and source disclosure. The service validates again at solve time so stale
or hand-edited browser state cannot bypass controls.

## Baseline And Ownership

### InventoryBallast baseline

- Assessed commit: `74737e53bf9821089c6aa2aeca5dffc4e67c81b7`.
- Package: `inventory-optimizer==0.1.0`; Python `>=3.11`.
- Runtime extra: `inventory-optimizer[highs]`.
- Public invocation: `InventoryOptimizer(config=load_config(overrides=...)).optimize(request,
  platform=context)`.
- Input: `domain.requests.OptimizationRequest`.
- Output: `domain.results.OptimizationResult`.
- Validation: construct Pydantic records, then call `validation.validate_request`; solve repeats
  validation through the facade.
- Flat output: `reporting.tables.result_tables` and `adapters.csv_io`.
- Core limitation: `SecurityInventory.currency` must equal `USD`.
- Integration scope excludes non-empty `planning_periods`, `known_future_events`, and
  `expected_economics` until their complete behaviors are advertised by capabilities.

The owner approved immutable commit `74737e53bf9821089c6aa2aeca5dffc4e67c81b7` for the initial
integration on 2026-09-14. T-001 verifies and records that exact pin. Never depend on `main`, this
feature branch, or another mutable branch.

### QuantMeridian baseline

- Repository: `https://github.com/joshualutkemuller/QuantMeridian.git`.
- Assessed `origin/main`: `ec274543346d82c56c149168dd31f4371111df21`.
- Frontend: Vite 5, React 18, React Router 6, Tailwind, Lucide.
- API: Web-standard `Request -> Response` route modules discovered from
  `src/app/api/**/route.ts` by `src/server/registry.ts`.
- Module registration: `src/lib/nav.ts`, `src/App.tsx`, and
  `settings/modules.config.json`.
- Provenance: `src/lib/provenance.ts` and `ProvenanceBadge`.
- Existing `OPT` page: `src/app/optimization/page.tsx`; this integration does not edit its behavior
  or data contracts.

Implementation starts from latest QuantMeridian `main` at that future time. The assessed checkout
had unrelated work on `phase4/markets-charting`; none of it is an integration prerequisite and it
must not be stashed, overwritten, or folded into this work.

## Architecture & Components

```text
QuantMeridian browser
  src/app/inventory-optimizer/page.tsx
  src/features/inventory-optimizer/*
    - source/config state machine
    - synthetic controls or upload drop zone
    - normalized preview and validation issues
    - result tabs and downloads
          |
          | same-origin /api/inventory-optimizer/*
          v
QuantMeridian Node/Vercel route layer
  src/app/api/inventory-optimizer/**/route.ts
  src/lib/server/inventoryOptimizerProxy.ts
    - feature/auth gate
    - body/timeout limits
    - correlation headers
    - forwards without logging payloads
          |
          | Bearer INVENTORY_OPTIMIZER_API_TOKEN
          v
QuantMeridian Python companion service
  services/inventory_optimizer_api/
    - FastAPI versioned endpoints
    - workbook/template adapter
    - deterministic synthetic generator
    - DatasetEnvelope and located issues
    - config allowlist and platform context
    - health, capabilities, metadata-only telemetry
          |
          | pinned Python package dependency
          v
InventoryBallast
  OptimizationRequest -> validate_request
  load_config -> InventoryOptimizer.optimize
  OptimizationResult -> result_tables
```

### Target file layout in QuantMeridian

```text
services/inventory_optimizer_api/
  pyproject.toml
  Dockerfile
  README.md
  src/inventory_optimizer_api/
    __init__.py
    app.py                    # FastAPI assembly and exception mapping
    auth.py                   # constant-time bearer check
    capabilities.py           # one compatibility source of truth
    contracts.py              # API-only envelopes/configs/issues
    config_adapter.py         # strict UI setting allowlist -> engine overrides
    engine_service.py         # validate/solve/export orchestration
    synthetic.py              # deterministic generator
    upload.py                 # JSON/XLSX parsing and located validation
    templates.py              # workbook/JSON artifact generation
    telemetry.py              # metadata-only logging helpers
  tests/
    fixtures/
    test_api.py
    test_contract_parity.py
    test_synthetic.py
    test_upload.py
    test_security.py

src/app/inventory-optimizer/page.tsx
src/features/inventory-optimizer/
  api.ts
  types.ts                   # generated from service OpenAPI, no domain math
  state.ts
  SourceToolbar.tsx
  SyntheticControls.tsx
  UploadWorkspace.tsx
  DatasetPreview.tsx
  ValidationIssues.tsx
  RunControls.tsx
  ResultsWorkspace.tsx
  ResultsOverview.tsx
  AllocationsGrid.tsx
  BalancesGrid.tsx
  DemandGrid.tsx
  EconomicsGrid.tsx
  ConstraintsGrid.tsx
  DiagnosticsPanel.tsx
  downloads.ts
  *.test.ts(x)
src/lib/server/inventoryOptimizerProxy.ts
src/app/api/inventory-optimizer/health/route.ts
src/app/api/inventory-optimizer/capabilities/route.ts
src/app/api/inventory-optimizer/templates/[kind]/route.ts
src/app/api/inventory-optimizer/datasets/synthetic/route.ts
src/app/api/inventory-optimizer/datasets/upload/route.ts
src/app/api/inventory-optimizer/validate/route.ts
src/app/api/inventory-optimizer/runs/route.ts
src/app/api/inventory-optimizer/exports/result-tables/route.ts
src/tests/inventory-optimizer.e2e.spec.ts
```

Do not create a generic platform SDK in this slice. The one shared proxy helper and one feature
folder are enough. Do not place generated portfolios in `src/data/`; that directory's committed
fixtures would make transient/user data look like product data.

## Interfaces & Data Contracts

### Versioning and compatibility

The service API prefix is `/v1`. Three versions are independent and always returned:

- `api_schema_version`: semantic version of API envelopes, initially `1.0.0`.
- `template_schema_version`: workbook/JSON template major/minor, initially `1.0`.
- `generator_version`: algorithm version, initially `synthetic-v1`.

The engine contributes `engine_package_version`, `engine_commit`, and `backend_version`. Startup
fails readiness if the installed commit/version does not match the build-time capability manifest.
QuantMeridian generates TypeScript types from the service OpenAPI document in CI and fails on an
uncommitted diff. A capability's availability is declared explicitly; class/module presence is not
evidence that behavior is complete.

### Service authentication and request identity

Every `/v1` endpoint except `/health` requires:

```http
Authorization: Bearer <INVENTORY_OPTIMIZER_API_TOKEN>
X-Correlation-ID: <uuid>
```

Run creation also requires `Idempotency-Key`. The browser sends same-origin requests and never sees
the service token. QuantMeridian's server proxy supplies the token, forwards/generated correlation
and idempotency identifiers, enforces request size and timeout, and returns the service response
without rewriting domain status. Logs include only correlation ID, endpoint, source mode, row
counts, engine version, response category, and elapsed time.

The token does not authenticate the browser user. Therefore production remains off unless the
QuantMeridian deployment itself is access-controlled or a future platform auth layer supplies a
trusted `authorization_reference`.

### Capability endpoint

`GET /v1/capabilities` returns the single contract the UI uses to enable controls:

```json
{
  "api_schema_version": "1.0.0",
  "template_schema_version": "1.0",
  "generator_version": "synthetic-v1",
  "engine_package_version": "0.1.0",
  "engine_commit": "<approved immutable sha>",
  "backend": {"name": "highs", "version": "<runtime version>", "ready": true},
  "problem_families": ["securities_lending_inventory"],
  "formulations": ["lp", "mip", "qp"],
  "input_features": {
    "entity_scoped_limits": true,
    "all_or_none_routes": true,
    "minimum_active_quantity": true,
    "lot_sizes": true,
    "maximum_active_routes": true,
    "allocation_stability_penalty": true,
    "fee_tier_authoring": false,
    "expected_economics": false,
    "dynamic_buffers": false,
    "multi_period": false,
    "scenarios": false
  },
  "output_sections": [
    "allocations", "balances", "economics", "demand", "pricing", "constraints",
    "solver", "verification", "warnings"
  ],
  "upload_formats": ["xlsx", "json"],
  "limits": {
    "upload_bytes": 10485760,
    "inventory_rows": 500,
    "route_rows": 10000,
    "demand_rows": 5000,
    "optional_rows": 5000,
    "solve_timeout_seconds": 30
  }
}
```

The initial service rejects disabled features even if a hand-crafted request includes them. An
engine update changes capabilities only after its behavior and parity tests land.

### Located issue contract

All preparation failures share one shape:

```json
{
  "severity": "error",
  "stage": "file|parse|schema|reconciliation|configuration|service",
  "code": "STABLE_MACHINE_CODE",
  "message": "Human-readable action",
  "location": "inventory[2].available_to_lend_shares",
  "sheet": "inventory",
  "row": 4,
  "column": "available_to_lend_shares"
}
```

`sheet`, `row`, and `column` are null for JSON/global issues. Pydantic field errors are translated
from `.errors()`; InventoryBallast `ValidationIssue` codes/messages/locations are preserved. The
adapter adds only file/template/configuration codes. Return all detectable issues, capped at 500;
when capped, append `ISSUE_LIMIT_REACHED` with the omitted count.

### Dataset envelope

Both data-source endpoints and `/v1/validate` return the same envelope:

```json
{
  "api_schema_version": "1.0.0",
  "template_schema_version": "1.0",
  "source": {
    "mode": "synthetic|upload",
    "label": "SYNTHETIC|UPLOAD",
    "generator_version": "synthetic-v1",
    "seed": 1729,
    "file_name": null,
    "file_sha256": null
  },
  "request": {"request_id": "...", "inventory": [], "routes": [], "demand": []},
  "request_sha256": "<canonical hash>",
  "summary": {
    "inventory_rows": 0,
    "route_rows": 0,
    "demand_rows": 0,
    "borrowers": 0,
    "securities": 0,
    "total_lendable_shares": 0.0,
    "current_on_loan_shares": 0.0,
    "available_to_lend_shares": 0.0,
    "starting_utilization": 0.0,
    "total_reference_demand_shares": 0.0
  },
  "valid": true,
  "issues": []
}
```

Fields irrelevant to a source mode are null, never fabricated. The canonical request hash uses
InventoryBallast's canonical JSON behavior, exposed through a public integration helper or a tiny
adapter that calls the same `config.hashing.canonical_json`; it must not invent a different
canonicalization rule. `request` and `request_sha256` are nullable fields: they are null, not
omitted, when parsing errors prevent construction of a safe normalized request.

### Synthetic configuration

`POST /v1/datasets/synthetic` accepts this bounded API-only contract:

| Field | Type / values | Default | Purpose |
| --- | --- | --- | --- |
| `template_schema_version` | literal `1.0` | required | Prevent incompatible generation. |
| `generator_version` | literal `synthetic-v1` | required | Pins algorithm semantics. |
| `seed` | integer, `0..2^32-1` | required | Reproduction and reroll control. |
| `as_of` | timezone-aware ISO datetime | required | Fixed request and record knowledge time. |
| `effective_date` | ISO date | required | Solve date; never inferred from server clock. |
| `profile` | `balanced`, `scarce_inventory`, `demand_heavy`, `specials_concentrated`, `counterparty_concentrated`, `operational_friction`, `custom` | `balanced` | Coherent starting shape. |
| `scale` | `demo`, `small`, `medium`, `custom` | `demo` | Population preset. |
| `security_count` | `1..500` | from scale | Distinct securities/inventory records. |
| `inventory_pool_count` | `1..20` | from scale | Pools assigned across inventory. |
| `borrower_count` | `1..100` | from scale | Borrowers in route/demand graph. |
| `parent_group_count` | `1..borrower_count` | from scale | Legal/ultimate-parent concentration. |
| `routes_per_security_min/max` | `1..borrower_count`, ordered | from scale | Connectivity without a vague density value. |
| `quantity_distribution` | `uniform`, `lognormal` | `lognormal` | Lendable supply shape. |
| `lendable_shares_min/max` | finite positive numbers, ordered | `10000/1000000` | Supply range. |
| `variation_coefficient` | `0..1` | `0.25` | Dispersion around profile anchors. |
| `starting_utilization_min/max` | `0..1`, ordered | `0.25/0.70` | Current on-loan range. |
| `demand_to_supply_min/max` | finite `0..5`, ordered | `0.5/1.5` | Demand pressure. |
| `borrower_concentration` | `even`, `moderate`, `zipf` | `moderate` | Demand/route concentration. |
| `fee_regime` | `easy_to_borrow`, `mixed`, `specials`, `barbell` | `mixed` | Fee distribution family. |
| `fee_rate_bps_min/max` | finite `0..100000`, ordered | profile | Display units; generator converts once to decimal. |
| `specials_share` | `0..1` | profile | Mixture weight for special names. |
| `elasticity_min/max` | finite `0..20`, ordered | `0/2` | Demand response range. |
| `eligible_route_fraction` | `0..1` | `0.95` | Ineligible-route share. |
| `existing_route_fraction` | `0..1` | `0.40` | Routes with positive current quantity. |
| `reserve_fraction_min/max` | `0..1`, ordered | `0.02/0.10` | Inventory reserve policy. |
| `counterparty_limit_fraction` | `0..1` | profile | Borrowers/parents receiving limits. |
| `hard_limit_fraction` | `0..1` | `1.0` | Hard versus soft entity mappings. |
| `limit_tightness_min/max` | finite `0..2`, ordered | `0.7/1.2` | Cap relative to generated reference demand. |
| `entity_limit_scope` | `borrower`, `legal_entity`, `ultimate_parent`, `mixed` | `mixed` | Limit aggregation scope. |
| `all_or_none_route_fraction` | `0..1` | `0` | Supported MIP trigger. |
| `minimum_ticket_route_fraction` | `0..1` | `0` | Supported minimum-active trigger. |
| `lot_size_route_fraction` | `0..1` | `0` | Supported lot-size trigger. |
| `maximum_active_routes_per_security` | null or integer `1..100` | null | Supported cardinality trigger. |

Scale defaults are stable contract data, not UI-only constants:

| Scale | Securities | Pools | Borrowers | Parent groups | Routes/security |
| --- | ---: | ---: | ---: | ---: | --- |
| `demo` | 8 | 2 | 4 | 2 | 2..4 |
| `small` | 25 | 3 | 8 | 4 | 3..8 |
| `medium` | 100 | 5 | 25 | 10 | 5..20 |

Profiles set visible initial values in the form. Once the user edits one, the profile becomes
`custom`; there are no hidden profile adjustments after submission. `Reroll` changes only the seed
to a newly generated displayed integer. Date/time and all other controls stay fixed.

### Synthetic generation algorithm and invariants

Use `numpy.random.Generator(numpy.random.PCG64(seed))`. Do not use module-global random state,
Python hash ordering, current time, or UUIDs. IDs are deterministic, zero-padded strings such as
`SYN-SEC-0001`, `SYN-INV-0001`, `SYN-BOR-001`, `SYN-DMD-000001`, and `SYN-ROUTE-000001`.

Generate in dependency order:

1. Resolve profile defaults into one fully explicit config and serialize it in the response.
2. Create securities, pools, borrowers, legal entities, and ultimate parents.
3. Create a deterministic route graph with at least one route per security and no duplicate route
   ID or borrower/security/demand tuple.
4. Generate total lendable supply, then allocate current on-loan quantity only across eligible
   existing routes. Set each inventory's `on_loan_shares` to the exact route sum.
5. Generate reserved and committed-out shares within remaining supply, then derive
   `available_to_lend_shares` exactly from the balance identity.
6. Create one demand group per supported borrower/security pricing combination. Route
   `security_id`, `borrower_id`, `demand_group_id`, and `fee_rate` must agree with the demand row.
7. Create utilization policies and optional route MIP features within their validated bounds.
8. Create point-in-time entity relationships before entity-scoped limits. Every scoped hard limit
   must have a unique, confidence-satisfying mapping as of `as_of`.
9. Construct the full `OptimizationRequest`, run engine validation, and return issues instead of a
   request if an internal generator defect is detected.

Generation guarantees structural validity, not a particular optimal allocation. The initial
profiles target feasible books. A future intentional-infeasibility lab must be separately named
and must not weaken this generator's guarantees.

### Downloadable input templates

`GET /v1/templates/{kind}` supports:

| Kind | File | Content |
| --- | --- | --- |
| `starter-xlsx` | `inventory_optimizer_starter_v1.xlsx` | Small, valid, obviously fictitious example with required and common optional sheets. |
| `advanced-xlsx` | `inventory_optimizer_upload_v1.xlsx` | Header-only supported sheets plus `README` and full `data_dictionary`. |
| `request-json` | `inventory_optimizer_request_v1.json` | Exact, valid `OptimizationRequest` matching starter workbook semantics. |

Templates are generated from the same field registry the parser uses. CI regenerates them and
checks byte-normalized workbook structure/JSON for drift. The workbook uses plain cells only: no
macros, formulas, links, merged data cells, hidden required columns, or locale-specific formats.

Workbook conventions:

- Sheet names and headers are exact lowercase ASCII.
- `README` and `data_dictionary` are informational; all other non-empty sheets are data.
- Timestamps are ISO 8601 with timezone, e.g. `2026-09-14T14:30:00Z`.
- Dates are ISO `YYYY-MM-DD`.
- Rates and fractions are decimal values unless the field name explicitly says `_bps`.
  `fee_rate=0.0125` means 125 bps. The parser never guesses that `1.25` means 1.25%.
- Booleans are literal `true`/`false` or native workbook booleans; `Y`, `N`, `1`, and `0` are
  rejected.
- Blank optional cells become null/default as documented. Blank required cells are errors.
- IDs are strings and are never numeric-coerced, trimmed internally, or case-normalized.
- Unknown columns and non-empty unknown sheets are errors. Completely blank trailing rows are
  ignored; partially populated rows are validated and never dropped.
- Formula cells are rejected even when a cached value exists. `.xls`, `.xlsm`, and password-
  protected files are unsupported.

### Workbook sheet catalogue

The following is the authoritative V1 template map. `R` means required column, `O` optional. A
sheet marked optional may be absent or header-only.

#### `run` (required, exactly one data row)

| Field | R/O | Type / rule | Meaning |
| --- | --- | --- | --- |
| `template_schema_version` | R | literal `1.0` | Workbook contract version. |
| `request_id` | R | non-empty string | User/run request identifier. |
| `as_of` | R | aware datetime | Knowledge time for the request. |
| `effective_date` | R | date | Optimization effective date. |
| `problem_family` | R | `securities_lending_inventory` | Only initial supported family. |
| `legal_entity_id` | O | string | `DeskContext.legal_entity_id`. |
| `platform_tenant_id` | O | string | Opaque tenant identifier. |
| `attribution_scope` | O | string | Opaque reporting scope. |

#### `inventory` (required, one or more rows)

| Field | R/O | Type / rule |
| --- | --- | --- |
| `inventory_id` | R | unique string |
| `inventory_pool_id` | R | string |
| `security_id` | R | string |
| `as_of` | R | aware datetime |
| `settlement_date` | R | date |
| `total_lendable_shares` | R | finite number >= 0 |
| `on_loan_shares` | R | finite number >= 0; equals route-current sum |
| `reserved_shares` | R | finite number >= 0 |
| `committed_out_shares` | R | finite number >= 0 |
| `available_to_lend_shares` | R | exact balance identity within engine tolerance |
| `price_usd` | R | finite number > 0 |
| `currency` | R | literal `USD` |
| `eligible` | R | boolean |
| `source_version` | R | non-empty lineage string |

#### `routes` (required, one or more rows)

| Field | R/O | Type / rule |
| --- | --- | --- |
| `route_id` | R | unique string |
| `inventory_id` | R | foreign key to `inventory` |
| `security_id` | R | must equal referenced inventory security |
| `borrower_id` | R | string |
| `demand_group_id` | R | foreign key to `demand` |
| `current_quantity_shares` | R | finite number >= 0 |
| `hard_minimum_quantity_shares` | O | finite number >= 0; default 0 |
| `minimum_active_quantity_shares` | O | finite number >= 0 |
| `maximum_quantity_shares` | R | finite number >= all route minima/current |
| `fee_rate` | R | finite decimal annual rate |
| `revenue_share` | R | finite fraction 0..1 |
| `reinvestment_rate` | O | finite decimal annual rate |
| `collateral_factor` | O | finite number >= 0 |
| `variable_cost_rate` | R | finite decimal annual rate >= 0 |
| `increase_cost_usd_per_share` | R | finite number >= 0 |
| `decrease_cost_usd_per_share` | R | finite number >= 0 |
| `recall_notice_days` | R | integer >= 0 |
| `term_end_date` | O | date |
| `eligible` | R | boolean |
| `all_or_none` | O | boolean; default false |
| `lot_size_shares` | O | finite number > 0 |
| `priority_class` | O | string |

#### `demand` (required, one or more rows)

| Field | R/O | Type / rule |
| --- | --- | --- |
| `demand_group_id` | R | unique string |
| `security_id` | R | agrees with every route in group |
| `borrower_id` | R | agrees with every route in group |
| `as_of` | R | aware datetime |
| `reference_quantity_shares` | R | finite number >= 0 |
| `reference_fee_rate` | R | finite decimal annual rate >= 0; > 0 if elasticity > 0 |
| `elasticity` | R | finite number >= 0 |
| `forecast_std_shares` | O | finite number >= 0 |
| `hard_max_quantity_shares` | O | finite number >= 0 |
| `source_model` | R | non-empty lineage string |
| `source_version` | R | non-empty lineage string |

The V1 UI does not author `candidate_fee_rates`. The exact JSON endpoint rejects a non-empty value
while capability `fee_tier_authoring` is false. A future workbook extension uses a normalized
`demand_fee_tiers(demand_group_id, tier_index, fee_rate)` sheet rather than a delimiter-packed cell.

#### `counterparty_limits` (optional)

| Field | R/O | Type / rule |
| --- | --- | --- |
| `limit_id` | R | unique string |
| `borrower_id` | R | string; required by current engine contract |
| `legal_entity_id` | O | string; mutually exclusive with ultimate parent in V1 adapter |
| `ultimate_parent_id` | O | string; mutually exclusive with legal entity in V1 adapter |
| `effective_from` | R | aware datetime |
| `effective_to` | O | aware datetime >= effective_from |
| `security_id` | O | string scope |
| `inventory_pool_id` | O | string scope |
| `maximum_notional_usd` | O | finite number >= 0; one cap required |
| `maximum_quantity_shares` | O | finite number >= 0; one cap required |
| `hard` | O | boolean; default true |
| `risk_class` | O | string |
| `source` | R | non-empty lineage string |
| `source_version` | R | non-empty lineage string |

#### `utilization_policies` (optional)

| Field | R/O | Type / rule |
| --- | --- | --- |
| `policy_id` | R | unique string |
| `inventory_pool_id` | O | string scope |
| `security_id` | O | string scope |
| `effective_from` | R | aware datetime |
| `effective_to` | O | aware datetime >= effective_from |
| `minimum_utilization` | O | fraction 0..1 |
| `target_utilization` | O | fraction 0..1 |
| `maximum_utilization` | O | fraction 0..1; ordered with min/target |
| `reserve_buffer_shares` | O | finite number >= 0; default 0 |
| `reserve_buffer_fraction` | O | fraction 0..1; default 0 |
| `target_hard` | O | boolean; default false |
| `target_penalty_usd_per_share` | O | finite number >= 0; required for soft target |
| `target_priority` | O | integer |
| `maximum_active_routes` | O | integer >= 0; MIP trigger |
| `source` | R | non-empty lineage string |
| `source_version` | R | non-empty lineage string |

#### `entity_relationships` (optional)

This sheet flattens `PointInTimeValue[EntityRelationship]` and is required when a hard limit uses a
legal-entity or ultimate-parent scope.

| Field | R/O | Type / rule |
| --- | --- | --- |
| `entity_id` | R | borrower/entity string |
| `legal_entity_id` | R | string |
| `ultimate_parent_id` | R | string |
| `relationship_type` | R | non-empty string |
| `ownership_confidence` | R | finite fraction 0..1 |
| `observed_at` | R | aware datetime <= request as_of to be usable |
| `effective_from` | R | aware datetime |
| `effective_to` | O | aware datetime > effective_from |
| `source` | R | non-empty lineage string |
| `source_version` | R | non-empty lineage string |
| `field_mapping_version` | R | non-empty mapping version |
| `quality` | R | `verified`, `estimated`, `stale`, or `conflicting` |

#### `metadata` (optional)

| Field | R/O | Type / rule |
| --- | --- | --- |
| `key` | R | unique non-empty string |
| `value` | R | string |

No workbook sheet accepts `config_overrides`; run configuration comes from the allowlisted UI/API
contract. This prevents an uploaded file from changing solver or validation policy invisibly.

### Upload parser pipeline

1. Reject by `Content-Length` where available, then enforce the same limit while reading.
2. Sniff content and extension; do not trust MIME alone.
3. For JSON, parse one object and reject duplicate keys before Pydantic validation.
4. For XLSX, use `openpyxl` in read-only/data-only-disabled mode, reject macros/formulas/external
   links, and enforce sheet/row/column limits before collecting values.
5. Validate each row independently to aggregate located field errors.
6. Reconstruct nested `DeskContext` and `PointInTimeValue[EntityRelationship]` records.
7. Construct `OptimizationRequest`, enforce the initial capability scope, then call
   `validate_request` using the chosen staleness threshold.
8. Return an envelope whether valid or invalid. Invalid responses omit `request` only when a safe
   normalized request cannot be constructed; parsed preview counts remain available where safe.

Uploaded `available_to_lend_shares` is never recomputed. The parser reports a reconciliation error
and lets the user correct the source. This differs deliberately from synthetic mode, where the
generator owns every dependent value and derives the balance exactly.

### Run configuration adapter

The browser sends an API-owned `RunConfig` with these optional keys only:

```json
{
  "planning_horizon_days": 1,
  "day_count_basis": "act_360",
  "solver_time_limit_seconds": 30,
  "solver_relative_gap": 0.0,
  "solver_threads": 1,
  "solver_seed": 1729,
  "max_staleness_hours": 24,
  "minimum_entity_confidence": 0.8,
  "allocation_stability_penalty": 0.0
}
```

`config_adapter.py` maps each key to a known `load_config(overrides=...)` path. Unknown keys are
forbidden. `solver_threads` defaults to 1 for reproducibility and service capacity. The adapter
detects route/policy MIP triggers and positive QP penalty before solve; the existing engine remains
the final authority on unsupported conflicts.

The UI displays the detected formulation from capabilities and prepared input. It does not let the
user force a label. Expected-economics mode and arbitrary component lists are absent.

### Validate and run endpoints

```text
POST /v1/datasets/synthetic    SyntheticConfig -> DatasetEnvelope
POST /v1/datasets/upload       multipart file  -> DatasetEnvelope
POST /v1/validate              {source, request, run_config} -> DatasetEnvelope + config issues
POST /v1/runs                  RunRequest -> RunResponse
POST /v1/exports/result-tables OptimizationResult -> application/zip
```

`RunRequest` contains `api_schema_version`, the exact `DatasetSource`, normalized
`OptimizationRequest`, `request_sha256`, `RunConfig`, and browser-generated idempotency key. The
service recomputes the hash and rejects a mismatch. It builds `PlatformInvocationContext` with:

- `request_id`: engine request ID.
- `correlation_id`: proxy header.
- `idempotency_key`: request header/body, equal by validation.
- `problem_family` and `as_of`: copied from the request.
- `authorization_reference`: opaque trusted-edge marker, never a user email/token.
- `schema_version`: API schema version.
- `platform_tenant_id`: copied from desk context when present.
- `actor_reference`: optional opaque reference only when the trusted platform supplies one.

`RunResponse` contains source disclosure, resolved explicit run config, and the raw
`OptimizationResult`. Infeasible and feasible-limit results are successful HTTP transport (`200`)
with their original model status. The stateless result-table export endpoint Pydantic-validates the
in-session result posted back by the browser and returns a ZIP built from `result_tables()`; it does
not retrieve or persist a run. HTTP mapping:

| Status | Meaning |
| ---: | --- |
| 200 | Prepared/validated response or optimizer result, including non-optimal model statuses. |
| 400 | Malformed API envelope/header. |
| 401/403 | Missing or invalid service authorization. |
| 409 | Schema/capability/hash/idempotency conflict. |
| 413 | Byte or row limit exceeded. |
| 415 | Unsupported file/content type. |
| 422 | Located input/configuration validation issues. |
| 429 | Trusted-edge rate/concurrency limit. |
| 503 | Service or solver not ready. |
| 504 | Proxy/service solve timeout. |
| 500 | Redacted internal failure with correlation ID. |

Never serialize a Python traceback, filesystem path, service token, or input row in a response.

### Result presentation contract

The module is an operational workspace, not a landing page. Use the terminal's `PageHeader`,
`KpiStrip`, `Panel`, `DataGrid`, `Tag`, formatters, and Lucide icons. Do not add nested cards,
oversized marketing copy, decorative gradients, or a second visual design system.

Page structure:

1. `PageHeader`: `IBAL`, Inventory Optimizer, source provenance, engine/backend version, status.
2. Stable source/run toolbar: segmented `Synthetic | Upload`, generate/upload action, validate,
   run, reset, and download menu. Disable commands with a visible reason/tooltip.
3. Data workspace: synthetic controls or upload target/template actions on one side; preview summary
   and record tabs on the other. On narrow screens these become sequential full-width bands.
4. Validation issue grid: stage/code/location/message, filterable and linked to preview location.
5. Result KPI strip: status, objective value/delta, post on-loan, quantity change, weighted fill,
   binding constraints, runtime. Derived display aggregations may only sum fields already emitted;
   no new economic measure is introduced.
6. Result tabs: Overview, Allocations, Balances, Demand, Economics, Constraints, Diagnostics, Raw.

The Allocations view shows `current_quantity_shares`, `post_quantity_shares`, increase/decrease,
fee, cap, eligibility, reason codes, and expandable `explanation_evidence`. It may call positive
deltas `Increase` and negative deltas `Decrease`; it must not invent settlement instructions,
counterparty transfers, or an execution recommendation.

Constraint binding state is `abs(slack) <= displayed_tolerance` only if the engine does not expose
an explicit binding field. If the UI derives this display flag, the tolerance is shown and the raw
slack remains present. Objective, utilization, fill, status, and verification are never recomputed
when a direct field already exists.

Provenance source codes add `UPLOAD` to QuantMeridian's vocabulary with a file-upload description;
`SYNTHETIC` may render through canonical `SIM` styling but the module text must say `SYNTHETIC`, not
`LIVE`. Upload does not mean externally verified or live.

### Export contract

Downloads are generated from the completed in-memory run, with filenames containing safe request
ID, run ID, and date:

- `<request>-normalized-input.json`: exact request accepted by Pydantic.
- `<run>-optimization-result.json`: exact `OptimizationResult.model_dump(mode="json")`.
- `<request>-validation.json`: located issues and source/config disclosure.
- `<run>-result-tables.zip`: one CSV per `result_tables()` output using engine table names/order.

The Python service must use InventoryBallast table builders for the CSV ZIP. The browser may create
the three JSON download blobs from its in-session envelopes and raw result, but may not independently
flatten result schemas. The browser posts that raw result to the stateless result-table export
endpoint when a CSV ZIP is requested.

## State Model

Use one reducer/state machine rather than scattered component booleans:

```text
idle
  -> preparing_synthetic | uploading
  -> invalid | prepared
prepared
  -> validating -> invalid | ready
ready
  -> solving -> completed | failed
invalid/failed/completed
  -> preparing_synthetic | uploading | validating | reset -> idle
```

State carries source mode, dirty flag, envelope, explicit synthetic config, run config, result,
request/correlation IDs, and last error category. A monotonically increasing attempt token prevents
late responses from replacing newer state. Abort prior fetches when source or dataset changes.
Session means in-memory React state; no `localStorage`, IndexedDB, server database, or committed
fixture contains uploaded rows or results. Only non-sensitive control preferences may later be
persisted under a separately named key.

## Constitution Check

| Principle | Upheld? | Notes |
| --- | --- | --- |
| P1 Spec is source of truth | yes | This full SDD chain precedes cross-repository implementation. |
| P2 Traceability | yes | Every requirement/NFR maps below to tasks; every AC maps in `tasks.md`. |
| P3 Testable DoD | yes | Contract parity, property, security, benchmark, and browser evidence are named. |
| P4 Correct by construction | yes | Seeded PCG64, fixed timestamps, dependency-order generation, Pydantic construction, and engine revalidation prevent hidden randomness/leakage. |
| P5 Reversibility | yes | Separate module/API namespace, production-off feature flag, service kill switch, immutable engine pin. |
| P6 Observability | yes | Capabilities, health, metadata-only logs, error/latency counters, Data Ops status. |
| P7 Small changes | yes | Tasks are sliced service contract -> data paths -> proxy -> UI -> rollout. Existing `OPT` is untouched. |
| P8 No silent trade-offs | yes | Synchronous limits, session-only state, formats, unfinished capability gates, and deployment assumptions are explicit. |
| P9 Security and data | yes | Transient uploads, token boundary, redaction tests, macro/formula rejection, production auth gate. |
| P10 Honest reporting | yes | Explicit provenance and preserved solver/verification statuses; no fallback or promotion. |

## Traceability Matrix

| Requirement | Design element | Tasks |
| --- | --- | --- |
| REQ-001 | Separate `IBAL` route/nav/config and existing-OPT regression | T-009, T-015 |
| REQ-002 | Pinned engine dependency, `engine_service.py`, parity fixture | T-001, T-002, T-006, T-015 |
| REQ-003 | Explicit source state machine and no-fallback error handling | T-005, T-010, T-015 |
| REQ-004 | `SyntheticConfig`, PCG64, explicit dates/versions/hash | T-005, T-015 |
| REQ-005 | Profile registry and bounded synthetic controls | T-005, T-010 |
| REQ-006 | Dependency-order generator, engine validation, preview | T-005, T-010, T-015 |
| REQ-007 | Shared field registry and three generated templates | T-003, T-010, T-015 |
| REQ-008 | JSON/XLSX parser and resource/content controls | T-003, T-004, T-008, T-015 |
| REQ-009 | Located issue translation and no-repair policy | T-004, T-010, T-015 |
| REQ-010 | `DatasetEnvelope`, summary, hash, preview | T-002, T-004, T-005, T-010 |
| REQ-011 | Strict `RunConfig` allowlist and conflict detection | T-006, T-010, T-015 |
| REQ-012 | Healthy/valid UI gate and solve-time revalidation | T-006, T-008, T-010, T-015 |
| REQ-013 | Platform context, status/error mapping | T-006, T-008, T-011, T-015 |
| REQ-014 | Result workspace over raw result fields | T-011, T-015 |
| REQ-015 | Inspection/filtering/explanation/constraint views | T-011, T-015 |
| REQ-016 | Input/result/validation/table exports | T-007, T-012, T-015 |
| REQ-017 | Reducer lifecycle, confirmation, session-only state | T-010, T-012, T-015 |
| REQ-018 | Capability manifest/endpoint and UI enforcement | T-001, T-002, T-008, T-010, T-015 |
| REQ-019 | Health, Data Ops, redacted telemetry | T-002, T-013, T-015 |
| REQ-020 | Environment gates, credentials, deployment, rollback | T-008, T-014, T-015 |
| NFR-001 | Seeded generator and canonical parity tests | T-005, T-015 |
| NFR-002 | Engine-only domain math and architecture tests | T-006, T-011, T-015 |
| NFR-003 | Reference profiles and benchmark suite | T-005, T-015 |
| NFR-004 | Service/parser limits and early rejection | T-004, T-006, T-008, T-015 |
| NFR-005 | Transient processing, auth, redaction/security tests | T-002, T-004, T-008, T-014, T-015 |
| NFR-006 | Typed error/status mapping | T-006, T-008, T-010, T-011, T-015 |
| NFR-007 | Existing UI system, responsive/a11y browser verification | T-009, T-010, T-011, T-015 |
| NFR-008 | API/template versions, generated types, capabilities | T-001, T-002, T-003, T-008, T-015 |
| NFR-009 | Correlation IDs, telemetry, health, layered tests | T-002, T-008, T-013, T-015 |

## Trade-offs & Alternatives

| Decision | Chosen | Rejected alternative | Why |
| --- | --- | --- | --- |
| Product surface | New `IBAL` module | Replace existing `OPT` page | `OPT` is a broad simulated dashboard; replacing it changes an unrelated module and blurs provenance. |
| Runtime boundary | Python FastAPI companion service | Port solver/model to TypeScript | Keeps InventoryBallast the sole calculation authority and supports native HiGHS. |
| Browser path | Same-origin QuantMeridian proxy | Browser calls Python service directly | Keeps credentials server-side, centralizes limits, avoids CORS/public-service exposure. |
| Engine dependency | Immutable Git SHA/release pin | Mutable branch or copied source | Reproducible builds and explicit upgrades without source divergence. |
| Initial execution | Bounded synchronous solve | Queue/worker immediately | Smaller initial system and immediate workflow; strict limits contain request-window risk. |
| Upload formats | XLSX plus exact JSON | Arbitrary CSV collection | Workbook keeps related tables/schema version together; JSON serves machine workflows. |
| Spreadsheet semantics | Strict, no inference/repair | Convenient coercion and auto-fix | A quant control should reject ambiguity instead of silently changing positions or rates. |
| Synthetic ownership | QuantMeridian Python adapter | InventoryBallast core | Generator is an application/demo input adapter, not optimization policy. |
| Synthetic random source | Seeded NumPy PCG64 | `Math.random`, UUIDs, server clock | Cross-run deterministic and independent of render timing. |
| Run persistence | Browser session only | Server database/history | Avoids introducing retention, tenant isolation, and authorization before those are designed. |
| Output flattening | InventoryBallast `result_tables()` | TypeScript-built CSV schemas | Reuses the established output contract and prevents drift. |
| Feature discovery | Explicit capability manifest | Infer from Pydantic fields | Input classes can land before behavior, as expected economics currently demonstrates. |
| Production default | Off until trusted access boundary | Public demo endpoint | Uploaded books and CPU-heavy solve calls require access/rate controls. |

## Validation Strategy

### Python service tests

- Contract test the approved package SHA/version and capabilities manifest.
- Compare one golden service solve with direct facade invocation, excluding only `run_id`,
  `created_at`, and measured runtime.
- Property-test at least 100 synthetic config/seed combinations across profiles and bounds.
- Snapshot resolved profile configs and deterministic normalized request hashes.
- Parse valid starter/advanced workbooks and exact JSON to equivalent requests.
- Aggregate independent cell/Pydantic/reconciliation issues with exact workbook locations.
- Reject duplicate JSON keys, formulas, macros, external links, unknown data, oversized files,
  excessive rows, invalid booleans/dates/rates, and disabled features.
- Capture logs while confidential sentinel values pass through every endpoint; assert absence.
- Exercise optimal, feasible-limit, infeasible, numerical, timeout, configuration, and internal
  mappings with controlled backends/fixtures.
- Assert CSV ZIP contents exactly equal `result_tables()`.

### TypeScript and component tests

- Proxy tests for feature gate, auth injection, size/timeout handling, header propagation, and
  response/status pass-through.
- Reducer tests for every legal transition, stale-response token, abort, dirty confirmation, reset,
  and no-fallback rule.
- Capability tests proving disabled controls cannot be submitted even through altered client state.
- Presentation tests that trace every KPI/column to fixture result fields and preserve status.
- Existing nav/module/badge coverage tests updated deliberately for `IBAL`/`UPLOAD` provenance.
- `npm run typecheck`, `npm test`, and build pass with generated OpenAPI types current.

### End-to-end tests

Run the real local Python service and QuantMeridian dev server:

1. Generate a fixed demo profile, validate, solve, inspect allocation and constraint detail, and
   download/revalidate normalized input and result.
2. Download the starter workbook, upload it unchanged, validate, solve, and compare its request
   hash with the canonical JSON equivalent.
3. Upload a multi-error workbook and verify located issues, no solve call, no synthetic fallback.
4. Stop the Python service and verify `UNAVAILABLE`, disabled solve, and Data Ops health state.
5. Exercise keyboard flow and screenshots at 375x812, 768x1024, and 1440x900; assert no overlap,
   clipping, horizontal page overflow, blank panels, or console/page errors.

### Performance reference

Record OS, CPU, memory, Python, InventoryBallast SHA, HiGHS version, Node version, and dataset hash.
Warm up once, then run at least 20 iterations for generation/parsing and 10 for solve. Report p50,
p95, max, row counts, formulation, variables, and constraints. Keep benchmark output as CI artifact;
do not claim NFR-003 from a single laptop timing.

## Rollout, Observability & Rollback

### Configuration

QuantMeridian adds:

```text
settings/modules.config.json              IBAL.enabled=false by default
INVENTORY_OPTIMIZER_API_URL               server-only service base URL
INVENTORY_OPTIMIZER_API_TOKEN             server-only secret
INVENTORY_OPTIMIZER_API_TIMEOUT_MS         default 30000
INVENTORY_OPTIMIZER_MAX_UPLOAD_BYTES       default 10485760
INVENTORY_OPTIMIZER_AUTHORIZATION_REF      opaque trusted-boundary reference
```

Do not prefix any browser-visible variable with `VITE_` if it contains service location details or
credentials. Add placeholders, never values, to `.env.example`.

### Stages

1. Local: service and module enabled manually; golden/demo data only.
2. Protected staging: immutable engine image deployed, upload security tests passed, concurrency
   set to 1, trusted access boundary confirmed, synthetic and fictitious upload testing only.
3. Internal pilot: owner approves workbook and result interpretation; confidential-data log audit
   passes; run limits and retention statement are visible in operating docs.
4. Production: explicit owner sign-off flips `IBAL.enabled`; no automatic promotion from staging.

### Observability

Health distinguishes `live`, `degraded`, `incompatible`, `solver_unready`, and `unreachable`.
Metrics/logs include:

- request count and elapsed milliseconds by endpoint/result category;
- generation/parse/validation/solve duration;
- source mode and profile, never source rows or file name unless safely reduced to extension;
- row counts, formulation, solver status, verification passed, engine/backend versions;
- validation issue codes and counts, never messages if they can include identifiers;
- timeout, limit, auth, compatibility, and internal-error counts;
- correlation ID and idempotency key hash, never tokens.

Alert owner: Market Terminal owner for proxy/UI, InventoryBallast owner for package/solver defects.
Initial thresholds: any compatibility failure; solver readiness failure for 5 minutes; internal
error rate > 2% over 15 minutes with at least 10 calls; p95 solve > 20 seconds over 15 minutes;
verification failure count > 0. Verification failure immediately returns an error state and is not
shown as an accepted recommendation.

### Rollback

1. Set `IBAL.enabled=false` to remove navigation and block proxy endpoints.
2. If only the service release is faulty, redeploy the last approved immutable image/engine pin.
3. If schema compatibility fails, keep the module disabled; never downgrade requests silently.
4. Revert the isolated `IBAL` files and config entry if permanent removal is needed. Existing `OPT`
   and other terminal modules remain untouched.

No database rollback or uploaded-data cleanup is required because the initial service persists no
datasets or results. Container/process memory is the only server-side lifetime.

## Approved Decisions And Remaining Gates

- Approved 2026-09-14: `IBAL` as a separate module; immutable InventoryBallast pin `74737e5`;
  separate Python companion service; XLSX/JSON input; session-only transient data; local and
  protected-staging implementation may begin.
- Production gate: choose the Python container host and approve CPU, memory, concurrency,
  rate-limit, timeout, and trusted network boundaries.
- Production gate: confirm whether QuantMeridian adds user authentication or remains restricted to
  an already-private deployment. Production stays disabled until one path is verified.
- Follow-up requiring a new spec: saved datasets/runs, asynchronous solves, multi-period/scenario
  workflows, fee-tier authoring, and expected-economics controls after their engine capabilities
  are complete.

# Spec: Public API and CLI facade (T12)

- **ID:** 0003-public-api-cli
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code, reviewed and implemented against)
- **Approver:** Joshua Lutkemuller, CFA (approved the draft's three flagged decisions -- the
  `formulation/context.py::build_context()` extraction, the CLI exit-code scheme, and
  `load_config`'s reduced scope -- and directed implementation to proceed as drafted)
- **Last updated:** 2026-09-05

> WHAT and WHY only. No implementation detail — that belongs in `plan.md`.

## Problem & Context

`specs/spec002/01_SPEC.md` §17 defines the public surface every caller of this engine (a script, a
notebook, a future platform adapter) is meant to use instead of reaching into `formulation/`,
`solvers/`, or `validation/` directly: a stable facade (§17.1, `InventoryOptimizer` + `load_config`),
three service protocols (§17.2), and a CLI (§17.3). §17.4 (the QR Haven platform adapter,
`src/qr_haven/integrations/inventory_optimizer.py`) and most of §17.5 (the platform-owned half of
the invocation contract — authentication, persistence, idempotency-key *enforcement*, result
caching, cancellation cooperation) are out of scope: `docs/handoff.md`'s T12 entry already
scopes them out ("the adapter itself lives in `QR-Haven`, not here"), and `specs/spec002/
TRACEABILITY.md`'s `PLT-001`/`PLT-005`/`PLT-006` rows tag `T17`/`T34`, not `T12`, as their owning
tasks. `01_SPEC.md`'s own Task Matrix (§26) confirms the boundary directly: `T12 | Implement public
API and CLI | T02, T11 | end-to-end JSON test` — it depends only on T02 (config) and T11 (result/
attribution), not on T17/T34.

None of §17's public surface exists yet. `src/inventory_optimizer/__init__.py` exports only
`__version__`; there is no `InventoryOptimizer` class, no `load_config` function, no `services.py`,
no `cli.py`, and `pyproject.toml` has no `[project.scripts]` entry (confirmed by directory listing
and by reading `pyproject.toml` directly). Every dependency §17.1's facade would wrap is already
implemented and already tested in isolation: `validation.raise_if_invalid`/`validate_request`
(Section 7.1), `formulation.lp.compile_lp` (T08), `solvers.highs.HighsBackend` behind
`ports.solver.SolverBackend` (T09), `validation.solution_verifier.verify_solution` (T10), and
`reporting.result_builder.build_optimization_result` (T11, the primary dependency this facade
composes last). This spec's job is to wire those five already-correct stages together behind one
call, not to re-implement any of their logic.

Two integration details surfaced while reading that existing code closely enough to ground this
spec, both carried into `plan.md` rather than hidden:

1. `formulation.lp.compile_lp(request, config) -> CompiledProblem` builds a `BuildContext`
   internally (everything a component needs to `contribute()`) but does not return it — only the
   compiled matrices come back. `reporting.result_builder.build_optimization_result` requires a
   `VerifiedSolution`, which embeds that same `BuildContext` (`reporting/types.py`'s own docstring:
   "so `attribute()` can recompute ... from domain fields"). The only place in this repo that has
   ever needed a `BuildContext` outside `compile_lp` itself — `tests/unit/reporting/conftest.py`'s
   `_solve_and_verify` — currently rebuilds one by reaching into `compile_lp`'s private
   `_compute_demand_caps`/`_group_by` helpers. A production facade doing the same thing would
   depend on another module's private symbols; `plan.md` resolves this rather than leaving it as an
   implicit pattern to copy.
2. `InventoryOptimizerConfig` (`config/models.py`) is the Phase-0A subset of the full config object
   §8.2 describes: it has `desk`, `formulation`, `validation`, `solver`, `observability`,
   `elasticity` — it has **no** `objective` or `policy` section yet (both are explicitly listed in
   `config/models.py`'s own module docstring as "added as those subsystems land"). §17.1's
   illustrative `load_config(environment=..., desk=..., formulation=..., objective="net_revenue",
   policy="standard")` call assumes named-profile resolution across five axes and profile files on
   disk that do not exist (only `configs/default.yaml` exists, and `CFG-004` — desk profiles
   declaring required/optional components — is `TRACEABILITY.md`'s own row for that work, tagged
   `T35`, not `T12`). This spec's `load_config` is scoped to what today's config schema and
   `config/loader.py`'s existing `LAYER_ORDER`/`build_config` actually support, not the full
   illustrative signature; see Non-Goals and the Open Questions below.

Per `agents/README.md`'s routing table and `docs/handoff.md`'s own "How to actually start" section
for T12, this spec should ultimately be shaped with `agents/optimization/problem_formulation/` and
verified against `agents/testing_validation/`; that review has not happened yet (see Author line
above) and is a precondition for moving this spec's Status past `Draft`.

## Goals

- Provide one composed entry point, `InventoryOptimizer.optimize(request) -> OptimizationResult`,
  that runs validation → LP compilation → solve → independent verification → result assembly in
  that order, using only the five already-implemented modules named above.
- Provide `load_config(...) -> InventoryOptimizerConfig` as a thin, honestly-scoped wrapper over
  `config.build_config`/`config.load_yaml_file`/`config.hashing.config_hash` — not a
  reimplementation of config merging, and not a promise of the full five-axis profile resolution
  §17.1 illustrates until the config schema and profile files it depends on exist.
- Define `OptimizationService` and `ExplanationService` (§17.2) as `runtime_checkable` `Protocol`
  types, with `InventoryOptimizer` satisfying the former and a concrete implementation provided for
  the latter that derives its output from an already-built `OptimizationResult`'s existing
  `reason_codes`/`explanation_evidence` (T11), never by re-deriving from a `VerifiedSolution`.
- Add an `inventory-optimizer` console script (§17.3) with `validate`, `optimize`, `components`, and
  `doctor` as real subcommands, and `scenarios` as a recognized-but-explicitly-not-yet-implemented
  subcommand (see Non-Goals) — writing machine-readable output to `--output`/stdout, diagnostics to
  stderr, and a process exit code that distinguishes the categories §17.3 names.
- Supply `run_id`, `created_at`, `config_hash`, and `input_hash` — the four identity fields
  `build_optimization_result` deliberately left as caller-supplied keyword arguments so that
  function itself could stay pure (T11's own design choice) — deterministically and without
  duplicating `config.hashing.canonical_json`'s hashing logic.
- Supply the evidence `specs/spec002/TRACEABILITY.md`'s `PLT-002` row names for the `T01`-`T12`
  span it depends on ("component manifest" / "end-to-end golden test") — without unilaterally
  marking `PLT-002` `IMPLEMENTED` in this draft, since that row's gate (`G2C`) is a release
  approval this spec does not grant itself.

## Non-Goals

- **The QR Haven platform adapter (§17.4)** — lives in the separate `QR-Haven` repository per
  `01_SPEC.md` §17.4's own text ("The standalone core must not import the adapter or QR Haven") and
  `docs/handoff.md`'s T12 entry; not this repo's code to write.
- **Platform-owned parts of the invocation contract (§17.5)** — idempotency-key *rejection*
  enforcement, returning a cached result for a valid duplicate, and cooperative cancellation/time-
  budget honoring all require persisted state or a running worker loop that does not exist in this
  standalone core, and §17.5's own closing paragraph assigns "persistence... operational recovery"
  to the platform, not the optimizer. This spec's `InventoryOptimizer.optimize()` accepts and
  passes through an opaque `PlatformInvocationContext` (already implemented, T34) and supplies the
  `config_hash`/`input_hash` values a future cache layer would need to *detect* a duplicate — it
  does not implement the cache or the rejection logic itself.
- **`ScenarioService` (§17.2) as a real, implemented Protocol** — `run(request: ScenarioBatchRequest)
  -> ScenarioComparison` references two types (`ScenarioBatchRequest`, `ScenarioComparison`) that do
  not exist anywhere in this repo yet; the scenario engine (T13-T14) hasn't started. **Decision:**
  this spec does not define the `ScenarioService` Protocol at all, even as a stub, because doing so
  today would mean inventing the shape of those two types ahead of T13/T14's own spec — the same
  class of false-completeness risk `specs/0002-.../spec.md` explicitly corrected for `LP-008`. The
  CLI's `scenarios` subcommand exists as a recognized name (so `--help` matches §17.3's listed
  surface) but fails fast with a message naming T13/T14, rather than accepting input it cannot act
  on. This is a judgment call, not a certainty — see Risks and the final review notes.
- **Full five-axis named configuration profiles** (`environment=`, `desk=`, `formulation=`,
  `objective=`, `policy=` each resolving a name to a profile file on disk, per §17.1's illustrative
  import) — `objective`/`policy` config sections don't exist in `InventoryOptimizerConfig` yet, and
  desk-profile capability declarations are `CFG-004`/`T35`'s job, not `T12`'s. `load_config` here
  wraps only what `config/loader.py`'s existing `LAYER_ORDER` and `configs/default.yaml` already
  support.
- **Any change to `formulation.lp.compile_lp`'s public return signature.** It has roughly fifteen
  existing call sites across `tests/unit/` and `tests/golden/`, all expecting a single
  `CompiledProblem` back; this spec's resolution to the `BuildContext` problem (see Problem &
  Context) must not break them. The exact resolution is a `plan.md`/Open-Questions matter.
- **Agency/prime desk request shapes.** §17.1's "Agency and prime invocations select
  `desk="agency"` or `desk="prime"`" describes a target state; `OptimizationRequest`/`DeskContext`
  (Phase 0A) only carry the baseline securities-lending-inventory family today (`T35`-`T39` add the
  rest). This facade passes through whatever `problem_family`/`desk_context` a request already
  carries; it does not add new request fields.
- **New solver-diagnostics or reason-code content.** The CLI/facade surfaces exactly what
  `OptimizationResult` (T11) already contains; no new `SolverDiagnostics` field or `ReasonCode`
  predicate is added here.
- **Result persistence, a database, or any stored run history.** The CLI reads/writes plain files
  the caller names; there is no run store.

## Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| REQ-001 | The system shall provide an `InventoryOptimizer` facade class whose `optimize(request: OptimizationRequest) -> OptimizationResult` method composes, in order, `validation.raise_if_invalid`, `formulation.lp.compile_lp`, the configured `ports.solver.SolverBackend.solve`, `validation.solution_verifier.verify_solution`, and `reporting.result_builder.build_optimization_result`, without re-deriving any of their internal logic. | must |
| REQ-002 | The system shall provide `load_config(...) -> InventoryOptimizerConfig` composing the already-implemented `config.build_config`/`config.load_yaml_file`/`config.hashing.config_hash`, always applying `configs/default.yaml` as the lowest-precedence layer. | must |
| REQ-003 | `InventoryOptimizer.optimize()` shall compute `run_id`, `created_at`, `config_hash`, and `input_hash` itself and pass them to `build_optimization_result`, deriving `input_hash` from the request via the same canonical-JSON hashing approach `config.hashing.config_hash` already uses for config (not a second, ad hoc hash scheme). | must |
| REQ-004 | `InventoryOptimizer` shall select its `ports.solver.SolverBackend` from `InventoryOptimizerConfig.solver.backend`, translate `SolverConfig`'s fields into a `ports.solver.SolverOptions`, and raise a structured `ConfigurationError` for any backend name other than an actually-registered one (only `"highs"` today) rather than silently defaulting. | must |
| REQ-005 | `InventoryOptimizer.optimize()` shall accept an optional `platform: PlatformInvocationContext \| None` argument, pass it through unchanged to `build_optimization_result`'s `platform` keyword, and never import or depend on any platform-specific package to do so. | must |
| REQ-006 | The system shall define `OptimizationService` and `ExplanationService` as `runtime_checkable` `Protocol` classes matching §17.2's method signatures, with `InventoryOptimizer` satisfying `OptimizationService` structurally. | must |
| REQ-007 | The system shall provide a concrete `ExplanationService` implementation whose `explain(result: OptimizationResult) -> OptimizationExplanation` derives its output solely from `result.allocations[*].reason_codes`/`explanation_evidence` (already populated by T11), without re-solving or requiring a `VerifiedSolution`. | must |
| REQ-008 | The system shall add an `inventory-optimizer` console-script entry point dispatching to subcommands `validate`, `optimize`, `components`, `doctor`, and `scenarios`, writing machine-readable output to `--output`/stdout and diagnostics to stderr, per §17.3. | must |
| REQ-009 | The CLI's `validate` subcommand shall load an `OptimizationRequest` from `--request`, run `validation.validate_request` (not `raise_if_invalid`, so every issue is reported at once), and exit non-zero printing every `ValidationIssue` as structured JSON when any issue exists, zero otherwise. | must |
| REQ-010 | The CLI's `optimize` subcommand shall build config via `load_config`/`--config`, call `InventoryOptimizer.optimize()`, write the resulting `OptimizationResult` as JSON to `--output`/stdout, and select a process exit code that distinguishes success, a feasible-limit result, an infeasible/unbounded model, an invalid-input rejection, and an internal/solver error. | must |
| REQ-011 | The CLI's `components` subcommand shall print every `(kind, name, version)` triple from `components.registry.default_registry.manifest()` as JSON, after importing `formulation.lp` for its component-registration side effect so the listing reflects what a real `compile_lp` call actually uses. | must |
| REQ-012 | The CLI's `doctor` subcommand shall perform a read-only self-check — default config loads and hashes without error, the configured solver backend is importable/constructible, and the component registry is non-empty after import — reporting each check's pass/fail individually, without mutating any file or external state. | must |
| REQ-013 | The CLI's `scenarios` subcommand shall exist and appear in `--help`, but shall exit non-zero with a message naming T13/T14 as the owning future work, rather than either fabricating scenario behavior or being silently absent from the subcommand list. | must |

## Non-Functional Requirements

| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | Determinism modulo identity | Given the same `OptimizationRequest` and `InventoryOptimizerConfig`, two `InventoryOptimizer.optimize()` calls produce `OptimizationResult`s identical in every field except `run_id`, `created_at`, and `solver.runtime_seconds` (wall-clock solve time, inherently non-deterministic across separate `.solve()` calls — confirmed empirically during implementation: `HighsBackend.solve()`'s measured runtime differs run-to-run on an identical, tiny E1-sized problem even though `iterations`/`termination_reason` do not). |
| NFR-002 | No unhandled tracebacks from the CLI | The CLI never surfaces a raw Python traceback for a recognized exception class (`InputValidationError`, `ConfigurationError`, `RegistrationError`, `AttributionMismatchError`); each is caught, reported as a structured stderr diagnostic, and mapped to its own distinguishing exit code. |
| NFR-003 | No platform import leakage | `services.py`, the new facade module, and `cli.py` import nothing from `qr_haven` or any other platform-specific package, extending `ARC-002`'s existing boundary to this spec's new surface. |
| NFR-004 | CLI output stability | For a fixed request/config pair, the `optimize` subcommand's JSON output is stable across repeated runs field-for-field, excluding only `run_id`/`created_at`/`solver.runtime_seconds` (the same three identity/wall-clock fields NFR-001 excludes at the facade level — the CLI does not add any further non-determinism). |

## Acceptance Criteria

| ID | Given / When / Then | Covers |
| --- | --- | --- |
| AC-001 | Given a valid `OptimizationRequest` and `InventoryOptimizerConfig` (the E1 golden fixture), when `InventoryOptimizer(config=config).optimize(request)` is called, then it returns an `OptimizationResult` with `verification.passed is True` and `status == SolverStatus.OPTIMAL`. | REQ-001 |
| AC-002 | Given the same E1 fixture solved twice via `InventoryOptimizer.optimize()`, when the two `OptimizationResult`s are compared field-by-field excluding `run_id`/`created_at`/`solver.runtime_seconds`, then every other field is identical. | REQ-001, NFR-001 |
| AC-003 | Given `load_config()` called with no explicit overrides, when compared to `config.build_config(defaults=config.load_yaml_file(Path("configs/default.yaml")))`, then the two `InventoryOptimizerConfig` objects and their `config_hash` values are identical. | REQ-002 |
| AC-004 | Given two `OptimizationRequest` objects identical except one route's `fee_rate`, when `InventoryOptimizer.optimize()` computes `input_hash` for each, then the two hashes differ; given two byte-identical requests, their hashes are equal. | REQ-003 |
| AC-005 | Given `InventoryOptimizerConfig.solver.backend == "not-a-real-backend"`, when `InventoryOptimizer(config=config)` is constructed, then it raises `ConfigurationError` before any solve is attempted. | REQ-004 |
| AC-006 | Given a `PlatformInvocationContext` instance, when passed to `optimize(request, platform=context)`, then `result.platform is context` and no module named `qr_haven` appears in `sys.modules` anywhere in the call path. | REQ-005, NFR-003 |
| AC-007 | Given an `InventoryOptimizer` instance, when checked with `isinstance(optimizer, OptimizationService)` against the `runtime_checkable` Protocol, then it evaluates `True` without `InventoryOptimizer` explicitly subclassing it. | REQ-006 |
| AC-008 | Given an already-built `OptimizationResult` whose `allocations` carry `reason_codes`/`explanation_evidence` for at least one route (E1 with a binding demand cap), when the `ExplanationService` implementation's `explain(result)` runs, then the returned `OptimizationExplanation` includes that route's reason codes and evidence, and no solver or verifier call occurs during `explain()`. | REQ-007 |
| AC-009 | Given `pyproject.toml` after `pip install -e .`, when `inventory-optimizer --help` runs, then it exits zero and lists `validate`, `optimize`, `scenarios`, `components`, `doctor` as subcommands. | REQ-008 |
| AC-010 | Given a request JSON file with both a stale `as_of` and a separately-broken cross-record reconciliation issue, when `inventory-optimizer validate --request stale.json --config run.yaml` runs, then it exits non-zero and both `ValidationIssue`s appear in the JSON output — not just the first one found. | REQ-009 |
| AC-011 | Given the E1 golden fixture as `request.json`/`run.yaml`, when `inventory-optimizer optimize --request request.json --config run.yaml --output result.json` runs twice, then both runs exit zero, `result.json` parses with `verification.passed == true`, and the two files are identical except for `run_id`/`created_at`/`solver.runtime_seconds` (see NFR-001's note — the same wall-clock non-determinism applies here). | REQ-010, NFR-004 |
| AC-012 | Given a request engineered to be infeasible, when `inventory-optimizer optimize` runs against it, then its exit code differs from both AC-011's success case and AC-010's invalid-input case. | REQ-010 |
| AC-013 | Given no request/config files at all, when `inventory-optimizer components` runs, then it prints every `(kind, name, version)` from `default_registry.manifest()` post-import, including at least `fee_revenue`, `transition_cost`, and `inventory_balance`. | REQ-011 |
| AC-014 | Given a working environment with `highspy` installed, when `inventory-optimizer doctor` runs, then it exits zero and reports every check as passing; given `highspy` is not importable, it exits non-zero and names the solver-backend check specifically as the failure, not a generic traceback. | REQ-012, NFR-002 |
| AC-015 | Given `inventory-optimizer scenarios --request batch.json --config run.yaml`, when run today, then it exits non-zero with a message naming T13/T14, and `scenarios` still appears in `--help`'s subcommand list. | REQ-013 |

## Data & Dependencies

- `validation.raise_if_invalid`/`validation.validate_request` (Section 7.1, already implemented) —
  read-only input to REQ-001/REQ-009.
- `formulation.lp.compile_lp` (T08) and its internally-built `BuildContext` (`formulation/
  context.py`) — see Problem & Context; `plan.md` resolves how the facade obtains a `BuildContext`
  without duplicating `compile_lp`'s private helpers.
- `ports.solver.SolverBackend`/`SolverOptions`/`SolverResult` (T09 protocol) and
  `solvers.highs.HighsBackend` (T09 concrete, registered as `("solver_backend", "highs", "1")` via
  `components.decorators.solver_backend`) — the only registered backend today; `highspy` is an
  optional extra (`pyproject.toml`'s `highs` extra), so it must not be imported unconditionally at
  module load.
- `validation.solution_verifier.verify_solution`/`VerificationReport` (T10) — read-only input.
- `reporting.types.VerifiedSolution`, `reporting.result_builder.build_optimization_result` (T11) —
  this spec's primary composed dependency; not re-implemented.
- `config.build_config`, `config.load_yaml_file`, `config.hashing.canonical_json`/`config_hash`
  (T02) — `load_config`'s only building blocks.
- `platform.context.PlatformInvocationContext` (T34, already implemented) — accepted and passed
  through opaquely; never constructed or inspected beyond pass-through.
- `components.registry.default_registry`/`ComponentKind` (T05) — read by the `components` CLI
  subcommand and by backend resolution.
- `specs/spec002/TRACEABILITY.md`'s `PLT-002` row (`T01`-`T12` / `R1` / `G2C`) is the primary row
  this spec's evidence feeds; `ARC-001`/`PLT-001`/`PLT-005`/`PLT-006`/`CFG-004` are tagged `T17`/
  `T34`/`T35` and are **not** rows this spec closes (see Non-Goals).
- `tests/golden/`, `tests/conftest.py`'s `e1_request`/`default_config` fixtures — reused rather than
  duplicated for AC evidence, matching T11's own Validation Strategy precedent.

## Risks

| ID | Risk | Impact | Mitigation |
| --- | --- | --- | --- |
| RISK-001 | The facade reconstructs `BuildContext` by reaching into `formulation.lp`'s private `_compute_demand_caps`/`_group_by` helpers (the only existing precedent, in a test fixture), coupling production code to another module's private symbols and risking silent drift if either changes independently. | A future change to `compile_lp`'s internals silently breaks facade correctness without any import-time or type-level signal. | `plan.md` proposes extracting a shared, public `formulation.context.build_context()` helper instead of copying the private-reach-in pattern; flagged for explicit sign-off since it touches a T08 file this spec was told only to wrap, not modify. |
| RISK-002 | A CLI subcommand catches a broad exception and reports a misleading exit-code category (e.g., an internal bug reported as "invalid input"), eroding trust in the exit-code contract §17.3 promises. | A caller scripting against exit codes makes a wrong automated decision (e.g., retries a non-retryable failure). | NFR-002 requires exit-code selection to switch on the specific structured exception type, never a bare `except Exception`; AC-012/AC-014 require the failing check to be named specifically. |
| RISK-003 | `load_config`'s reduced signature is mistaken for full §17.1 conformance, since `01_SPEC.md` still shows the five-axis illustrative call verbatim. | A reviewer or future caller assumes `environment=`/`objective=`/`policy=` profile resolution exists when it does not, and ships code that silently no-ops or errors on those keywords. | `load_config`'s own docstring and this spec's Non-Goals state the gap explicitly; `TRACEABILITY.md`'s `CFG-004` row stays `SPECIFIED`, not marked as if this spec closed it. |
| RISK-004 | Defining `ScenarioService`'s Protocol shape now (even as a stub) would lock in method signatures referencing `ScenarioBatchRequest`/`ScenarioComparison` before T13/T14 decide their real shape. | A later, real scenario-engine spec inherits an awkward signature it must either keep for compatibility or breakingly change. | This spec deliberately does not define `ScenarioService` at all (see Non-Goals); the CLI's `scenarios` subcommand fails fast by name only, with no Protocol backing it yet. |
| RISK-005 | `optimize`'s CLI output is the first place `OptimizationResult` (a large nested Pydantic model) is serialized to JSON at the process boundary; a naive dump could in principle emit non-finite floats (`NaN`/`Infinity`), which are invalid per RFC 8259 and unparseable by strict downstream JSON tooling. | A CLI-produced result file silently fails to parse in a downstream system, discovered only when that system errors far from the actual cause. | `tasks.md`'s CLI-serialization task must include a test asserting the output parses with Python's strict `json.loads` (which rejects `NaN`/`Infinity` unless explicitly allowed), not just that `model_dump_json()` did not raise. |

## Assumptions & Open Questions

- Assumption: "material" scope boundaries already drawn by `docs/handoff.md`'s T12 entry (§17.4/
  17.5's platform-owned half out of scope) are correct and current; this spec does not re-litigate
  them, only restates them precisely against the actual `TRACEABILITY.md` task tags.
- Open question (resolved in `plan.md`, flagged for sign-off): how the facade obtains a
  `BuildContext` without either (a) reaching into `compile_lp`'s private helpers or (b) widening
  `compile_lp`'s public return signature and breaking ~15 existing call sites. `plan.md` proposes a
  third option; it is the least certain design decision in this draft.
- Open question (resolved in `plan.md`, flagged for sign-off since it becomes a stable contract once
  shipped): the exact integer exit codes for each of §17.3's five distinguished categories. No
  convention exists yet anywhere in this repo.
- Open question: exact CLI flag shapes beyond the five subcommand verbs themselves — e.g., whether
  `optimize` needs a `--platform <file>` flag to supply a `PlatformInvocationContext`, and whether
  `--config` accepts one merged YAML file or multiple `--config` flags mapped onto
  `config.loader.LAYER_ORDER`. `plan.md` picks a minimal default (one `--config` file, no
  `--platform` flag in this first cut); this is explicitly a smaller surface than §17.1's Python API
  offers and may need revisiting once a real caller exists.
- Open question: whether `load_config` should keep that exact name (matching §17.1 verbatim, at the
  risk of implying more conformance than RISK-003 warns about) or be named differently to signal its
  reduced scope. `plan.md` keeps the name `load_config` for now, for API-surface consistency with
  `01_SPEC.md`, but flags this as worth a second opinion.

## Exceptions

None recorded.

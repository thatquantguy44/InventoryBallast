# Plan: Public API and CLI facade (T12)

- **Spec:** 0003-public-api-cli (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code, implemented as described below)
- **Last updated:** 2026-09-05

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Add two new top-level modules plus one small, additive extraction from an existing module —
nothing in `formulation/lp.py` (public signature), `solvers/highs.py`, `validation/`, or
`reporting/` changes its existing contract:

1. **`services.py`** — the §17.2 Protocols (`OptimizationService`, `ExplanationService`, both
   `runtime_checkable`, mirroring the existing pattern in `ports.solver.SolverBackend`) plus
   `OptimizationExplanation` (a new small aggregate type) and a concrete `ExplanationServiceImpl`.
   `ScenarioService` is deliberately not defined here (`spec.md` Non-Goals).
2. **`facade.py`** — `InventoryOptimizer` (the class satisfying `OptimizationService`) and
   `load_config`. This is where `run_id`/`created_at` are generated and where `input_hash` is
   computed — the one place in this spec's surface that is intentionally impure (wall clock,
   `uuid4`), matching T11's own design note that `build_optimization_result` left those four fields
   as caller-supplied precisely so its own function could stay pure.
3. **`cli.py`** — `main(argv: Sequence[str] | None = None) -> int`, an `argparse` dispatcher over
   five subcommands, each a small handler function. `sys.exit(main())` is the only thing
   `[project.scripts]` needs to invoke.
4. **`formulation/context.py::build_context(request, config) -> BuildContext`** — a new public
   function extracted from `formulation.lp.compile_lp`'s current inline construction (see
   "Resolving the `BuildContext` gap" below). `compile_lp` itself is refactored to call this new
   function internally instead of building the same shape inline a second time; its own public
   signature (`compile_lp(request, config) -> CompiledProblem`) does not change, so none of its
   ~15 existing call sites in `tests/unit/`/`tests/golden/` need updating.

`src/inventory_optimizer/__init__.py` gains two re-exports (`InventoryOptimizer`, `load_config`),
matching §17.1's `from inventory_optimizer import InventoryOptimizer, load_config`.
`pyproject.toml` gains one `[project.scripts]` line.

### Resolving the `BuildContext` gap

`spec.md`'s Problem & Context section names the issue: `compile_lp` builds a `BuildContext`
internally but never returns it, and the only existing precedent for needing one outside
`compile_lp` (`tests/unit/reporting/conftest.py::_solve_and_verify`) rebuilds an equivalent one by
calling `compile_lp`'s private `_compute_demand_caps`/`_group_by` helpers directly. Three options
were considered:

- **(A) Widen `compile_lp`'s return type** to `tuple[CompiledProblem, BuildContext]`. Rejected:
  breaks every existing call site (`tests/unit/test_lp_compiler.py`, `test_solution_verifier.py`,
  `test_highs_backend.py`, `tests/golden/test_e1_scarce_name_allocation.py`, and the T11 conftest
  itself) for a facade-only need.
- **(B) Have the facade duplicate the private-helper reach-in**, same as the T11 test conftest.
  Rejected: this would be the first time production code (not a test) depends on another module's
  underscore-prefixed symbols; a future change to `compile_lp`'s internals could silently break the
  facade with no import-time signal, and it duplicates logic that already exists once.
- **(C) Extract a shared, public `build_context()` helper** in `formulation/context.py` (the module
  that already owns the `BuildContext` dataclass) that both `compile_lp` and the facade call.
  **Chosen.** `compile_lp`'s own internals (`_compute_demand_caps`, `_group_by`, the
  `inventory_by_id`/`routes_by_*` grouping) move, verbatim, into this new function; `compile_lp`
  calls it once, in place of its current inline block, so behavior is provably unchanged (same code,
  new location). The facade calls the same function once, independently, to get its own
  `BuildContext` before separately calling `compile_lp` for the `CompiledProblem`. This means the
  grouping/demand-cap computation runs twice per `optimize()` call (once inside each), which is
  cheap, pure, and non-hot-path work (a handful of dict comprehensions over route lists, not the
  vectorized formulation math NFR-003 in T11 was written for) — an acceptable, explicit trade-off,
  not a silent one.

This is flagged in `spec.md` as the least-certain design decision in this draft because it is the
one place this spec touches a file (`formulation/context.py`, and `formulation/lp.py`'s *internals*,
not its signature) outside the "wrap, don't reinvent" set of modules it was scoped to only consume.
Human sign-off on option (C) specifically (versus, say, accepting option (B)'s coupling as a known,
documented trade-off instead) is requested before implementation starts.

### Lazy solver-backend import

`solvers.highs` is the sole owner of `highspy` imports (Section 16.4), and `highspy` is an optional
extra (`pyproject.toml`'s `highs` extra) — not a hard dependency of `inventory-optimizer`. If
`facade.py` imported `solvers.highs` unconditionally at module load, importing `inventory_optimizer`
at all would require the `highs` extra to be installed, breaking `ARC-003`'s "independently
installable" guarantee for anyone who only needs, say, the LP compiler or the domain contracts.
`InventoryOptimizer.__init__` therefore imports `inventory_optimizer.solvers.highs` lazily, inside
the backend-resolution helper, only when `config.solver.backend == "highs"` is actually requested,
and translates any resulting `ImportError` into a `ConfigurationError` naming the missing `highs`
extra rather than letting a raw `ImportError` surface.

## Architecture & Components

```
formulation/context.py
  + build_context(request: OptimizationRequest, config: InventoryOptimizerConfig) -> BuildContext
    # extracted from compile_lp's current inline construction; compile_lp calls this internally

services.py
  OptimizationService(Protocol)      # optimize(request) -> OptimizationResult
  ExplanationService(Protocol)       # explain(result) -> OptimizationExplanation
  OptimizationExplanation            # new: aggregate view over a result's per-route explanations
  ExplanationServiceImpl             # concrete; reads only OptimizationResult.allocations

facade.py
  InventoryOptimizer
    __init__(self, *, config: InventoryOptimizerConfig, backend: SolverBackend | None = None)
    optimize(self, request, *, platform: PlatformInvocationContext | None = None) -> OptimizationResult
  load_config(*, config_path: Path | None = None, overrides: Mapping[str, Any] | None = None) -> InventoryOptimizerConfig
  _resolve_backend(solver_config: SolverConfig) -> SolverBackend       # private, lazy-imports solvers.highs
  _solver_options_from_config(solver_config: SolverConfig) -> SolverOptions   # private
  _hash_request(request: OptimizationRequest) -> str                          # private, reuses canonical_json
  _generate_run_id(prefix: str) -> str                                        # private, uuid4-based

cli.py
  main(argv: Sequence[str] | None = None) -> int
  _cmd_validate / _cmd_optimize / _cmd_components / _cmd_doctor / _cmd_scenarios   # private handlers
  _EXIT_* constants                                                                # see Exit codes below

pyproject.toml
  [project.scripts]
  inventory-optimizer = "inventory_optimizer.cli:main"

__init__.py
  + from inventory_optimizer.facade import InventoryOptimizer, load_config
  + __all__ += ["InventoryOptimizer", "load_config"]
```

`services.py` sits at the top level (not under `ports/`) because `ports/solver.py`'s own docstring
scopes that package to internal backend-abstraction protocols ("Solver backend protocol...");
`services.py` fronts the outward-facing contract §17.2 names, which is a different audience
(callers of this library) than `ports/`'s audience (backend implementers).

## Interfaces & Data Contracts

```python
# services.py
@runtime_checkable
class OptimizationService(Protocol):
    def optimize(self, request: OptimizationRequest) -> OptimizationResult: ...

@runtime_checkable
class ExplanationService(Protocol):
    def explain(self, result: OptimizationResult) -> OptimizationExplanation: ...

@dataclass(frozen=True, slots=True)
class OptimizationExplanation:
    """Aggregate, read-only view over a result's per-route explanations (Section 18.3) --
    not a re-derivation. Built entirely from `OptimizationResult.allocations`, which already
    carries each route's `reason_codes`/`explanation_evidence` (populated during T11's
    `build_optimization_result` via `reporting.explanations.explain_routes`)."""

    run_id: str
    routes_with_reasons: tuple[RouteExplanationView, ...]   # route_id, reason_codes, evidence
    reason_code_counts: Mapping[ReasonCode, int]             # e.g. {DEMAND_CAP_BINDING: 3, ...}


class ExplanationServiceImpl:
    def explain(self, result: OptimizationResult) -> OptimizationExplanation:
        routes = tuple(
            RouteExplanationView(a.route_id, a.reason_codes, a.explanation_evidence)
            for a in result.allocations
            if a.reason_codes
        )
        counts: dict[ReasonCode, int] = {}
        for route in routes:
            for code in route.reason_codes:
                counts[code] = counts.get(code, 0) + 1
        return OptimizationExplanation(
            run_id=result.run_id, routes_with_reasons=routes, reason_code_counts=counts
        )
```

```python
# facade.py
class InventoryOptimizer:
    def __init__(
        self, *, config: InventoryOptimizerConfig, backend: SolverBackend | None = None
    ) -> None:
        self._config = config
        self._backend = backend if backend is not None else _resolve_backend(config.solver)
        self._config_hash = config_hash(config)   # computed once, reused across calls

    def optimize(
        self, request: OptimizationRequest, *, platform: PlatformInvocationContext | None = None
    ) -> OptimizationResult:
        raise_if_invalid(request, max_staleness_hours=self._config.validation.max_staleness_hours)
        context = build_context(request, self._config)
        problem = compile_lp(request, self._config)
        result = self._backend.solve(problem, _solver_options_from_config(self._config.solver))
        verification = verify_solution(problem, result)
        solution = VerifiedSolution(
            context=context, problem=problem, result=result, verification=verification
        )
        return build_optimization_result(
            solution,
            run_id=_generate_run_id(self._config.observability.run_id_prefix),
            created_at=datetime.now(UTC),
            config_hash=self._config_hash,
            input_hash=_hash_request(request),
            platform=platform,
        )


def load_config(
    *, config_path: Path | None = None, overrides: Mapping[str, Any] | None = None
) -> InventoryOptimizerConfig:
    """Deliberately reduced vs. Section 17.1's illustrative five-axis signature -- see spec.md's
    Non-Goals and Open Questions. Always applies `configs/default.yaml` as the `defaults` layer;
    `config_path` (if given) is merged as the `run` layer; `overrides` (if given) as the
    `overrides` layer -- both already-named slots in `config.loader.LAYER_ORDER`."""
    defaults = load_yaml_file(_PACKAGE_DEFAULT_YAML_PATH)
    run_layer = load_yaml_file(config_path) if config_path is not None else None
    return build_config(defaults=defaults, run=run_layer, overrides=overrides)
```

`_hash_request` reuses `config.hashing.canonical_json` exactly as `config.hashing.config_hash`
already does for config, applied to `request.model_dump(mode="json")` instead of a config dump —
one hashing helper, two callers, no second hash implementation:

```python
def _hash_request(request: OptimizationRequest) -> str:
    return hashlib.sha256(
        canonical_json(request.model_dump(mode="json")).encode("utf-8")
    ).hexdigest()
```

`_resolve_backend` translates an unregistered `config.solver.backend` name into `ConfigurationError`
before any solve is attempted (REQ-004), and translates a missing `highspy` install into the same
exception type naming the `highs` extra (see "Lazy solver-backend import" above) rather than letting
`ImportError` propagate raw:

```python
def _resolve_backend(solver_config: SolverConfig) -> SolverBackend:
    if solver_config.backend == "highs":
        try:
            from inventory_optimizer.solvers.highs import HighsBackend
        except ImportError as exc:
            raise ConfigurationError(
                "solver backend 'highs' requires the 'highs' extra "
                "(pip install -e '.[highs]')"
            ) from exc
        return HighsBackend()
    raise ConfigurationError(f"unregistered solver backend: {solver_config.backend!r}")
```

### CLI exit codes (proposed; see spec.md's Open Questions)

| Code | Meaning | Condition |
| --- | --- | --- |
| 0 | Success | `SolverStatus.OPTIMAL`, `verification.passed is True` |
| 1 | Invalid input | `InputValidationError` raised before a solve is attempted |
| 2 | Infeasible / unbounded model | `SolverStatus` in `{INFEASIBLE, UNBOUNDED, INFEASIBLE_OR_UNBOUNDED}` |
| 3 | Feasible-limit result | `SolverStatus.FEASIBLE_LIMIT` (a usable but not proven-optimal incumbent) |
| 4 | Internal / solver error | Any other `SolverStatus` (`INVALID_MODEL`, `NUMERICAL_ERROR`, `INTERRUPTED`, `SOLVER_ERROR`), `verification.passed is False`, `ConfigurationError`, `RegistrationError`, `AttributionMismatchError`, or any uncaught exception |

`validate`, `components`, and `doctor` use only codes 0/1/4 (there is no solver involved in those
paths); `optimize` is the only subcommand that can produce codes 2/3.

## Constitution Check

| Principle | Upheld? | Notes |
| --- | --- | --- |
| P4 Correct by construction | yes | The facade calls the already-verified pipeline in the fixed order §17.1/T08-T11 established; it adds no new numerical logic. `ConfigurationError` fails closed on an unregistered backend rather than silently defaulting (REQ-004). |
| P5 Reversibility | yes | `services.py`, `facade.py`, `cli.py` are additive new modules; the `build_context()` extraction is a same-behavior move, not a semantic change (`compile_lp`'s own tests are the regression check). Reverting this spec's commits removes the new modules and the `[project.scripts]` line cleanly; the `formulation/context.py` extraction would need its own, separate revert if ever needed, since it also touches `compile_lp`'s internals — noted explicitly, not hidden. |
| P6 Observability | yes | CLI diagnostics go to stderr, structured `ValidationIssue`s are never truncated to "first issue only" (REQ-009), exit codes are documented and specific per failure class (NFR-002), `doctor` names which check failed rather than a generic error. |
| P9 Security & data | yes | No secrets, credentials, or client-identifying data enter any new module; CLI reads/writes only the files the caller names via `--request`/`--config`/`--output`. |

## Traceability Matrix

| Requirement | Design element | Tasks |
| --- | --- | --- |
| REQ-001 | `facade.py::InventoryOptimizer.optimize`; `formulation/context.py::build_context` | T-001, T-004 |
| REQ-002 | `facade.py::load_config` | T-003 |
| REQ-003 | `facade.py::_hash_request`, `_generate_run_id` | T-004 |
| REQ-004 | `facade.py::_resolve_backend`, lazy `solvers.highs` import | T-004 |
| REQ-005 | `facade.py::InventoryOptimizer.optimize`'s `platform` passthrough | T-004 |
| REQ-006 | `services.py::OptimizationService`, `ExplanationService` (`runtime_checkable` Protocols) | T-002 |
| REQ-007 | `services.py::ExplanationServiceImpl`, `OptimizationExplanation` | T-002 |
| REQ-008 | `cli.py::main`; `pyproject.toml`'s `[project.scripts]` | T-005 through T-010 |
| REQ-009 | `cli.py::_cmd_validate` | T-005 |
| REQ-010 | `cli.py::_cmd_optimize`; exit-code table above | T-006 |
| REQ-011 | `cli.py::_cmd_components` | T-007 |
| REQ-012 | `cli.py::_cmd_doctor` | T-008 |
| REQ-013 | `cli.py::_cmd_scenarios` (stub) | T-009 |
| NFR-001 | `InventoryOptimizer.optimize`'s only per-call-varying identity fields are `run_id`/`created_at` | T-011 |
| NFR-002 | `cli.py`'s per-subcommand `try`/`except` over the named structured exception types only | T-005 through T-009, T-012 |
| NFR-003 | No `qr_haven` import anywhere in `services.py`/`facade.py`/`cli.py` | T-002, T-004, T-011 |
| NFR-004 | `cli.py::_cmd_optimize` writes `model_dump_json()` with `sort_keys`-equivalent stable output | T-006, T-012 |

## Trade-offs & Alternatives

| Decision | Chosen | Rejected alternative | Why |
| --- | --- | --- | --- |
| `BuildContext` availability | Extract `formulation.context.build_context()`, called by both `compile_lp` and the facade | Widen `compile_lp`'s return type; duplicate the private-helper reach-in | Widening breaks ~15 existing call sites; duplicating couples production code to underscore-prefixed symbols in another module. See "Resolving the `BuildContext` gap" above — flagged for sign-off regardless. |
| Solver-backend import timing | Lazy, inside `_resolve_backend`, only for `backend == "highs"` | Eager `import inventory_optimizer.solvers.highs` at `facade.py` module load | Eager import would force the optional `highs` extra onto anyone who imports `inventory_optimizer` at all, breaking `ARC-003`'s portability guarantee. |
| Module layout for Protocols | New `services.py` at the top level | Nest under `ports/` alongside `ports/solver.py` | `ports/`'s own docstring scopes it to internal backend-abstraction protocols; `services.py` fronts a different, outward-facing audience (§17.2's own heading). |
| `ScenarioService` | Not defined at all in this spec; CLI `scenarios` subcommand fails fast by name only | Define the Protocol now with placeholder/`Any`-typed request/response | A Protocol referencing `ScenarioBatchRequest`/`ScenarioComparison` before T13/T14 decide their real shape risks locking in a signature that spec will have to either keep for compatibility or breakingly change. |
| `load_config` scope | Reduced to `config_path`/`overrides` over the existing `LAYER_ORDER` "run"/"overrides" slots | Implement the full `environment=`/`desk=`/`formulation=`/`objective=`/`policy=` signature with stub/no-op behavior for the axes with no config section yet | A signature that accepts keywords it cannot honor (no `ObjectiveConfig` exists to merge `objective=` into) is worse than a narrower, honestly-scoped one — matches spec.md's Non-Goals reasoning and avoids a second false-completeness claim. |
| CLI I/O format | JSON files/stdout only | YAML CLI output, or a richer text/table report | §17.3's own text: "CLI writes machine-readable output"; JSON matches `OptimizationResult.model_dump_json()` directly, no second serialization format to maintain. |

## Validation Strategy

- Reuse `tests/conftest.py`'s `e1_request`/`default_config` fixtures for facade-level tests
  (`tests/unit/test_facade.py`, `tests/unit/test_services.py`) rather than authoring a new fixture
  family, matching T11's own precedent.
- CLI tests (`tests/unit/test_cli.py`) invoke `cli.main(argv)` directly (no subprocess) against
  `tmp_path`-written request/config JSON/YAML files, asserting on `capsys` output and the returned
  exit code — faster and more debuggable than shelling out, while still exercising the real
  `argparse` wiring.
- One additional end-to-end test (`tests/golden/test_e1_cli_end_to_end.py`) invokes the CLI via
  `subprocess.run(["inventory-optimizer", ...])` after `pip install -e .`, satisfying `01_SPEC.md`
  §26's own listed evidence for T12 ("end-to-end JSON test") with a real installed console script,
  not just an in-process `argparse` call — this is the evidence `PLT-002`'s row also names
  ("end-to-end golden test").
- AC-011's byte-for-byte repeat-run comparison excludes only `run_id`/`created_at` by diffing parsed
  JSON with those two keys removed, not by string-diffing the raw files (which would also need to
  tolerate key ordering if `model_dump_json()`'s field order were ever to change).
- No backtest/leakage gates apply (this is an orchestration/CLI layer, not a time-series pipeline);
  the relevant quant gate is `repro` (NFR-001, NFR-004) via `hooks/stages/run-stage.sh`.

## Rollout, Observability & Rollback

Additive library + CLI surface; no runtime consumer depends on it yet (this is the first spec to
introduce one). No feature flag, no staged rollout, no production traffic at risk. Rollback is a
revert of `services.py`, `facade.py`, `cli.py`, the `pyproject.toml`/`__init__.py` diffs, and
(separately, since it touches an existing file) the `formulation/context.py` extraction — the latter
should be called out on its own in any revert, per P5's note above. Observability is the CLI's own
stderr diagnostics plus the test suite; `specs/engine_spec/TRACEABILITY.md`'s `PLT-002` row evidence
pointer and `docs/handoff.md`'s "Next priorities" section are updated once this spec is actually
implemented (tracked as T-013/T-014 in `tasks.md`, not performed by this draft).

## Open Questions

- Whether `ExplanationServiceImpl` (or `services.py` generally) should also expose a way to explain
  a single route rather than only the whole-result aggregate `OptimizationExplanation` — no caller
  need for this has surfaced yet; deferred until one does rather than speculatively added.
- Whether the CLI should support reading `--request`/`--config` from stdin (`-`) as well as a file
  path — §17.3's text only shows file paths; left out of this first cut, callable as a follow-up if
  a real workflow needs it.

## Deviations Discovered During Implementation

Two things this draft did not anticipate, surfaced only by actually wiring the facade end to end
and writing the AC tests — both fixed rather than worked around, per this repo's "deviations noted,
not hidden" convention (see T11's own `LP-008`/`DeskSummary` corrections for precedent):

- **`OptimizationRequest.config_overrides`/`metadata` and `AllocationRecord.explanation_evidence`
  could not be serialized at all.** Their `Field(default_factory=lambda: MappingProxyType({}))`
  default (`domain/requests.py`, `domain/results.py` — the latter from T11) produces a
  `mappingproxy` object pydantic v2 has no serializer for; `_hash_request`'s first call to
  `request.model_dump(mode="json")` raised `PydanticSerializationError` immediately. Fixed with a
  `@field_serializer` on each affected field, converting to a plain `dict` only at the
  serialization boundary — the in-memory immutability the original `MappingProxyType` default was
  chosen for is unaffected; only `model_dump`/`model_dump_json` output changes (from "crashes" to
  "works"). This touches two files (`domain/requests.py`, `domain/results.py`) outside this spec's
  originally-scoped "wrap, don't reinvent" file list, but the bug blocked REQ-003 entirely and
  predates T12 — it simply had no caller until now.
- **`SolverDiagnostics.runtime_seconds` is not deterministic**, even given the identical E1 request
  solved twice back to back: it is `HighsBackend.solve()`'s measured wall-clock time
  (`time.perf_counter()`-based), which genuinely varies run to run while `iterations` and
  `termination_reason` do not. `spec.md`'s `NFR-001`/`NFR-004` and `AC-002`/`AC-011` were corrected
  in place to exclude this one field from the determinism claim, discovered while writing
  `test_optimize_is_deterministic_modulo_identity_fields` (it failed on the first run, with
  `runtime_seconds` as the only differing field).

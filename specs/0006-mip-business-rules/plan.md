# Plan: MIP business rules (Phase 3)

- **Spec:** 0006-mip-business-rules (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code, implemented as described below)
- **Last updated:** 2026-09-05

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Extract two more shared helpers out of `formulation/lp.py` (mirroring T12's own `build_context`
extraction precedent exactly — same-behavior moves, not rewrites), then add one new formulation
module, one new constraints module, one new domain field, and small facade wiring:

1. **`formulation/compiler_support.py`** (new) — `resolve_component()`, `set_route_bounds()`
   (moved out of `lp.py`, made public so `mip.py` doesn't reach into `lp.py`'s private helpers),
   plus new `needs_mip(request) -> bool` and `mip_required_issues(request) -> tuple[ValidationIssue,
   ...]`. `lp.py` and `mip.py` both import from here; neither imports the other's internals.
2. **`formulation/context.py`** — `build_context()` gains two new computed sets on `BuildContext`:
   `activation_route_ids` (routes needing a `z` binary — `all_or_none`, `minimum_active_quantity_
   shares` set, or in a cardinality policy's scope) and `lot_size_route_ids` (routes with
   `lot_size_shares` set). The variable index gains `z`/`n` blocks built from these sets — **empty
   whenever no route/policy qualifies**, which is what keeps this change behavior-preserving for
   every existing LP-only request (NFR-001; `build_variable_index` contributes zero keys for an
   empty scope-id list, so `q`/`inc`/`dec`/`a` positions never shift).
3. **`domain/policies.py`** — `UtilizationPolicy` gains `maximum_active_routes: int | None =
   Field(default=None, ge=0)`. Additive, backward-compatible; no existing test constructs a
   `UtilizationPolicy` with this field, so nothing changes for them.
4. **`components/constraints/mip_rules.py`** (new) — `RouteActivationConstraint` (all-or-none +
   minimum-ticket, sharing one `z` per route), `CardinalityConstraint` (the `sum(z) <=
   maximum_active_routes` row), `LotSizeConstraint` (`q = lot_size * n`).
5. **`formulation/mip.py`** (new) — `compile_mip()`, reusing `formulation.lp.REQUIRED_CONSTRAINTS`/
   `REQUIRED_OBJECTIVES` (imports them from `lp.py` — a one-directional dependency; `mip.py` never
   needs anything `lp.py` doesn't already export) plus the three new components, and sets
   `CompiledProblem.integrality` for every `z`/`n` position.
6. **`formulation/lp.py`** — `compile_lp()` gains one line: raise (via `needs_mip`/
   `mip_required_issues`) before doing anything else, rather than silently ignoring a route/policy
   it cannot honor.
7. **`facade.py`** — `InventoryOptimizer.optimize()` calls `compile_mip` instead of `compile_lp`
   when `needs_mip(request)` is true. No new public parameter; fully automatic.

Nothing in `solvers/highs.py`, `validation/solution_verifier.py`, `reporting/`, `services.py`, or
`cli.py` changes — every one of them is already MIP-aware (see `spec.md`'s Problem & Context) and
is exercised for the first time by this spec's golden tests, not modified by it.

## Dependency graph (why no cycle)

```
formulation/compiler_support.py      (no dependency on lp.py or mip.py)
        ^                    ^
        |                    |
formulation/lp.py  <---  formulation/mip.py   (mip.py imports lp.py's REQUIRED_CONSTRAINTS/
        ^                    ^                  REQUIRED_OBJECTIVES and, as an import side effect,
        |                    |                  the same baseline component registrations --
     facade.py -------------+                   mip.py does not re-import each one itself)
```

## Constraint designs

All three new components live in `components/constraints/mip_rules.py`, registered with
`formulations={Formulation.MIP}` (never contributed by `compile_lp`, which never resolves them).

**`RouteActivationConstraint`** (REQ-001/002), per route in `context.activation_route_ids`:

```python
z = VariableKey("z", route.route_id); q = VariableKey("q", route.route_id)
builder.set_variable_bounds(z, lower=0.0, upper=1.0)

if route.all_or_none:
    row = builder.add_row("all_or_none", route.route_id, lower=0.0, upper=0.0)
    builder.add_row_coefficient(row, q, 1.0)
    builder.add_row_coefficient(row, z, -route.maximum_quantity_shares)
    # q - max*z = 0  =>  q is exactly 0 or exactly max. Fully determines the link; nothing else
    # needed for this route.
else:
    if route.minimum_active_quantity_shares is not None:
        lower_row = builder.add_row("min_ticket", route.route_id, lower=0.0, upper=math.inf)
        builder.add_row_coefficient(lower_row, q, 1.0)
        builder.add_row_coefficient(lower_row, z, -route.minimum_active_quantity_shares)
        # q - min_ticket*z >= 0  =>  q >= min_ticket when active
    upper_row = builder.add_row("activation_upper", route.route_id, lower=-math.inf, upper=0.0)
    builder.add_row_coefficient(upper_row, q, 1.0)
    builder.add_row_coefficient(upper_row, z, -route.maximum_quantity_shares)
    # q - max*z <= 0  =>  q = 0 when inactive; needed for min-ticket routes explicitly, and for
    # cardinality-only routes (no all_or_none, no min-ticket) as their *only* q-to-z link.
```

**`CardinalityConstraint`** (REQ-004), per `UtilizationPolicy` with `maximum_active_routes` set,
scoped by the same `inventory_pool_id`/`security_id` matching `UtilizationCapConstraint`/
`ReserveBufferConstraint` already use (`components/constraints/utilization.py::_policy_applies`,
imported directly — both modules are siblings inside `components.constraints`, not a
cross-layer reach-in):

```python
matching_routes = [route for inventory in context.request.inventory
                    if _policy_applies(policy, inventory)
                    for route in context.routes_by_inventory.get(inventory.inventory_id, ())]
row = builder.add_row("cardinality", policy.policy_id, lower=-math.inf, upper=float(policy.maximum_active_routes))
for route in matching_routes:
    builder.add_row_coefficient(row, VariableKey("z", route.route_id), 1.0)
```

**`LotSizeConstraint`** (REQ-003), per route with `lot_size_shares` set:

```python
n = VariableKey("n", route.route_id); q = VariableKey("q", route.route_id)
row = builder.add_row("lot_size", route.route_id, lower=0.0, upper=0.0)
builder.add_row_coefficient(row, q, 1.0)
builder.add_row_coefficient(row, n, -route.lot_size_shares)
# q - lot_size*n = 0
max_n = math.floor(route.maximum_quantity_shares / route.lot_size_shares + 1e-9)  # float-division guard
builder.set_variable_bounds(n, lower=0.0, upper=float(max_n))
```

## `compile_mip`

```python
def compile_mip(request: OptimizationRequest, config: InventoryOptimizerConfig) -> CompiledProblem:
    context = build_context(request, config)
    builder = SparseBuilder(context.variable_index)
    for route in request.routes:
        set_route_bounds(builder, route)

    all_names = (*REQUIRED_CONSTRAINTS, *REQUIRED_OBJECTIVES, *MIP_CONSTRAINTS, *config.desk.enabled_components)
    component_names = list(dict.fromkeys(all_names))
    resolved = [resolve_component(name) for name in component_names]
    instances = [(kind, registration, registration.component_class()) for kind, registration in resolved]

    issues = [issue for _, _, instance in instances for issue in instance.validate(context)]
    if issues:
        raise InputValidationError(tuple(issues))
    for kind, _, instance in instances:
        if kind is ComponentKind.CONSTRAINT:
            instance.contribute(context, builder)
    for kind, _, instance in instances:
        if kind is ComponentKind.OBJECTIVE:
            instance.contribute(context, builder)

    manifest = tuple(registration for _, registration, _ in instances)
    integrality = np.zeros(len(context.variable_index), dtype=np.int8)
    for route_id in context.activation_route_ids:
        integrality[context.variable_index.position(VariableKey("z", route_id))] = 1
    for route_id in context.lot_size_route_ids:
        integrality[context.variable_index.position(VariableKey("n", route_id))] = 1

    return builder.build(
        formulation=Formulation.MIP, objective_sense=ObjectiveSense.MAXIMIZE,
        integrality=integrality, manifest=manifest,
    )
```

`MIP_CONSTRAINTS = ("route_activation", "cardinality", "lot_size")`.

## `compile_lp`'s new rejection (REQ-006)

```python
def compile_lp(request: OptimizationRequest, config: InventoryOptimizerConfig) -> CompiledProblem:
    if needs_mip(request):
        raise InputValidationError(mip_required_issues(request))
    context = build_context(request, config)
    ...  # unchanged from here down, using the same set_route_bounds/resolve_component now
         # imported from compiler_support instead of defined locally
```

`mip_required_issues` names every offending route/policy individually (not just the first), one
`ValidationIssue` per field per route/policy — consistent with `Section 9.8`'s "aggregate every
issue" convention this repo's other validation already follows (`validation.reconciliation`,
`validation.input_validation`).

## Facade wiring (REQ-007)

```python
# facade.py, inside InventoryOptimizer.optimize()
problem = compile_mip(request, self._config) if needs_mip(request) else compile_lp(request, self._config)
```

No new public parameter on `optimize()`; fully automatic, matching `spec.md`'s Goals.

## Constitution Check

| Principle | Upheld? | Notes |
| --- | --- | --- |
| P4 Correct by construction | yes | `compile_lp` now fails closed instead of silently ignoring a hard discrete requirement (the specific gap this spec exists to close). `compile_mip` reuses every baseline component unchanged rather than re-implementing economics logic for a second time. |
| P5 Reversibility | yes | `formulation/compiler_support.py`, `formulation/mip.py`, `components/constraints/mip_rules.py` are new, additive modules. `formulation/context.py`'s extension is additive (new fields, new variable blocks that are empty by default). `formulation/lp.py`'s only behavior change is the new rejection — a deliberate, documented one (RISK-001), not an accidental side effect. |
| P6 Observability | yes | `compile_lp`'s rejection names every offending route/policy field individually, not a generic "MIP required" message. |
| P9 Security & data | yes | No secrets; only structural/numeric domain fields are involved. |

## Traceability Matrix

| Requirement | Design element | Tasks |
| --- | --- | --- |
| REQ-001 | `components/constraints/mip_rules.py::RouteActivationConstraint` (all_or_none branch) | T-003 |
| REQ-002 | `components/constraints/mip_rules.py::RouteActivationConstraint` (min-ticket branch) | T-003 |
| REQ-003 | `components/constraints/mip_rules.py::LotSizeConstraint` | T-003 |
| REQ-004 | `domain/policies.py::UtilizationPolicy.maximum_active_routes`; `mip_rules.py::CardinalityConstraint` | T-002, T-003 |
| REQ-005 | `formulation/mip.py::compile_mip` | T-004 |
| REQ-006 | `formulation/compiler_support.py::needs_mip`/`mip_required_issues`; `formulation/lp.py::compile_lp` | T-001, T-005 |
| REQ-007 | `facade.py::InventoryOptimizer.optimize` | T-006 |
| REQ-008 | `tests/golden/test_mip_business_rules.py` (one test per trigger) | T-007 |
| REQ-009 | `tests/golden/test_mip_business_rules.py::test_integrality_violation_caught_on_real_mip` | T-007 |
| NFR-001 | `formulation/context.py`'s empty-block behavior; existing E1/E2/E3 tests unchanged | T-002, T-007 |
| NFR-002 | `mip_required_issues` covers all four trigger conditions exhaustively | T-001 |
| NFR-003 | `tests/golden/test_mip_business_rules.py::test_no_shadow_prices_for_real_mip_solve` | T-007 |

## Trade-offs & Alternatives

| Decision | Chosen | Rejected alternative | Why |
| --- | --- | --- | --- |
| `z`/`n` variable-block placement | Always computed in `build_context()`, empty when unused | A separate MIP-only context/variable-index built inside `compile_mip` alone | One `build_context()` keeps `compile_lp`/`compile_mip`/the facade's `VerifiedSolution` construction (T11/T12) all seeing the same variable index shape logic; empty blocks contribute zero positions, so LP-only requests are provably unaffected (NFR-001). |
| `compile_lp`'s new rejection | Raise `InputValidationError` before compiling anything | Silently ignore the fields (today's actual behavior) | RISK-001 — silently ignoring a discrete requirement is the exact failure mode P4 forbids; a wrong silent LP relaxation is worse than a clear, actionable rejection. |
| Cardinality's `z_j` scope | Every route in the policy's matched inventory pool/security | Only routes that *also* have `all_or_none`/min-ticket set | §14.1 defines cardinality over "active routes" generally, not only ones with another MIP flag — restricting scope would silently under-enforce the cardinality limit for routes with no other trigger. |
| Route-activation vs. lot-size composition | Independent; compose naturally with no special-case code when both apply to one route | Add explicit joint-feasibility pre-checks (e.g. reject if `maximum_quantity_shares` isn't a multiple of `lot_size_shares`) | Deferred per `spec.md`'s Non-Goals (RISK-003) — a friendlier diagnostic for the incompatible-combination case is a real, separate follow-up, not required for this spec's four triggers to work correctly in isolation. |

## Validation Strategy

- `tests/golden/test_mip_business_rules.py` — one test per trigger (AC-001 through AC-004), the
  integrality-corruption test (AC-008), and the no-shadow-prices test (AC-009), all solving a real
  compiled MIP via `InventoryOptimizer.optimize()` end to end.
- `tests/unit/test_mip_compiler.py` — `compile_lp`'s new rejection (AC-006), `compile_mip`'s
  variable/row shape for each trigger in isolation (mirroring `test_lp_compiler.py`'s existing
  per-component style), and `needs_mip`'s detection logic.
- Existing `tests/golden/test_e1_scarce_name_allocation.py`, `test_e2_fee_elasticity_shock.py`,
  `test_e3_sale_and_recall_scenario.py`, and every `tests/unit/test_lp_compiler.py` test must
  continue to pass unchanged (AC-005) — the plainest possible proof of NFR-001.
- No new benchmark test in this spec; `specs/0005-test-hardening/tasks.md`'s Follow-ups already
  notes MIP-scale benchmarking as future work (RISK-002).

## Rollout, Observability & Rollback

Additive modules plus one new domain field and one behavior change (`compile_lp`'s rejection,
deliberate and documented). Rollback is a revert of the new files, the `UtilizationPolicy` field,
and the `lp.py`/`facade.py` diffs. Observability is the rejection's per-field `ValidationIssue`
list and the test suite; `specs/spec002/TRACEABILITY.md`'s `LP-009` row gains an evidence pointer
for the MIP portion (done — see the Task List's traceability-update task).

## Open Questions

- Whether `CompiledProblem.formulation` (already a field, already `MIP` for these requests) should
  be surfaced anywhere in `OptimizationResult` for observability (spec.md's Open Questions) — not
  resolved here; a pre-existing, separate small gap, not created by this spec.

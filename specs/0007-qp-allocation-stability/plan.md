# Plan: QP allocation-stability penalty (Phase 4)

- **Spec:** 0007-qp-allocation-stability (`spec.md`)
- **Status:** Approved
- **Author:** Joshua Lutkemuller, CFA (drafted by Claude Code, implemented as described below)
- **Last updated:** 2026-09-05

> HOW. This plan requires an approved `spec.md`. Every requirement in the spec
> must appear in the traceability matrix below.

## Approach

Mirror `specs/0006-mip-business-rules/`'s own compiler pattern almost exactly: a new
`formulation.qp.compile_qp` reuses `formulation.lp`'s `REQUIRED_CONSTRAINTS`/`REQUIRED_OBJECTIVES`
(unchanged), adds one new objective component, resolves/validates/contributes in the same fixed
order, and returns a `CompiledProblem` tagged `Formulation.QP`. No new `BuildContext` fields and no
new variable kinds are needed — the term is expressed entirely via the existing `q`/`inc`/`dec`
variables (T08), unlike Phase 3's new `z`/`n` blocks.

### The objective term

For route `j` with current quantity `q0_j` and configured coefficient `lambda >= 0`, the term is:

```text
-(lambda/2) * (q_j - q0_j)^2
```

The transition identity (`q_j = q0_j + inc_j - dec_j`, already enforced by
`TransitionIdentityConstraint`) means `q_j - q0_j = inc_j - dec_j` exactly, so the term expands to:

```text
-(lambda/2)*inc_j^2 + lambda*inc_j*dec_j - (lambda/2)*dec_j^2
```

a 2x2 Hessian block per route, `[[lambda, -lambda], [-lambda, lambda]]` (eigenvalues `0`,
`2*lambda`, positive semidefinite whenever `lambda >= 0`). This is exactly zero when
`inc_j = dec_j = 0` (the unchanged baseline), needing no linear term and no constant/offset —
`CompiledProblem` gains no new field for this term, unlike an earlier design (rejected below) that
penalized `q_j` directly.

### Sign convention (`formulation.qp_support`)

`CompiledProblem.quadratic_objective` (`Q`) is always validated positive semidefinite (Section
14.2's literal text) and represents *penalty intensity*, independent of `objective_sense`. Its
contribution to the declared sense's optimized value is `-0.5 * x^T Q x` when maximizing (this
engine's objective is always revenue, maximized — a concave penalty that discourages deviation) or
`+0.5 * x^T Q x` when minimizing (the equivalent convex cost, for a possible future minimize-sense
formulation). `signed_hessian(matrix, sense)`/`signed_quadratic_term(matrix, primal, sense)` apply
this once, shared by `solvers.highs` (solve-time Hessian construction) and
`validation.solution_verifier` (verify-time reconstruction), so the two cannot drift apart.

Empirically verified against HiGHS directly (`objective = 0.5*x^T H x + c^T x` in the *declared*
sense, not just minimize): a 1-variable `minimize 0.5x^2 - x` case with `H=[1]` gave `x=1`,
`obj=-0.5` as expected; a 1-variable `maximize -0.5x^2 + x` case with `H=[-1]` gave `x=1`,
`obj=0.5` as expected — confirming the sign-flip-for-maximize convention is exactly right.

### Why not penalize `q_j` directly (rejected alternative)

The mathematically simpler alternative — a diagonal Hessian entry directly on `q_j`, `Q[j,j] =
lambda`, plus a linear term `lambda*q0_j` on `q_j` — needs a constant `-(lambda/2)*q0_j^2` to make
the *reported* objective exactly zero at baseline (`q_j = q0_j`). No `CompiledProblem` field exists
for a scalar objective offset (confirmed: no field in the Phase 0A sketch, `HighsBackend` hardcodes
`lp.offset_ = 0.0`), so this alternative would have needed a new field purely to sidestep dropping
a constant. Empirically, this alternative Hessian placement showed the *identical* HiGHS QP solver
stall (see below) as the `inc`/`dec` formulation, at the identical coefficient threshold — proving
the instability is unrelated to which variables the Hessian touches, so there was no actual
numerical-robustness reason to prefer it. The `inc`/`dec` formulation was kept for being
architecturally simpler (no new field) with identical numerical behavior once scaled.

### The empirically-discovered scaling requirement

Reconstructing the compiled 4-variable QP model directly against the pinned `highspy` (1.15.1)
`Highs()` API (bypassing this repo's compiler) reproduced a genuine solver stall: for the concrete
case (`q0=50`, bounds `[0,100]`, fee coefficient `0.01`, `lambda` in `{0.0002, 0.00025, 0.0003,
0.00039, 0.0004, 0.00045}`), HiGHS's "QP ASM" (active-set method) iterated into the millions
without converging, stuck at a *suboptimal* vertex (confirmed suboptimal: the true unconstrained
optimum `q=75` gives objective `0.625`, but the stalled run reports `0.5`, the value *at the
boundary* `q=100`). At `lambda=0.0005` and above, or `lambda=0.0001` and below, the identical model
solved instantly to `OPTIMAL`. This is a narrow, coefficient-range-dependent conditioning cliff, not
a structural cycling issue tied to any particular variable choice (reproduced identically whether
the Hessian sits on `inc`/`dec` or on `q` directly, and independent of `dec`'s own bound).

Uniformly rescaling the *entire* objective (linear cost and Hessian together) by a single positive
constant resolved every reproduced case instantly to `OPTIMAL`, with the correct analytical answer
(verified: `obj_scale=10` and above all converged correctly for the `lambda=0.0004` case). This is
an exact transformation (multiplying a maximized objective by a positive constant never changes its
argmax), so it changes nothing about correctness — only about whether the solver's active-set
method can actually find the optimum in practice.

**Scaling rule:** `formulation.qp.compile_qp` computes `objective_scale_usd = 1.0 /
max(abs(Q.data))` from the fully-assembled quadratic matrix (so the Hessian's largest-magnitude
entry becomes exactly `1.0`) and attaches it via `ScalingMetadata(applied=True,
objective_scale_usd=...)`. `CompiledProblem.linear_objective`/`quadratic_objective` themselves are
**not** rescaled — they stay in true USD units. Only `solvers.highs.HighsBackend.solve()` reads
`problem.scaling` and applies the factor to its own HiGHS-facing translation
(`col_cost_`/Hessian), then divides the solved objective and both `dual`/`reduced_costs` back down
by the same factor before returning a `SolverResult` — every other subsystem (`validation.
solution_verifier`, `reporting.attribution`, `reporting.shadow_prices`) needs zero changes for
scaling awareness beyond REQ-007's quadratic-term reconstruction itself, since they only ever see
true, unscaled numbers. Verified empirically end to end (facade solve, `lambda=0.0004`): duals
report at the fee-coefficient's own order of magnitude (`~0.01`), not inflated by the ~2500x
internal scale factor.

## Dependency graph (why no cycle)

`formulation.qp` imports `formulation.lp` (for `REQUIRED_CONSTRAINTS`/`REQUIRED_OBJECTIVES`, plus
the baseline components' registration side effect) and `components.objective_terms.
allocation_stability` (for its own registration side effect) — the same one-directional shape
`formulation.mip` already established relative to `formulation.lp`. `formulation.qp_support` sits
below both `formulation.qp` and `solvers.highs`/`validation.solution_verifier`, importing only
`domain.enums`/`exceptions`/`formulation.compiled` — no cycle, since none of those import back up.
`formulation.compiler_support` gains `needs_qp`/`qp_required_issues`/`miqp_conflict_issues`
alongside the existing `needs_mip`/`mip_required_issues`, and its `resolve_component` gains a
required `formulation=` keyword — `formulation.lp`/`formulation.mip`/`formulation.qp` all update
their one call site each.

## `compile_qp`

```python
def compile_qp(request, config) -> CompiledProblem:
    if needs_mip(request):
        raise InputValidationError(miqp_conflict_issues())
    context = build_context(request, config)
    builder = SparseBuilder(context.variable_index)
    for route in request.routes:
        set_route_bounds(builder, route)
    # REQUIRED_CONSTRAINTS + REQUIRED_OBJECTIVES (from formulation.lp) + ("allocation_stability",)
    # + config.desk.enabled_components, resolved with formulation=Formulation.QP
    ...
    problem = builder.build(formulation=Formulation.QP, objective_sense=ObjectiveSense.MAXIMIZE,
                             manifest=manifest)
    if problem.quadratic_objective is not None:
        raise_if_not_psd(problem.quadratic_objective)          # REQ-002
        problem = dataclasses.replace(problem, scaling=_objective_scaling(...))  # REQ-008
    return problem
```

`SparseBuilder` gains `add_quadratic_objective_coefficient(row_key, col_key, value)`: a diagonal
entry when `row_key == col_key`, or a symmetric pair (`Q[i,j] = Q[j,i] += value`) otherwise — COO
accumulation, converted once at `build()` time exactly like the constraint matrix already is
(duplicate entries summed by scipy's COO-to-CSR conversion, the same convention
`add_row_coefficient` already relies on). `build()`'s previously-unused external
`quadratic_objective` parameter (never passed by any existing caller — confirmed by inspection) is
removed in favor of this internal accumulation, matching how `constraint_matrix` already works.

## PSD validation (`formulation.qp_support.validate_psd`)

Checks the fully-assembled matrix's smallest eigenvalue (not any one component's contribution in
isolation, so a future second QP term whose *sum* with this one is not PSD still gets caught):
dense `numpy.linalg.eigvalsh` for matrices at or below 64 columns (covers every realistic test
fixture), `scipy.sparse.linalg.eigsh(..., which="SA")` above that threshold (avoids densifying a
large, mostly-diagonal matrix at Core-desk scale). Verified directly against hand-built matrices on
both code paths: a diagonal PSD matrix and an indefinite `[[0,2],[2,0]]` 2x2 example (dense path);
an 80x80 mostly-identity matrix with one bad 2x2 block (sparse `eigsh` path) — both paths correctly
distinguish PSD from non-PSD.

## `compile_lp`'s new rejection (REQ-003) and the MIQP conflict (REQ-004)

`compile_lp` aggregates `mip_required_issues(request) + qp_required_issues(config)` in one pass
(Section 9.8's "aggregate every issue" convention) before compiling anything — extending, not
replacing, `0006`'s existing `MIP_REQUIRED` check. `compile_mip` gains a new pre-flight check
(`if needs_qp(config): raise InputValidationError(miqp_conflict_issues())`) fired *before* any
building work, symmetric with `compile_qp`'s own `if needs_mip(request): raise ...` check — both
share one message (`MIQP_UNSUPPORTED`), so the two compilers cannot describe the same conflict
inconsistently.

## Facade wiring (REQ-005)

```python
if needs_mip(request):
    problem = compile_mip(request, self._config)
elif needs_qp(self._config):
    problem = compile_qp(request, self._config)
else:
    problem = compile_lp(request, self._config)
```

When both triggers are present, `compile_mip` runs first (per this ordering) and raises the
`MIQP_UNSUPPORTED` error itself — no redundant facade-level conflict check needed.

## `resolve_component`'s formulation check (REQ-010)

```python
def resolve_component(name, *, formulation, version=COMPONENT_VERSION):
    for kind in (CONSTRAINT, OBJECTIVE):
        try:
            registration = default_registry.get(kind, name, version)
        except RegistrationError:
            continue
        if formulation not in registration.metadata.get("formulations", frozenset()):
            raise ConfigurationError(...)
        return kind, registration
    raise RegistrationError(...)
```

Verified every existing baseline/MIP component's `formulations=` set already declares its correct,
complete scope (`inventory_balance`/`transition_identity`/`utilization_cap`/`reserve_buffer`/
`demand`/`counterparty`/`fee_revenue`/`transition_cost` all declare `{LP, MIP, QP}`; `mip_rules`'s
three components declare exactly `{MIP}`) — so this check is purely additive for every existing
`compile_lp`/`compile_mip` call, confirmed via the full 172-test suite passing unchanged.

## Constitution Check

- Spec is source of truth: `spec.md` written and approved before this plan/implementation.
- Traceable: every REQ/NFR below maps to file(s) and test(s).
- Definition of Done: each AC has a named test.
- Correct by construction: PSD validation, MIQP-conflict rejection, and the fail-closed
  `compile_lp` rejection all reject invalid/unsupported states outright rather than approximating.
- No silent trade-offs: the scaling rule, the `q`-vs-`inc`/`dec` design choice, and every deferred
  §14.2 term are recorded above and in `spec.md`'s Non-Goals/Risks, not silently decided.

## Traceability Matrix

| ID | Evidence | Task |
| --- | --- | --- |
| REQ-001 | `config/models.py::ObjectiveConfig`; `components/objective_terms/allocation_stability.py` | T-001, T-002 |
| REQ-002 | `formulation/qp.py::compile_qp`; `formulation/qp_support.py::validate_psd` | T-003, T-004 |
| REQ-003 | `formulation/lp.py::compile_lp`; `formulation/compiler_support.py::qp_required_issues` | T-005 |
| REQ-004 | `formulation/compiler_support.py::miqp_conflict_issues`; `formulation/mip.py`, `formulation/qp.py` | T-005, T-004 |
| REQ-005 | `facade.py::InventoryOptimizer.optimize` | T-006 |
| REQ-006 | `solvers/highs.py::HighsBackend`, `_build_highs_hessian` | T-007 |
| REQ-007 | `validation/solution_verifier.py` | T-008 |
| REQ-008 | `formulation/qp.py::_objective_scaling`; `solvers/highs.py`'s scale-factor handling | T-004, T-007 |
| REQ-009 | `tests/golden/test_qp_allocation_stability.py`, `tests/unit/test_qp_compiler.py`, `tests/unit/test_qp_support.py` | T-009 |
| REQ-010 | `formulation/compiler_support.py::resolve_component` | T-003 |
| NFR-001 | Full existing 172-test suite, rerun unchanged | T-009 |
| NFR-002 | `tests/unit/test_highs_backend.py::test_backend_is_registered_with_lp_mip_and_qp_capabilities` | T-007 |
| NFR-003 | `validation/solution_verifier.py` unchanged beyond REQ-007; `tests/golden/test_qp_allocation_stability.py`'s attribution/shadow-price assertions | T-008, T-009 |

## Trade-offs & Alternatives

- **`q`-direct Hessian + offset field vs. `inc`/`dec` block (chosen)** — see "Why not penalize
  `q_j` directly" above. Chosen for zero `CompiledProblem` shape change with identical numerical
  behavior once scaled.
- **Scaling applied to `CompiledProblem`'s own arrays vs. solver-adapter-only (chosen)** —
  rescaling `CompiledProblem.linear_objective`/`quadratic_objective` themselves would have required
  `validation.solution_verifier`/`reporting.attribution` to become scale-aware (comparing against
  `objective_value_scaled` instead of `_unscaled`, threading a scale factor through every consumer
  of `problem.linear_objective`). Confining scaling to `solvers.highs` alone keeps every other
  already-tested subsystem's logic completely unchanged — the correct trade-off given no other
  subsystem has any actual need to see scaled numbers.
- **A general auto-scaling pass for every formulation vs. QP-only (chosen)** — LP/MIP have no
  reproduced numerical issue; adding scaling there would be speculative engineering against a
  problem that does not exist for those paths.

## Validation Strategy

- Golden, end-to-end tests via the facade for AC-001 through AC-003 (a fee/penalty sweep proving
  the closed-form optimum), AC-007 (attribution), AC-008 (shadow prices).
- Direct unit tests for `compile_lp`/`compile_mip`/`compile_qp`'s rejections (AC-004, AC-005),
  `validate_psd` (AC-006), `needs_qp`, and `compile_qp`'s exact row/variable/scaling shape,
  mirroring `test_mip_compiler.py`'s own style.
- A `@pytest.mark.slow` scale/performance test (AC-010, Plan Phase 4 item 3's "scaling tests"),
  matching `specs/0005-test-hardening/`'s Core-desk-benchmark precedent, excluded from the default
  run.
- Full suite rerun (AC-009/NFR-001) after every incremental change, confirming zero regressions
  throughout implementation (each step verified live during this session, not only at the end).

## Rollout, Observability & Rollback

Additive modules plus one new config section and one behavior change each in `compile_lp`/
`compile_mip` (both fail-closed rejections, deliberate and documented). Rollback is a revert of the
new files, the `ObjectiveConfig` section, and the `lp.py`/`mip.py`/`facade.py`/`solvers/highs.py`/
`validation/solution_verifier.py` diffs. Observability is the rejection issues' structured codes,
the attribution breakdown's `allocation_stability` entry (RISK-002), and the test suite;
`specs/spec002/TRACEABILITY.md`'s `LP-009` row gains further evidence for the QP portion (PWL/NLP
stay `SPECIFIED`).

## Open Questions

- Whether a future second QP term should share this spec's scaling rule unchanged — deferred until
  one exists (`spec.md`'s own Open Question).
- Whether `config.formulation.mode` should ever become a manual override rather than staying
  unused — out of scope here, matching `0006`'s own precedent of leaving it untouched.

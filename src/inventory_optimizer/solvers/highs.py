"""HiGHS LP/MIP backend adapter (T09; Section 16.4).

The sole owner of ``highspy`` imports in this package. Registers as the ``"highs"`` solver
backend (Section 15) and implements ``ports.solver.SolverBackend``.

Capability scope matches Section 16.4's staged acceptance: LP and linear MIP now; continuous QP
is deferred to T18 pending its own pinned-version capability test, so it is not claimed here.
"""

from __future__ import annotations

import time

import highspy
import numpy as np
from numpy.typing import NDArray

from inventory_optimizer.components.decorators import solver_backend
from inventory_optimizer.domain.enums import Capability, SolverStatus
from inventory_optimizer.formulation.compiled import CompiledProblem
from inventory_optimizer.ports.solver import SolverOptions, SolverResult, SolverWarmStart

_BACKEND_VERSION = (
    f"{highspy.HIGHS_VERSION_MAJOR}.{highspy.HIGHS_VERSION_MINOR}.{highspy.HIGHS_VERSION_PATCH}"
)

_LIMIT_STATUSES = frozenset(
    {
        highspy.HighsModelStatus.kTimeLimit,
        highspy.HighsModelStatus.kIterationLimit,
        highspy.HighsModelStatus.kSolutionLimit,
        highspy.HighsModelStatus.kObjectiveBound,
        highspy.HighsModelStatus.kObjectiveTarget,
    }
)
_INVALID_MODEL_STATUSES = frozenset(
    {
        highspy.HighsModelStatus.kModelEmpty,
        highspy.HighsModelStatus.kModelError,
        highspy.HighsModelStatus.kLoadError,
    }
)
_SOLVER_ERROR_STATUSES = frozenset(
    {
        highspy.HighsModelStatus.kPresolveError,
        highspy.HighsModelStatus.kSolveError,
        highspy.HighsModelStatus.kPostsolveError,
        highspy.HighsModelStatus.kMemoryLimit,
        highspy.HighsModelStatus.kNotset,
        highspy.HighsModelStatus.kUnknown,
    }
)
_INTERRUPT_STATUSES = frozenset(
    {
        highspy.HighsModelStatus.kInterrupt,
        highspy.HighsModelStatus.kHighsInterrupt,  # type: ignore[attr-defined]
    }
)


def _normalize_status(
    model_status: highspy.HighsModelStatus, info: highspy.HighsInfo
) -> SolverStatus:
    if model_status == highspy.HighsModelStatus.kOptimal:
        return SolverStatus.OPTIMAL
    if model_status == highspy.HighsModelStatus.kInfeasible:
        return SolverStatus.INFEASIBLE
    if model_status == highspy.HighsModelStatus.kUnbounded:
        return SolverStatus.UNBOUNDED
    if model_status == highspy.HighsModelStatus.kUnboundedOrInfeasible:
        return SolverStatus.INFEASIBLE_OR_UNBOUNDED
    if model_status in _LIMIT_STATUSES:
        if info.primal_solution_status == highspy.kSolutionStatusFeasible:
            return SolverStatus.FEASIBLE_LIMIT
        # A limit was hit with no proven-feasible incumbent: neither optimal, nor a reportable
        # incumbent, nor a proven infeasible/unbounded claim. Section 16.3 does not name this
        # case explicitly; SOLVER_ERROR is the closest fit among the nine normalized statuses and
        # -- unlike FEASIBLE_LIMIT -- never implies an incumbent exists.
        return SolverStatus.SOLVER_ERROR
    if model_status in _INVALID_MODEL_STATUSES:
        return SolverStatus.INVALID_MODEL
    if model_status in _INTERRUPT_STATUSES:
        return SolverStatus.INTERRUPTED
    if model_status in _SOLVER_ERROR_STATUSES:
        return SolverStatus.SOLVER_ERROR
    return SolverStatus.SOLVER_ERROR


def _build_highs_lp(problem: CompiledProblem) -> highspy.HighsLp:
    lp = highspy.HighsLp()
    lp.num_col_ = len(problem.variable_index)
    lp.num_row_ = len(problem.row_index)
    lp.col_cost_ = problem.linear_objective
    lp.col_lower_ = problem.variable_lower
    lp.col_upper_ = problem.variable_upper
    lp.row_lower_ = problem.row_lower
    lp.row_upper_ = problem.row_upper
    lp.offset_ = 0.0
    lp.sense_ = (
        highspy.ObjSense.kMaximize
        if problem.objective_sense.value == "maximize"
        else highspy.ObjSense.kMinimize
    )

    csr = problem.constraint_matrix
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.num_col_ = lp.num_col_
    lp.a_matrix_.num_row_ = lp.num_row_
    lp.a_matrix_.start_ = csr.indptr.tolist()
    lp.a_matrix_.index_ = csr.indices.tolist()
    lp.a_matrix_.value_ = csr.data.tolist()

    if np.any(problem.integrality != 0):
        lp.integrality_ = [
            highspy.HighsVarType.kInteger if flag else highspy.HighsVarType.kContinuous
            for flag in problem.integrality
        ]
    return lp


_ALLOWED_OPTIONS = ("time_limit", "mip_rel_gap", "threads", "random_seed")


def _apply_options(highs: highspy.Highs, options: SolverOptions) -> None:
    highs.setOptionValue("output_flag", options.log_level == "debug")
    if options.time_limit_seconds is not None:
        highs.setOptionValue("time_limit", options.time_limit_seconds)
    if options.relative_gap is not None:
        highs.setOptionValue("mip_rel_gap", options.relative_gap)
    if options.threads is not None:
        highs.setOptionValue("threads", options.threads)
    if options.seed is not None:
        highs.setOptionValue("random_seed", options.seed)


@solver_backend(name="highs", capabilities={Capability.LP, Capability.MIP})
class HighsBackend:
    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.LP, Capability.MIP})

    def solve(
        self,
        problem: CompiledProblem,
        options: SolverOptions,
        warm_start: SolverWarmStart | None = None,
    ) -> SolverResult:
        highs = highspy.Highs()
        _apply_options(highs, options)

        pass_status = highs.passModel(_build_highs_lp(problem))
        if pass_status == highspy.HighsStatus.kError:
            return SolverResult(
                status=SolverStatus.INVALID_MODEL,
                primal=None,
                dual=None,
                reduced_costs=None,
                objective_value_scaled=None,
                objective_value_unscaled=None,
                best_bound=None,
                relative_gap=None,
                runtime_seconds=0.0,
                iterations=None,
                nodes=None,
                termination_reason="passModel returned HighsStatus.kError",
                backend_name="highs",
                backend_version=_BACKEND_VERSION,
                effective_options=options,
                native_status="kError",
            )

        if warm_start is not None and warm_start.primal is not None:
            seeded = highspy.HighsSolution()
            seeded.col_value = warm_start.primal.tolist()
            seeded.value_valid = True
            highs.setSolution(seeded)

        start = time.perf_counter()
        highs.run()
        runtime_seconds = time.perf_counter() - start

        model_status = highs.getModelStatus()
        info = highs.getInfo()
        solution = highs.getSolution()
        status = _normalize_status(model_status, info)

        has_integer_variables = bool(np.any(problem.integrality != 0))
        primal: NDArray[np.float64] | None = (
            np.array(solution.col_value, dtype=np.float64) if solution.value_valid else None
        )
        dual: NDArray[np.float64] | None = (
            np.array(solution.row_dual, dtype=np.float64)
            if solution.dual_valid and not has_integer_variables
            else None
        )
        reduced_costs: NDArray[np.float64] | None = (
            np.array(solution.col_dual, dtype=np.float64)
            if solution.dual_valid and not has_integer_variables
            else None
        )
        objective = info.objective_function_value if solution.value_valid else None

        return SolverResult(
            status=status,
            primal=primal,
            dual=dual,
            reduced_costs=reduced_costs,
            objective_value_scaled=objective,
            objective_value_unscaled=objective,
            best_bound=info.mip_dual_bound if has_integer_variables else None,
            relative_gap=info.mip_gap if has_integer_variables else None,
            runtime_seconds=runtime_seconds,
            iterations=info.simplex_iteration_count or None,
            nodes=info.mip_node_count if has_integer_variables else None,
            termination_reason=highs.modelStatusToString(model_status),
            backend_name="highs",
            backend_version=_BACKEND_VERSION,
            effective_options=options,
            native_status=model_status.name,
        )

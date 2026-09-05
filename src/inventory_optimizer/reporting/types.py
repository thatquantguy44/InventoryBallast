"""Shared reporting contracts (T11; Section 18): ``VerifiedSolution`` is the single bundle every
``reporting/`` module and every ``ObjectiveComponent.attribute()`` reads from -- the request/build
context, the compiled problem, the raw solver result, and T10's independent ``VerificationReport``,
plus a reversible primal lookup so no caller re-derives ``VariableIndex`` positions by hand.

``components/interfaces.py``'s ``ObjectiveComponent.attribute(self, solution: object) -> object``
named these two types as "not introduced yet"; this module introduces them.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from inventory_optimizer.domain.enums import ReasonCode
from inventory_optimizer.formulation.compiled import CompiledProblem
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.indexes import RowKey, VariableKey
from inventory_optimizer.ports.solver import SolverResult
from inventory_optimizer.validation.solution_verifier import VerificationReport


@dataclass(frozen=True, slots=True)
class VerifiedSolution:
    """One solved, independently-verified request. ``context`` carries the same domain/config data
    every ``contribute()`` call already received, so ``attribute()`` can recompute its formula from
    domain fields rather than merely echo back the compiled coefficient (Section 18.2: "recomputes
    ... from domain allocations")."""

    context: BuildContext
    problem: CompiledProblem
    result: SolverResult
    verification: VerificationReport

    def primal_at(self, key: VariableKey) -> float:
        """0.0 when there is no primal, or the key is not part of this problem -- never raises, so
        callers can evaluate a formula across every route/inventory record without first checking
        which variable kinds a given compile happened to include."""
        if self.result.primal is None:
            return 0.0
        if key not in self.problem.variable_index:
            return 0.0
        return float(self.result.primal[self.problem.variable_index.position(key)])


@dataclass(frozen=True, slots=True)
class ObjectiveAttribution:
    """One objective component's independently-recomputed unscaled USD value (Section 18.2)."""

    component_name: str
    component_version: str
    unscaled_value_usd: float
    baseline_value_usd: float
    delta_usd: float


@dataclass(frozen=True, slots=True)
class RouteExplanation:
    """Structured decision explanation for one route with a material allocation change (Section
    18.3). ``evidence`` is machine-readable and cited by the reason codes it supports; a renderer
    may turn this into prose later, but correctness never depends on that step."""

    route_id: str
    reason_codes: tuple[ReasonCode, ...]
    evidence: Mapping[str, float | str]


@dataclass(frozen=True, slots=True)
class ShadowPriceEntry:
    """One row's LP dual, labeled with objective scale and sign convention (Section 18.4). Never
    constructed for a MIP solve or a failed verification -- see ``reporting.shadow_prices``."""

    row_key: RowKey
    dual_value: float
    objective_scale_usd: float
    sign_convention: str

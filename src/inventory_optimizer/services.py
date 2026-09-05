"""Public service protocols (T12; Section 17.2).

Sits at the top level, not under ``ports/`` -- ``ports/solver.py``'s own docstring scopes that
package to internal backend-abstraction protocols; these front the outward-facing contract §17.2
names, a different audience (callers of this library) than ``ports/``'s (backend implementers).

``ScenarioService`` is deliberately not defined here: it would reference ``ScenarioBatchRequest``/
``ScenarioComparison``, neither of which exists yet (the scenario engine, T13-T14, hasn't started).
Defining a Protocol against types that don't exist would lock in a signature before that work
decides its own shape -- see ``specs/0003-public-api-cli/spec.md``'s Non-Goals.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from inventory_optimizer.domain.enums import ReasonCode
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.results import OptimizationResult


@runtime_checkable
class OptimizationService(Protocol):
    def optimize(self, request: OptimizationRequest) -> OptimizationResult: ...


@runtime_checkable
class ExplanationService(Protocol):
    def explain(self, result: OptimizationResult) -> OptimizationExplanation: ...


@dataclass(frozen=True, slots=True)
class RouteExplanationView:
    """One route's explanation, read straight off an already-built ``OptimizationResult`` --
    never re-derived from a ``VerifiedSolution`` (Section 18.3's evidence was already computed
    once, during T11's ``build_optimization_result``)."""

    route_id: str
    reason_codes: tuple[ReasonCode, ...]
    evidence: Mapping[str, float | str]


@dataclass(frozen=True, slots=True)
class OptimizationExplanation:
    """Aggregate, read-only view over a result's per-route explanations (Section 18.3) -- not a
    re-derivation. Built entirely from ``OptimizationResult.allocations``, which already carries
    each route's ``reason_codes``/``explanation_evidence`` (populated during T11's
    ``build_optimization_result`` via ``reporting.explanations.explain_routes``)."""

    run_id: str
    routes_with_reasons: tuple[RouteExplanationView, ...]
    reason_code_counts: Mapping[ReasonCode, int]


class ExplanationServiceImpl:
    """The concrete ``ExplanationService``. Reads only ``OptimizationResult.allocations`` -- no
    solver or verifier call, no ``VerifiedSolution`` dependency (REQ-007)."""

    def explain(self, result: OptimizationResult) -> OptimizationExplanation:
        routes = tuple(
            RouteExplanationView(
                route_id=allocation.route_id,
                reason_codes=allocation.reason_codes,
                evidence=allocation.explanation_evidence,
            )
            for allocation in result.allocations
            if allocation.reason_codes
        )
        counts: dict[ReasonCode, int] = {}
        for route in routes:
            for code in route.reason_codes:
                counts[code] = counts.get(code, 0) + 1
        return OptimizationExplanation(
            run_id=result.run_id, routes_with_reasons=routes, reason_code_counts=counts
        )

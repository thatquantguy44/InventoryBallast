"""Objective attribution tests (T11; Section 18.2; VER-002, LP-007).

AC-001/AC-002 solve the real E1 fixture and confirm every registered component attributes
without error and the sum reconciles to the solver's own claimed objective. AC-003 proves the
reconciliation check actually fails closed: a fake objective component (registered on an isolated
``Registry`` so production registrations are untouched) whose ``attribute()`` returns a value that
cannot possibly match the solver's real objective must raise, not pass silently.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from inventory_optimizer.components.decorators import objective_component
from inventory_optimizer.components.registry import ComponentKind, Registry
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.exceptions import AttributionMismatchError
from inventory_optimizer.reporting.attribution import attribute_objective
from inventory_optimizer.reporting.types import ObjectiveAttribution, VerifiedSolution
from inventory_optimizer.validation import DEFAULT_TOLERANCE


def test_all_components_attribute_without_error(e1_solution: VerifiedSolution) -> None:
    """AC-001."""
    attributions = attribute_objective(e1_solution)

    assert {a.component_name for a in attributions} == {"fee_revenue", "transition_cost"}
    for attribution in attributions:
        assert math.isfinite(attribution.unscaled_value_usd)


def test_attributed_sum_matches_solver_objective(e1_solution: VerifiedSolution) -> None:
    """AC-002."""
    attributions = attribute_objective(e1_solution)
    total = sum(a.unscaled_value_usd for a in attributions)

    assert e1_solution.result.objective_value_unscaled is not None
    assert total == pytest.approx(
        e1_solution.result.objective_value_unscaled, abs=DEFAULT_TOLERANCE
    )


_FAKE_REGISTRY = Registry()


@objective_component(
    name="fake_mismatched_objective",
    version="1",
    formulations={Formulation.LP},
    registry=_FAKE_REGISTRY,
)
class _FakeMismatchedObjective:
    """Deliberately attributes a value the compiled objective never produced, to prove
    ``attribute_objective`` fails closed (AC-003) rather than trusting a component's claim."""

    def validate(self, context: object) -> tuple[object, ...]:
        return ()

    def contribute(self, context: object, builder: object) -> None:
        return None

    def attribute(self, solution: object) -> ObjectiveAttribution:
        return ObjectiveAttribution(
            component_name="fake_mismatched_objective",
            component_version="1",
            unscaled_value_usd=999.0,
            baseline_value_usd=0.0,
            delta_usd=999.0,
        )


def test_mismatch_raises_attribution_error(e1_solution: VerifiedSolution) -> None:
    """AC-003."""
    fake_registration = _FAKE_REGISTRY.get(
        ComponentKind.OBJECTIVE, "fake_mismatched_objective", "1"
    )
    mismatched_problem = dataclasses.replace(e1_solution.problem, manifest=(fake_registration,))
    mismatched_solution = dataclasses.replace(e1_solution, problem=mismatched_problem)

    with pytest.raises(AttributionMismatchError):
        attribute_objective(mismatched_solution)

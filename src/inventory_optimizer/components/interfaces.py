"""Component protocols (Section 15.2).

``BuildContext`` (T08) and ``ModelBuilder`` == ``formulation.SparseBuilder`` (T07) exist.
``VerifiedSolution`` and ``ObjectiveAttribution`` (T11) are introduced in ``reporting.types``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.reporting.types import ObjectiveAttribution, VerifiedSolution


@runtime_checkable
class ConstraintComponent(Protocol):
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None: ...


@runtime_checkable
class ObjectiveComponent(Protocol):
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None: ...
    def attribute(self, solution: VerifiedSolution) -> ObjectiveAttribution: ...

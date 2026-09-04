"""Component protocols (Section 15.2).

``VerifiedSolution`` and ``ObjectiveAttribution`` are independent-verifier (T10) and result-
attribution (T11) types not introduced yet. ``BuildContext`` (T08) and ``ModelBuilder`` ==
``formulation.SparseBuilder`` (T07) now exist.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.context import BuildContext
from inventory_optimizer.formulation.sparse_builder import SparseBuilder


@runtime_checkable
class ConstraintComponent(Protocol):
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None: ...


@runtime_checkable
class ObjectiveComponent(Protocol):
    def validate(self, context: BuildContext) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: BuildContext, builder: SparseBuilder) -> None: ...
    def attribute(self, solution: object) -> object: ...

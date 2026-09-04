"""Component protocols (Section 15.2).

``BuildContext``, ``VerifiedSolution``, and ``ObjectiveAttribution`` are formulation-compiler
(T08) and independent-verifier (T10) types not introduced yet. ``ModelBuilder`` is
``formulation.SparseBuilder`` (T07), now that it exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from inventory_optimizer.exceptions import ValidationIssue
from inventory_optimizer.formulation.sparse_builder import SparseBuilder


@runtime_checkable
class ConstraintComponent(Protocol):
    def validate(self, context: object) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: object, builder: SparseBuilder) -> None: ...


@runtime_checkable
class ObjectiveComponent(Protocol):
    def validate(self, context: object) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: object, builder: SparseBuilder) -> None: ...
    def attribute(self, solution: object) -> object: ...

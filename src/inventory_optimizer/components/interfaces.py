"""Component protocols (Section 15.2).

``BuildContext``, ``ModelBuilder``, ``VerifiedSolution``, and ``ObjectiveAttribution`` are
formulation/verification types introduced with the sparse compiler (T07-T08) and the independent
verifier (T10). Phase 0A types them as ``object`` placeholders so the protocol shape is fixed now
without inventing Phase 1 internals early.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from inventory_optimizer.exceptions import ValidationIssue


@runtime_checkable
class ConstraintComponent(Protocol):
    def validate(self, context: object) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: object, builder: object) -> None: ...


@runtime_checkable
class ObjectiveComponent(Protocol):
    def validate(self, context: object) -> Sequence[ValidationIssue]: ...
    def contribute(self, context: object, builder: object) -> None: ...
    def attribute(self, solution: object) -> object: ...

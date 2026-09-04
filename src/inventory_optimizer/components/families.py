"""Problem-family registration (Section 23.1, T35 baseline).

Only ``securities_lending_inventory`` registers in Phase 0A. Agency (T36-T37) and prime (T38-T39)
families register the same way once their domain records and desk components exist; registering
them must never change this family's compiled rows, objective terms, or results (Section 30).
"""

from __future__ import annotations

from abc import ABC

from inventory_optimizer.components.decorators import problem_family
from inventory_optimizer.domain.enums import Formulation
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.domain.results import OptimizationResult


class ProblemFamilyBase(ABC):
    """Base for registered problem-family definitions.

    Named distinctly from ``domain.enums.ProblemFamily`` (the family-name enum) even though
    Section 15's illustrative snippet reuses that identifier for both.
    """

    request_type: type
    result_type: type


@problem_family(
    name="securities_lending_inventory",
    version="1",
    supported_formulations={Formulation.LP, Formulation.MIP, Formulation.QP},
)
class SecuritiesLendingInventoryProblem(ProblemFamilyBase):
    request_type = OptimizationRequest
    result_type = OptimizationResult

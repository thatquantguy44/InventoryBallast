"""Domain contracts: business records, IDs, enums, and request/result types.

Per ``01_SPEC.md`` Section 7.1, this layer owns business records, IDs, enums, and
request/result types. It must not own solver calls or dataframe transforms.

Phase 0A implements the E1-vertical subset (Section 9.1): ``SecurityInventory``, ``LoanRoute``,
``DemandForecast``, ``CounterpartyLimit``, ``UtilizationPolicy``, ``OptimizationRequest``, and a
skeleton ``OptimizationResult``. ``EligibilitySchedule``, ``CollateralSchedule``,
``ConstraintSchedule``, ``DeskContext`` fields beyond the problem-family selector, and the
agency/prime records (``BeneficialOwnerMandate``, ``InventorySource``, ``ClientShortDemand``,
``ExternalBorrowQuote``, ``IndemnificationPolicy``, ``AgreementNettingSet``,
``BalanceSheetBudget``) are added when their owning subsystems land (T29-T33, T35-T39).
"""

from inventory_optimizer.domain.demand import DemandForecast
from inventory_optimizer.domain.enums import (
    Capability,
    DayCountBasis,
    Formulation,
    ObjectiveSense,
    ProblemFamily,
    QuantityType,
    ReasonCode,
    SolverStatus,
)
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.policies import CounterpartyLimit, UtilizationPolicy
from inventory_optimizer.domain.requests import DeskContext, OptimizationRequest
from inventory_optimizer.domain.results import OptimizationResult

__all__ = [
    "Capability",
    "CounterpartyLimit",
    "DayCountBasis",
    "DemandForecast",
    "DeskContext",
    "Formulation",
    "LoanRoute",
    "ObjectiveSense",
    "OptimizationRequest",
    "OptimizationResult",
    "ProblemFamily",
    "QuantityType",
    "ReasonCode",
    "SecurityInventory",
    "SolverStatus",
    "UtilizationPolicy",
]

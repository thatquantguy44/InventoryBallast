"""``BuildContext`` (Section 15.2): everything a constraint/objective component needs to
``contribute()`` to one compiled LP.

Kept separate from ``formulation/lp.py`` (the compiler) so concrete components can depend on this
module without creating an import cycle: components need ``BuildContext``'s *shape*, while
``lp.py`` needs to import the components themselves to trigger their registration.

Built once per compile so components never re-scan the request themselves (Section 20.1: "avoid
dataframe row iteration in formulation code").
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from inventory_optimizer.config.models import InventoryOptimizerConfig
from inventory_optimizer.domain.inventory import SecurityInventory
from inventory_optimizer.domain.loans import LoanRoute
from inventory_optimizer.domain.requests import OptimizationRequest
from inventory_optimizer.elasticity import EvaluatedDemand
from inventory_optimizer.formulation.indexes import VariableIndex


@dataclass(frozen=True, slots=True)
class BuildContext:
    request: OptimizationRequest
    config: InventoryOptimizerConfig
    variable_index: VariableIndex
    demand_caps: Mapping[str, EvaluatedDemand]
    inventory_by_id: Mapping[str, SecurityInventory]
    routes_by_inventory: Mapping[str, tuple[LoanRoute, ...]]
    routes_by_demand_group: Mapping[str, tuple[LoanRoute, ...]]
    routes_by_borrower: Mapping[str, tuple[LoanRoute, ...]]

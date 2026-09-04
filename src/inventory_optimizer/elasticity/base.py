"""Elasticity curve protocol (Section 12.1).

A curve turns a reference demand/fee pair plus an evaluated fee into a *raw* demand estimate --
before the uncertainty haircut and hard cap that ``caps.py`` applies. Elasticity is preprocessing,
not an LP decision: nothing here builds or touches a model.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ElasticityCurve(Protocol):
    def raw_demand(
        self,
        *,
        reference_quantity: float,
        reference_fee: float,
        evaluated_fee: float,
        elasticity: float,
        fee_floor: float,
    ) -> float:
        """Return ``D_raw_g(f_g)`` for one demand group. ``elasticity`` is a non-negative
        magnitude (validated by ``DemandForecast``); ``fee_floor`` keeps a non-positive evaluated
        fee out of the curve per Section 12.1 ("a fee at or below zero ... may not enter the power
        formula directly")."""
        ...

"""Elasticity service (T06; Section 12): the demand-group fee-to-quantity transform.

Elasticity runs before model construction (Section 12.1: "Elasticity is preprocessing, not an LP
decision"), so it is deliberately independent of the formulation/solver layers -- it only needs a
``DemandForecast`` and one evaluated fee. Golden values are validated against ``EXAMPLES.md`` E2.
"""

from __future__ import annotations

from dataclasses import dataclass

from inventory_optimizer.config.models import ElasticityConfig
from inventory_optimizer.domain.demand import DemandForecast
from inventory_optimizer.domain.enums import ElasticityCurveType, ReasonCode
from inventory_optimizer.elasticity.base import ElasticityCurve
from inventory_optimizer.elasticity.caps import apply_uncertainty_and_cap
from inventory_optimizer.elasticity.constant import ConstantElasticityCurve
from inventory_optimizer.elasticity.semilog import SemiLogElasticityCurve

_CURVES: dict[ElasticityCurveType, ElasticityCurve] = {
    ElasticityCurveType.CONSTANT: ConstantElasticityCurve(),
    ElasticityCurveType.SEMILOG: SemiLogElasticityCurve(),
}


@dataclass(frozen=True, slots=True)
class EvaluatedDemand:
    """Result of evaluating one demand group at one fee. All quantities in shares."""

    raw_demand_shares: float
    effective_cap_shares: float
    uncertainty_haircut_shares: float
    reason_code: ReasonCode | None


def evaluate_demand_cap(
    forecast: DemandForecast,
    evaluated_fee: float,
    *,
    config: ElasticityConfig,
) -> EvaluatedDemand:
    """Section 12.1's ``D_g(f_g)``, plus the uncertainty haircut and hard cap."""
    curve = _CURVES[config.curve]
    raw_demand = curve.raw_demand(
        reference_quantity=forecast.reference_quantity_shares,
        reference_fee=forecast.reference_fee_rate,
        evaluated_fee=evaluated_fee,
        elasticity=forecast.elasticity,
        fee_floor=config.fee_floor,
    )
    effective_cap = apply_uncertainty_and_cap(
        raw_demand,
        forecast_std=forecast.forecast_std_shares,
        uncertainty_haircut_sigma=config.uncertainty_haircut_sigma,
        hard_max=forecast.hard_max_quantity_shares,
    )
    haircut_shares = config.uncertainty_haircut_sigma * (forecast.forecast_std_shares or 0.0)

    reduced_by_fee = (
        forecast.elasticity > 0.0
        and evaluated_fee > forecast.reference_fee_rate
        and effective_cap < forecast.reference_quantity_shares
    )
    return EvaluatedDemand(
        raw_demand_shares=raw_demand,
        effective_cap_shares=effective_cap,
        uncertainty_haircut_shares=haircut_shares,
        reason_code=ReasonCode.ELASTICITY_REDUCED_DEMAND if reduced_by_fee else None,
    )


__all__ = ["EvaluatedDemand", "evaluate_demand_cap"]

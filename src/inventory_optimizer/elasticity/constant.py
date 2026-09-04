"""Default constant-elasticity curve (Section 12.1):

    D_raw_g(f_g) = Q_ref_g * (max(f_g, fee_floor) / F_ref_g) ^ (-epsilon_g)

``epsilon_g > 0`` means a higher fee reduces demand; ``epsilon_g == 0`` means price-insensitive
demand. The ``epsilon == 0`` case is special-cased to skip the power expression entirely so a
zero reference fee (legal when elasticity is zero -- see ``DemandForecast``) never divides by zero.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ConstantElasticityCurve:
    def raw_demand(
        self,
        *,
        reference_quantity: float,
        reference_fee: float,
        evaluated_fee: float,
        elasticity: float,
        fee_floor: float,
    ) -> float:
        if elasticity == 0.0:
            return reference_quantity
        floored_fee = max(evaluated_fee, fee_floor)
        # float ** float is typed Any in typeshed (a negative base with a fractional exponent can
        # return complex); floored_fee/reference_fee is always positive here, so this is safe.
        ratio_power = float((floored_fee / reference_fee) ** (-elasticity))
        return reference_quantity * ratio_power

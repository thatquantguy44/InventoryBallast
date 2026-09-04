"""Optional semi-log elasticity curve (Section 12.1):

    D_raw_g(f_g) = Q_ref_g * exp(-beta_g * (f_g - F_ref_g))

``elasticity`` plays the role of ``beta_g`` here; it is a separate curve selection
(``ElasticityConfig.curve``), not a second parameter alongside the constant curve's epsilon.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SemiLogElasticityCurve:
    def raw_demand(
        self,
        *,
        reference_quantity: float,
        reference_fee: float,
        evaluated_fee: float,
        elasticity: float,
        fee_floor: float,
    ) -> float:
        floored_fee = max(evaluated_fee, fee_floor)
        return reference_quantity * math.exp(-elasticity * (floored_fee - reference_fee))

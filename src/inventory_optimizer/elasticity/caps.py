"""Uncertainty haircut and hard-cap clipping (Section 12.1):

    D_g = clip(D_raw_g(f_g) - uncertainty_haircut_sigma * forecast_std_g, lower=0, upper=hard_max_g
               if supplied else +infinity)

Section 12.3: "Estimated uncertainty may haircut demand ... it must not silently change the fee
rate." This module only ever adjusts the quantity side.
"""

from __future__ import annotations

import math


def apply_uncertainty_and_cap(
    raw_demand: float,
    *,
    forecast_std: float | None,
    uncertainty_haircut_sigma: float,
    hard_max: float | None,
) -> float:
    haircut = uncertainty_haircut_sigma * (forecast_std or 0.0)
    upper = hard_max if hard_max is not None else math.inf
    return min(max(raw_demand - haircut, 0.0), upper)

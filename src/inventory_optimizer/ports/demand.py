"""Demand-source port: how the service layer pulls upstream demand forecasts.

Concrete sources (QR Haven's borrow-demand outputs, an equivalent upstream model) are wired by
platform-owned adapter code (Section 17.4: "reuse QR Haven borrow-demand outputs only through the
adapter contract"). Nothing here may import qr_haven.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol, runtime_checkable

from inventory_optimizer.domain.demand import DemandForecast


@runtime_checkable
class DemandForecastSource(Protocol):
    def fetch(
        self, as_of: datetime, security_ids: Sequence[str]
    ) -> Sequence[DemandForecast]:
        """Return demand forecasts observable as of ``as_of`` for the given securities."""
        ...

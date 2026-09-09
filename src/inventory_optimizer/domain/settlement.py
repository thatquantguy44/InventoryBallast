"""Multi-period settlement result contracts (specs/0010-multi-period-settlement/; Section 22.11).

A new, additive result type -- mirroring how ``domain.scenario_results.ScenarioComparison``/
``StressTestReport`` are already distinct result types rather than fields bolted onto
``OptimizationResult`` itself. Produced by two sanctioned constructors: ``settlement.project.
project_multi_period`` (``mode="projected"`` -- period 0 is the already-solved allocation, periods
1..N are a mechanical projection of already-known future events against it) and
``formulation.multi_period.compile_multi_period_lp``'s own result builder (``mode=
"jointly_optimized"`` -- every period was genuinely decided by the solver). ``mode``/``disclosure``
are unconditional (NFR-003): nothing about this type's shape implies a projected period was
optimized, or vice versa.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict

from inventory_optimizer.domain.enums import SolverStatus

MultiPeriodMode = Literal["projected", "jointly_optimized"]

_DISCLOSURE_BY_MODE: dict[MultiPeriodMode, str] = {
    "projected": (
        "Period 0 is the solved allocation. Periods 1..N are a mechanical projection of "
        "already-known future events against that allocation, not a re-optimized plan."
    ),
    "jointly_optimized": (
        "Every period 0..N was jointly optimized against known future events; this is not a "
        "projection."
    ),
}


def disclosure_for_mode(mode: MultiPeriodMode) -> str:
    """The single source of truth for REQ-009/NFR-003's disclosure text -- both sanctioned
    constructors call this rather than each spelling out its own string."""
    return _DISCLOSURE_BY_MODE[mode]


class PeriodBalance(BaseModel):
    """One inventory record's Section 22.11 balance identity at one period."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inventory_id: str
    period_index: int
    period_date: date
    total_lendable_shares: float
    on_loan_shares: float
    available_to_lend_shares: float
    utilization: float


class PeriodEconomics(BaseModel):
    """One period's net lending economics, discounted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    period_index: int
    period_date: date
    day_count_fraction: float
    undiscounted_net_revenue_usd: float
    discount_factor: float
    discounted_net_revenue_usd: float


class MultiPeriodProjection(BaseModel):
    """Frozen boundary contract. See this module's own docstring for the two sanctioned
    constructors and what ``mode`` means. ``status`` mirrors ``OptimizationResult``'s own honest-
    status discipline: when there is no feasible primal to report against (period 0 infeasible for
    ``"projected"``; the joint LP itself infeasible/no-primal for ``"jointly_optimized"``),
    ``balances``/``economics`` are empty rather than zero-filled placeholders, and a warning is
    recorded -- never raised, matching how ``reporting.result_builder`` handles the same case for
    ``OptimizationResult``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    mode: MultiPeriodMode
    status: SolverStatus
    planning_periods: tuple[date, ...]
    balances: tuple[PeriodBalance, ...]
    economics: tuple[PeriodEconomics, ...]
    total_discounted_net_revenue_usd: float
    warnings: tuple[str, ...] = ()
    disclosure: str

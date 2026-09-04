"""Canonical enumerations shared across the domain, config, and formulation layers.

Values are stable identifiers referenced by golden fixtures and configuration; do not rename
without a decision record (``01_SPEC.md`` Section 30).
"""

from __future__ import annotations

from enum import StrEnum


class ProblemFamily(StrEnum):
    """Registered problem families (Section 23.1). Only the baseline family ships in Phase 0A."""

    SECURITIES_LENDING_INVENTORY = "securities_lending_inventory"
    AGENCY_LENDING = "agency_lending"
    PRIME_INVENTORY_FINANCING = "prime_inventory_financing"


class Formulation(StrEnum):
    """Mathematical program shape (Section 14)."""

    LP = "lp"
    MIP = "mip"
    QP = "qp"


class ObjectiveSense(StrEnum):
    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


class DayCountBasis(StrEnum):
    """Section 5.2: day fraction is calendar days / configured year basis."""

    ACT_360 = "act_360"
    ACT_365 = "act_365"


class ElasticityCurveType(StrEnum):
    """Section 12.1. ``CONSTANT`` is the V0 default; ``SEMILOG`` is the documented optional
    curve."""

    CONSTANT = "constant"
    SEMILOG = "semilog"


class QuantityType(StrEnum):
    """Section 5.2: share quantities may be continuous in LP mode or integer under MIP/repair."""

    CONTINUOUS = "continuous"
    INTEGER_LOTS = "integer_lots"


class Capability(StrEnum):
    """Solver backend capabilities (Section 16.2)."""

    LP = "lp"
    MIP = "mip"
    CONTINUOUS_QP = "continuous_qp"


class SolverStatus(StrEnum):
    """Normalized solver statuses (Section 16.3). ``FEASIBLE_LIMIT`` must never be promoted to
    ``OPTIMAL``."""

    OPTIMAL = "optimal"
    FEASIBLE_LIMIT = "feasible_limit"
    INFEASIBLE = "infeasible"
    UNBOUNDED = "unbounded"
    INFEASIBLE_OR_UNBOUNDED = "infeasible_or_unbounded"
    INVALID_MODEL = "invalid_model"
    NUMERICAL_ERROR = "numerical_error"
    INTERRUPTED = "interrupted"
    SOLVER_ERROR = "solver_error"


class ReasonCode(StrEnum):
    """Structured decision-explanation reason codes (Section 18.3)."""

    HIGHER_NET_FEE = "higher_net_fee"
    DEMAND_CAP_BINDING = "demand_cap_binding"
    INVENTORY_SCARCE = "inventory_scarce"
    UTILIZATION_CAP_BINDING = "utilization_cap_binding"
    RESERVE_BINDING = "reserve_binding"
    COUNTERPARTY_LIMIT_BINDING = "counterparty_limit_binding"
    INELIGIBLE_ROUTE = "ineligible_route"
    TERM_OR_RECALL_RESTRICTION = "term_or_recall_restriction"
    TRANSITION_COST_EXCEEDS_UPLIFT = "transition_cost_exceeds_uplift"
    TRADE_REDUCED_SUPPLY = "trade_reduced_supply"
    ELASTICITY_REDUCED_DEMAND = "elasticity_reduced_demand"
    SOFT_TARGET_TRADEOFF = "soft_target_tradeoff"
    ELIGIBILITY_SCHEDULE_BOUND = "eligibility_schedule_bound"
    COLLATERAL_SCHEDULE_MISMATCH = "collateral_schedule_mismatch"
    COLLATERAL_CAPACITY_BINDING = "collateral_capacity_binding"
    COLLATERAL_CONCENTRATION_BINDING = "collateral_concentration_binding"
    OWNER_MANDATE_BOUND = "owner_mandate_bound"
    AGENCY_FAIRNESS_TRADEOFF = "agency_fairness_tradeoff"
    INDEMNIFICATION_COST = "indemnification_cost"
    SOURCE_CAPACITY_BINDING = "source_capacity_binding"
    EXTERNAL_BORROW_SELECTED = "external_borrow_selected"
    CLIENT_REUSE_NOT_AUTHORIZED = "client_reuse_not_authorized"
    HARD_COVERAGE_REQUIREMENT = "hard_coverage_requirement"
    BALANCE_SHEET_LIMIT_BINDING = "balance_sheet_limit_binding"

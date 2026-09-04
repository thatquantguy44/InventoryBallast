"""Solver backend protocol and normalized result types (Section 16.2).

Phase 0A defines the interface only; ``solvers/highs.py`` (T09) is the first concrete backend and
is the sole owner of ``highspy`` imports (Section 16.4). Nothing here may import a solver package.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

from inventory_optimizer.domain.enums import Capability, SolverStatus


@dataclass(frozen=True, slots=True)
class SolverOptions:
    """Allow-listed solver options (Section 16.4 item 3)."""

    time_limit_seconds: float | None = None
    relative_gap: float | None = None
    threads: int | None = None
    seed: int | None = None
    log_level: str = "warning"


@dataclass(frozen=True, slots=True)
class SolverWarmStart:
    """Opaque warm-start payload; shape is backend-specific and defined with T09/T15."""

    primal: NDArray[np.float64] | None = None


@dataclass(frozen=True, slots=True)
class SolverResult:
    """Normalized solver output (Section 16.2)."""

    status: SolverStatus
    primal: NDArray[np.float64] | None
    dual: NDArray[np.float64] | None
    reduced_costs: NDArray[np.float64] | None
    objective_value_scaled: float | None
    objective_value_unscaled: float | None
    best_bound: float | None
    relative_gap: float | None
    runtime_seconds: float
    iterations: int | None
    nodes: int | None
    termination_reason: str
    backend_name: str
    backend_version: str
    effective_options: SolverOptions
    native_status: str


@runtime_checkable
class SolverBackend(Protocol):
    """Section 16.2. ``problem``/``CompiledProblem`` is introduced with the formulation layer
    (T07-T08)."""

    @property
    def capabilities(self) -> frozenset[Capability]: ...

    def solve(
        self,
        problem: object,
        options: SolverOptions,
        warm_start: SolverWarmStart | None = None,
    ) -> SolverResult: ...

"""As-of resolution for ``PointInTimeValue`` (REQ-005, REQ-006; Section 22.3).

The entire no-look-ahead guarantee (NFR-003) is the ``observed_at <= known_as_of`` filter applied
*before* any effective-time reasoning below -- a value can never be selected on the strength of its
economic correctness alone. For a live solve, callers pass ``known_as_of = request.as_of`` (today's
knowledge is today's knowledge); for a backtest, callers pass the simulated decision time as
``known_as_of`` and the historical date being simulated as ``as_of`` -- this is Section 22.3's "join
on both economic effective time and knowledge/observation time," applied literally.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TypeVar

from inventory_optimizer.domain.reference import PointInTimeValue

T = TypeVar("T")


def resolve_latest_known(
    candidates: Iterable[PointInTimeValue[T]],
    *,
    as_of: datetime,
    known_as_of: datetime,
) -> PointInTimeValue[T] | None:
    """Returns the latest-effective candidate that was already known as of ``known_as_of`` and is
    economically effective at ``as_of``, or ``None`` if no such candidate exists -- never a stale
    silent default (REQ-005)."""
    eligible = [
        candidate
        for candidate in candidates
        if candidate.observed_at <= known_as_of
        and candidate.effective_from <= as_of
        and (candidate.effective_to is None or as_of < candidate.effective_to)
    ]
    if not eligible:
        return None
    return max(eligible, key=lambda candidate: (candidate.effective_from, candidate.observed_at))

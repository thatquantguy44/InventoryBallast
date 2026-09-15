"""Corporate-action event contract (specs/0011-bloomberg-data-foundation/; Section 22.3, 22.8).

R0/T21 scope only: identity, timing, and version lineage. Section 22.8's full economic
consequences (quantity transformation, manufactured-payment cost, election handling) are R1+ and
are not modeled here -- see ``specs/0011-bloomberg-data-foundation/spec.md``'s Non-Goals.

``CorporateActionEvent`` is never mutated in place (Section 22.3: "Announcements may be amended or
cancelled... history is not rewritten"). There is deliberately no method on this class that changes
an existing instance's fields; an amendment is a *new* instance sharing ``event_id`` with
``version = prior.version + 1`` and ``supersedes_event_id`` pointing at the prior version's own
identity. A store keyed by ``(event_id, version)`` -- not ``event_id`` alone -- retains every
version; ``enrichment.point_in_time.resolve_latest_known`` is what selects "the version known as of
a given time" out of that set.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CorporateActionType(StrEnum):
    """Section 22.8's event-behavior table, by example type rather than by behavior category --
    the behavior classification itself is R1+ scenario-compiler logic, not a domain field."""

    SPLIT = "split"
    DIVIDEND = "dividend"
    MERGER = "merger"
    SPINOFF = "spinoff"
    TENDER = "tender"
    RIGHTS = "rights"
    SUSPENSION = "suspension"
    DELISTING = "delisting"


class CorporateActionStatus(StrEnum):
    ANNOUNCED = "announced"
    CONFIRMED = "confirmed"
    AMENDED = "amended"
    CANCELLED = "cancelled"


class CorporateActionEvent(BaseModel):
    """Frozen boundary contract. See this module's own docstring for the versioning contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    event_id: str
    version: int = Field(ge=1)
    supersedes_event_id: str | None = None
    event_type: CorporateActionType
    status: CorporateActionStatus
    affected_security_ids: tuple[str, ...]
    announcement_date: date
    effective_date: date | None = None
    record_date: date | None = None
    ex_date: date | None = None
    pay_date: date | None = None
    election_deadline: date | None = None
    terms: Mapping[str, str] = {}

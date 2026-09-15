"""Adapter health check (REQ-011; Section 22.4: "The adapter's doctor command must list required
business concepts, mapped fields, entitlements, last successful observation, and unavailable
optional concepts without exposing credentials.").

Nothing in ``FieldMapping``/``ConceptMapping`` or either synthetic adapter carries a credential or
API key (NFR-005) -- there is nothing to redact by construction, not by a filter that could miss
one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from inventory_optimizer.adapters.bloomberg.field_mapping import FieldMapping
from inventory_optimizer.ports.corporate_actions import CorporateActionsPort
from inventory_optimizer.ports.reference_data import ReferenceDataPort


@dataclass(frozen=True, slots=True)
class ConceptHealth:
    concept: str
    mapped: bool
    entitlement_id: str
    last_observed_at: datetime | None
    available: bool


@dataclass(frozen=True, slots=True)
class BloombergHealthReport:
    field_mapping_version: str
    concepts: tuple[ConceptHealth, ...]


def check_bloomberg_adapter_health(
    mapping: FieldMapping,
    reference_data: ReferenceDataPort,
    *,
    sample_security_id: str,
    known_as_of: datetime,
    sample_market: str | None = None,
    corporate_actions: CorporateActionsPort | None = None,
) -> BloombergHealthReport:
    """Probes only what this port surface can actually probe: ``security_reference.*`` concepts
    via ``reference_data.get_security_reference``; ``market_calendar.*`` concepts via
    ``reference_data.get_market_calendar`` when ``sample_market`` is given;
    ``corporate_action_event.*`` concepts via ``corporate_actions.get_events`` when supplied. A
    concept this report cannot probe is reported ``available=False`` rather than guessed --
    Section 22.4's "unavailable optional concepts" language, taken literally."""
    concepts: list[ConceptHealth] = []
    for name, concept_mapping in mapping.concepts.items():
        last_observed_at: datetime | None = None
        available = False
        if name.startswith("security_reference."):
            found = reference_data.get_security_reference(
                sample_security_id, as_of=known_as_of, known_as_of=known_as_of
            )
            if found is not None:
                available = True
                last_observed_at = found.observed_at
        elif name.startswith("market_calendar.") and sample_market is not None:
            found_calendar = reference_data.get_market_calendar(
                sample_market, known_as_of=known_as_of
            )
            if found_calendar is not None:
                available = True
                last_observed_at = found_calendar.observed_at
        elif name.startswith("corporate_action_event.") and corporate_actions is not None:
            events = corporate_actions.get_events(sample_security_id, known_as_of=known_as_of)
            available = bool(events)
        concepts.append(
            ConceptHealth(
                concept=name,
                mapped=True,
                entitlement_id=concept_mapping.entitlement_id,
                last_observed_at=last_observed_at,
                available=available,
            )
        )
    return BloombergHealthReport(
        field_mapping_version=mapping.version, concepts=tuple(concepts)
    )

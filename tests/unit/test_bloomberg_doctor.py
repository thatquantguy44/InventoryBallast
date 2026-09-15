"""Bloomberg adapter health-check tests (specs/0011-bloomberg-data-foundation/: REQ-011, AC-008,
NFR-005)."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime

from inventory_optimizer.adapters.bloomberg.field_mapping import ConceptMapping, FieldMapping
from inventory_optimizer.adapters.bloomberg.health import check_bloomberg_adapter_health
from inventory_optimizer.adapters.bloomberg.reference import SyntheticReferenceDataAdapter
from inventory_optimizer.cli import main

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_CREDENTIAL_PATTERN = re.compile(r"(api[_-]?key|secret|password|token)", re.IGNORECASE)


def _mapping() -> FieldMapping:
    return FieldMapping(
        version="1",
        concepts={
            "security_reference.trading_status": ConceptMapping(
                mnemonic="EXAMPLE_MNEMONIC",
                unit=None,
                null_policy="reject",
                effective_time_field=None,
                entitlement_id="example-entitlement-refdata",
            ),
            "market_calendar.settlement_holidays": ConceptMapping(
                mnemonic="EXAMPLE_CALENDAR_MNEMONIC",
                unit=None,
                null_policy="empty",
                effective_time_field=None,
                entitlement_id="example-entitlement-calendar",
            ),
        },
    )


def test_health_report_lists_every_configured_concept() -> None:
    mapping = _mapping()
    adapter = SyntheticReferenceDataAdapter(field_mapping=mapping)
    report = check_bloomberg_adapter_health(
        mapping, adapter, sample_security_id="SEC-1", known_as_of=_T0
    )
    assert {concept.concept for concept in report.concepts} == set(mapping.concepts)
    assert all(concept.mapped for concept in report.concepts)
    assert all(concept.entitlement_id for concept in report.concepts)
    # No fixture data was supplied: every concept is honestly reported unavailable, not guessed.
    assert all(concept.available is False for concept in report.concepts)


def test_health_report_contains_no_credential_shaped_string() -> None:
    """AC-008/NFR-005: the report -- and its JSON serialization -- never contains anything that
    looks like a credential, because none exists on FieldMapping/ConceptMapping to begin with."""
    mapping = _mapping()
    adapter = SyntheticReferenceDataAdapter(field_mapping=mapping)
    report = check_bloomberg_adapter_health(
        mapping, adapter, sample_security_id="SEC-1", known_as_of=_T0
    )
    payload = json.dumps(
        {
            "field_mapping_version": report.field_mapping_version,
            "concepts": [
                {
                    "concept": c.concept,
                    "mapped": c.mapped,
                    "entitlement_id": c.entitlement_id,
                    "available": c.available,
                }
                for c in report.concepts
            ],
        }
    )
    assert _CREDENTIAL_PATTERN.search(payload) is None


def test_bloomberg_doctor_cli_command_succeeds(capsys) -> None:
    exit_code = main(["bloomberg-doctor"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["field_mapping_version"]
    assert len(payload["concepts"]) > 0
    assert _CREDENTIAL_PATTERN.search(captured.out) is None

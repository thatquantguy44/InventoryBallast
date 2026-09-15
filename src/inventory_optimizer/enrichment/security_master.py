"""Security-master reconciliation between internal identifiers and ``SecurityReference`` (REQ-007;
Section 22.1's source-of-truth table).

Reconciles only the fields ``SecurityInventory``/``LoanRoute`` already carry some form of today
(``currency``); expanding the reconciled field set is a follow-up, not something this function
grows silently.
"""

from __future__ import annotations

from inventory_optimizer.domain.reference import PointInTimeValue, SecurityReference
from inventory_optimizer.exceptions import ReconciliationConflict

#: Internal-field-name -> SecurityReference-field-name, for the fields this repo's own domain
#: contracts already carry and can therefore actually conflict on.
_RECONCILED_FIELDS: tuple[tuple[str, str], ...] = (("currency", "currency"),)


def reconcile(
    internal_security_id: str,
    internal_fields: dict[str, object],
    reference: PointInTimeValue[SecurityReference],
    *,
    internal_source: str = "internal",
) -> None:
    """Raises ``ReconciliationConflict`` on the first disagreeing field; returns ``None`` (no
    silent override in either direction) when every reconciled field agrees or is absent from
    ``internal_fields``."""
    for internal_field, reference_field in _RECONCILED_FIELDS:
        if internal_field not in internal_fields:
            continue
        internal_value = internal_fields[internal_field]
        bloomberg_value = getattr(reference.value, reference_field)
        if internal_value != bloomberg_value:
            raise ReconciliationConflict(
                internal_security_id=internal_security_id,
                field=internal_field,
                internal_value=internal_value,
                internal_source=internal_source,
                bloomberg_value=bloomberg_value,
                bloomberg_source_version=reference.source_version,
            )

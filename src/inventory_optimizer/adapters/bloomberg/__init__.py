"""Bloomberg adapter boundary (Section 22.2): the **sole** module tree in this package permitted
to reference a vendor field mnemonic (enforced by
``tests/unit/test_architecture_boundaries.py::test_no_bloomberg_mnemonic_outside_adapter``).

This spec (0011) ships only a synthetic, fixture-backed implementation of the two R0 ports
(``ports.reference_data.ReferenceDataPort``, ``ports.corporate_actions.CorporateActionsPort``) --
no real vendor SDK call exists anywhere in this repository. A real client is a tracked follow-up,
gated on the firm's confirmed entitlements and field catalog (Section 22.1); it would be a drop-in
implementation of the same two ports, with zero change to any consumer.
"""

from __future__ import annotations

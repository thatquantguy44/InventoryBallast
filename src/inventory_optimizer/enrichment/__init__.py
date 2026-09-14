"""Point-in-time resolution and reconciliation for enriched (Bloomberg or equivalent) reference
data (specs/0011-bloomberg-data-foundation/; Section 22.2's project structure).

Speaks only in the business-concept vocabulary of ``domain.reference``/``domain.events`` -- no
module here may import ``adapters.bloomberg`` or reference a vendor field mnemonic (Section 22.2's
adapter-boundary rule; enforced by ``tests/unit/test_architecture_boundaries.py``).
"""

from __future__ import annotations

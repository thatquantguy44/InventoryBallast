"""Small objective/constraint contributors and the registration system (Section 7.1, 15).

Must not own end-to-end orchestration. Importing this package registers the Phase 0A baseline
problem family as a side effect (``families.py``), mirroring how the illustrative decorators in
Section 15 register at module import time.
"""

from inventory_optimizer.components import families  # noqa: F401  (registers on import)
from inventory_optimizer.components.registry import (
    ComponentKind,
    ComponentRegistration,
    Registry,
    default_registry,
)

__all__ = [
    "ComponentKind",
    "ComponentRegistration",
    "Registry",
    "default_registry",
]

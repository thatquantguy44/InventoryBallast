"""Platform invocation contract (T34).

This package must never import ``qr_haven`` or any other platform-specific module: it defines the
opaque envelope the platform-owned adapter (``src/qr_haven/integrations/inventory_optimizer.py``,
T17) passes in, not the adapter itself.
"""

from inventory_optimizer.platform.context import PlatformInvocationContext

__all__ = ["PlatformInvocationContext"]

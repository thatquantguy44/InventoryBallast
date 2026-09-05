"""Portable securities-lending inventory optimization engine (Spec002).

This package must never import ``qr_haven``. See ``specs/spec002/`` in this
repository for the normative specification.
"""

from inventory_optimizer.facade import InventoryOptimizer, load_config
from inventory_optimizer.version import __version__

__all__ = ["InventoryOptimizer", "__version__", "load_config"]

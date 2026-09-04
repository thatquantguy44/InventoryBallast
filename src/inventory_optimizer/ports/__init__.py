"""Protocols for external capabilities (Section 7.1: ports own protocols, not concrete adapters).

No module in this package may import a concrete backend (``highspy``, ``pandas``, an HTTP client,
etc.); concrete adapters live in ``solvers/``, ``adapters/``, and platform-owned integration code.
"""

"""Phase 0 exit gate (Section 25): "no core file imports qr_haven".

Loads ``scripts/verify_portability.py`` by path (it is a standalone script, not part of the
installed package) and runs both of its checks.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify_portability.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("verify_portability", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_static_qr_haven_imports() -> None:
    script = _load_script()
    assert script.find_forbidden_imports() == []


def test_package_imports_with_qr_haven_blocked() -> None:
    script = _load_script()
    script.verify_importable_without_qr_haven()  # must not raise


def test_check_restores_original_module_identity() -> None:
    """Regression test: the check used to delete+reimport in place without restoring
    ``sys.modules`` afterward, which silently replaced classes like ``RegistrationError`` with new
    objects of the same name -- breaking ``except RegistrationError`` anywhere else already
    running in the same process. It must leave the exact module objects it found in place."""
    import sys

    import inventory_optimizer
    from inventory_optimizer.exceptions import RegistrationError

    module_before = sys.modules["inventory_optimizer"]

    script = _load_script()
    script.verify_importable_without_qr_haven()

    assert sys.modules["inventory_optimizer"] is module_before
    assert inventory_optimizer is module_before
    from inventory_optimizer.exceptions import RegistrationError as RegistrationErrorAfter

    assert RegistrationErrorAfter is RegistrationError

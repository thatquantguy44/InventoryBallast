#!/usr/bin/env python3
"""Portability check (Section 7.2; Phase 0 exit gate, Section 25: "no core file imports qr_haven").

Fails if:

1. any ``.py`` file under ``src/inventory_optimizer`` imports ``qr_haven`` (or any submodule), or
2. the package cannot be imported with ``qr_haven`` actively blocked from the import system.

Run directly (``python scripts/verify_portability.py``) or from ``tests/test_portability.py``.
"""

from __future__ import annotations

import ast
import importlib
import sys
import types
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent / "src" / "inventory_optimizer"
FORBIDDEN_PREFIXES = ("qr_haven",)

CHECKED_SUBMODULES = (
    "inventory_optimizer",
    "inventory_optimizer.domain",
    "inventory_optimizer.ports",
    "inventory_optimizer.validation",
    "inventory_optimizer.config",
    "inventory_optimizer.components",
    "inventory_optimizer.platform",
)


def find_forbidden_imports(package_root: Path = PACKAGE_ROOT) -> list[str]:
    """Static AST scan for ``import qr_haven`` / ``from qr_haven import ...`` anywhere in core."""
    violations: list[str] = []
    for path in sorted(package_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in FORBIDDEN_PREFIXES:
                        violations.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module.split(".")[0] in FORBIDDEN_PREFIXES:
                    violations.append(f"{path}: from {module} import ...")
    return violations


class _QrHavenBlocker:
    """A ``sys.meta_path`` finder that turns any ``qr_haven`` import into a hard failure, so a
    successful import of ``inventory_optimizer`` while this is installed proves independence even
    if ``qr_haven`` happens to be importable in the current environment."""

    def find_spec(
        self, name: str, path: object, target: types.ModuleType | None = None
    ) -> None:
        if name == "qr_haven" or name.startswith("qr_haven."):
            raise ModuleNotFoundError(f"{name} is blocked by verify_portability")
        return None


def verify_importable_without_qr_haven() -> None:
    """Prove a from-scratch import succeeds, then restore the original module objects.

    This process may already hold references to the pre-existing ``inventory_optimizer.*``
    classes (e.g. a test file's ``except SomeError`` bound at collection time). Deleting and
    reimporting in place would silently replace those classes with new, distinct objects of the
    same name, breaking ``isinstance``/``except`` checks anywhere else in the same process for the
    rest of the run. So: snapshot, delete, reimport fresh to prove it works, then put the original
    modules back rather than leaving the new ones installed.
    """
    original_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "inventory_optimizer" or name.startswith("inventory_optimizer.")
    }
    for name in original_modules:
        del sys.modules[name]

    blocker = _QrHavenBlocker()
    sys.meta_path.insert(0, blocker)
    try:
        for module_name in CHECKED_SUBMODULES:
            importlib.import_module(module_name)
    finally:
        sys.meta_path.remove(blocker)
        for name in list(sys.modules):
            if name == "inventory_optimizer" or name.startswith("inventory_optimizer."):
                del sys.modules[name]
        sys.modules.update(original_modules)


def main() -> int:
    violations = find_forbidden_imports()
    if violations:
        print("Portability check FAILED: qr_haven imports found in inventory_optimizer core:")
        for violation in violations:
            print(f"  {violation}")
        return 1

    try:
        verify_importable_without_qr_haven()
    except Exception as exc:  # noqa: BLE001 - reported to the caller, not swallowed
        print(f"Portability check FAILED: import raised {exc!r}")
        return 1

    print("Portability check passed: no qr_haven imports; package imports cleanly without it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

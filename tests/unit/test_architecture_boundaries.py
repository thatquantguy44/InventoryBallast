"""Import-boundary test for the ``adapters`` layer (specs/0008-tabular-result-output/spec.md
AC-009; ARC-004 partial evidence).

A self-contained ``ast`` walk, deliberately not reusing ``scripts/verify_portability.py``: that
script's forbidden-import set is a module-level constant tied to ARC-003's specific "no qr_haven
import" question, already IMPLEMENTED and tested; parameterizing it would widen an already-closed
surface to serve a different requirement.

This does not attempt full ARC-004 closure (every layer pair in Section 7.1's ownership table) --
only the ``adapters`` layer, whose boundary this spec's own new code must respect.
"""

from __future__ import annotations

import ast
from pathlib import Path

_PACKAGE_ROOT = Path(__file__).resolve().parents[2] / "src" / "inventory_optimizer"
_ADAPTERS_ROOT = _PACKAGE_ROOT / "adapters"

_DISALLOWED_PREFIXES = (
    "inventory_optimizer.formulation",
    "inventory_optimizer.solvers",
    "inventory_optimizer.services",
    "inventory_optimizer.scenarios",
    "inventory_optimizer.components",
    "inventory_optimizer.validation",
    "inventory_optimizer.config",
)


def _imported_module_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_adapters_layer_imports_stay_within_boundary() -> None:
    """REQ-011: adapters/* imports nothing from formulation, solvers, services, scenarios,
    components, validation, or config."""
    violations: list[str] = []
    for path in sorted(_ADAPTERS_ROOT.glob("*.py")):
        for name in _imported_module_names(path):
            if name.startswith(_DISALLOWED_PREFIXES):
                violations.append(f"{path.name} imports {name!r}")
    assert violations == []


_BLOOMBERG_ROOT = _ADAPTERS_ROOT / "bloomberg"
_KNOWN_BLOOMBERG_MNEMONICS = ("PX_LAST", "ID_BB_GLOBAL", "CRNCY", "EQY_FUND_CRNCY")


def test_no_bloomberg_mnemonic_outside_adapter() -> None:
    """AC-011 (specs/0011-bloomberg-data-foundation/, REQ-008/NFR-002): a real Bloomberg field
    mnemonic must never appear in this package's source outside adapters/bloomberg/."""
    offenders: list[str] = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        if _BLOOMBERG_ROOT in path.parents:
            continue
        text = path.read_text(encoding="utf-8")
        for mnemonic in _KNOWN_BLOOMBERG_MNEMONICS:
            if mnemonic in text:
                offenders.append(f"{path.relative_to(_PACKAGE_ROOT)} contains {mnemonic!r}")
    assert offenders == []


def test_pandas_imported_only_by_dataframe_adapter() -> None:
    """REQ-007: adapters/dataframe.py is the sole module in src/inventory_optimizer permitted to
    import pandas."""
    offenders: list[str] = []
    for path in sorted(_PACKAGE_ROOT.rglob("*.py")):
        if path == _ADAPTERS_ROOT / "dataframe.py":
            continue
        names = _imported_module_names(path)
        if any(name == "pandas" or name.startswith("pandas.") for name in names):
            offenders.append(str(path.relative_to(_PACKAGE_ROOT)))
    assert offenders == []

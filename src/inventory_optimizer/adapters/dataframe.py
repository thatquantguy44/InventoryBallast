"""Optional pandas conversion for ``reporting.tables.Table`` (T-005).

**The only module in ``src/inventory_optimizer`` permitted to import pandas** (REQ-007, enforced by
``tests/unit/test_architecture_boundaries.py``), and it imports lazily inside each function. An
eager module-level import would make the optional ``dataframe`` extra mandatory for anyone who
merely imports the package -- the same reason ``solvers/highs.py`` owns ``highspy`` behind a lazy
import, and what ``ARC-003``'s "independently installable" guarantee depends on.

A missing extra surfaces as ``ConfigurationError`` naming the install command, never a bare
``ModuleNotFoundError`` -- mirroring ``facade._resolve_backend``'s existing treatment of ``highs``.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from inventory_optimizer.exceptions import ConfigurationError
from inventory_optimizer.reporting.tables import Table

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    import pandas


def _require_pandas() -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ConfigurationError(
            "DataFrame output requires the 'dataframe' extra (pip install -e '.[dataframe]')"
        ) from exc
    return pd


def to_dataframe(table: Table) -> pandas.DataFrame:
    """One table as a frame. Columns are set explicitly so an empty table still carries its
    schema rather than degenerating to a shapeless frame."""
    pd = _require_pandas()
    return pd.DataFrame(list(table.rows), columns=list(table.columns))


def to_dataframes(tables: Sequence[Table]) -> dict[str, pandas.DataFrame]:
    """Every table keyed by its name, preserving the order given."""
    return {table.name: to_dataframe(table) for table in tables}


__all__ = ["to_dataframe", "to_dataframes"]

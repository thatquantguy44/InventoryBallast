"""``adapters.dataframe`` tests (specs/0008-tabular-result-output/spec.md AC-006, AC-007): the
happy path only runs when the optional ``dataframe`` extra is installed (``importorskip``,
NFR-001); the missing-extra path is pinned unconditionally since it is what every consumer without
the extra actually hits.
"""

from __future__ import annotations

import builtins

import pytest

from inventory_optimizer.exceptions import ConfigurationError
from inventory_optimizer.reporting.tables import Table

_TABLE = Table(name="sample", columns=("a", "b"), rows=((1, "x"), (2, "y")))


def test_to_dataframe_columns_and_shape() -> None:
    """AC-006."""
    pytest.importorskip("pandas")
    from inventory_optimizer.adapters.dataframe import to_dataframe

    frame = to_dataframe(_TABLE)

    assert list(frame.columns) == ["a", "b"]
    assert len(frame) == 2


def test_to_dataframes_keyed_by_table_name() -> None:
    pytest.importorskip("pandas")
    from inventory_optimizer.adapters.dataframe import to_dataframes

    other = Table(name="other", columns=("x",), rows=((1,),))
    frames = to_dataframes([_TABLE, other])

    assert set(frames) == {"sample", "other"}
    assert len(frames["other"]) == 1


def test_missing_extra_raises_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-007: simulates the extra being absent regardless of whether it actually is, since this
    is the failure mode every consumer without it hits."""
    real_import = builtins.__import__

    def _blocked_import(name, *args, **kwargs):
        if name == "pandas":
            raise ImportError("No module named 'pandas'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked_import)

    from inventory_optimizer.adapters.dataframe import to_dataframe

    with pytest.raises(ConfigurationError, match="dataframe"):
        to_dataframe(_TABLE)

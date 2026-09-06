"""``adapters.csv_io`` tests (specs/0008-tabular-result-output/spec.md AC-004, AC-005):
standard-library-only CSV output, and byte-identical repeat writes.
"""

from __future__ import annotations

from pathlib import Path

from inventory_optimizer.adapters.csv_io import write_table, write_tables
from inventory_optimizer.reporting.tables import Table

_TABLE = Table(
    name="sample",
    columns=("a", "b", "c"),
    rows=(
        ("x", 1.0, True),
        (None, 2, False),
    ),
)


def test_header_and_rows_written(tmp_path: Path) -> None:
    """AC-004."""
    path = tmp_path / "sample.csv"
    write_table(_TABLE, path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "a,b,c"
    assert lines[1] == "x,1.0,True"
    assert lines[2] == ",2,False"
    assert len(lines) == 3


def test_repeat_write_is_byte_identical(tmp_path: Path) -> None:
    """AC-005."""
    path_1 = tmp_path / "run1" / "sample.csv"
    path_2 = tmp_path / "run2" / "sample.csv"
    path_1.parent.mkdir()
    path_2.parent.mkdir()

    write_table(_TABLE, path_1)
    write_table(_TABLE, path_2)

    assert path_1.read_bytes() == path_2.read_bytes()


def test_write_tables_creates_one_file_per_table(tmp_path: Path) -> None:
    other = Table(name="other", columns=("x",), rows=((1,), (2,)))
    written = write_tables([_TABLE, other], tmp_path / "out")

    assert written == (tmp_path / "out" / "sample.csv", tmp_path / "out" / "other.csv")
    assert all(path.exists() for path in written)


def test_write_tables_creates_directory(tmp_path: Path) -> None:
    directory = tmp_path / "nested" / "deep"
    write_tables([_TABLE], directory)
    assert (directory / "sample.csv").exists()

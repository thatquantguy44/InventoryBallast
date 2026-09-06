"""CSV output for ``reporting.tables.Table`` (T-004), standard library only.

Deliberately not routed through pandas: the CLI's most useful path should not require the optional
``dataframe`` extra (NFR-001), and ``csv`` costs a few lines. ``adapters.dataframe`` remains
available for callers who genuinely want a frame.

Output is byte-stable across platforms and repeated runs (REQ-009): ``newline=""`` plus an explicit
``lineterminator`` stop the platform's own line ending from leaking in, and the row/column order is
already fixed by ``reporting.tables``.
"""

from __future__ import annotations

import csv
from collections.abc import Sequence
from pathlib import Path

from inventory_optimizer.reporting.tables import Table


def write_table(table: Table, path: Path) -> None:
    """Write one table to ``path``. ``None`` becomes an empty cell and ``bool`` becomes
    ``True``/``False`` -- ``csv``'s own defaults, documented rather than customized."""
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(table.columns)
        writer.writerows(table.rows)


def write_tables(tables: Sequence[Table], directory: Path) -> tuple[Path, ...]:
    """Write each table to ``<directory>/<table name>.csv``, creating the directory if needed.
    Returns the paths written, in the order the tables were given."""
    directory.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for table in tables:
        path = directory / f"{table.name}.csv"
        write_table(table, path)
        written.append(path)
    return tuple(written)


__all__ = ["write_table", "write_tables"]

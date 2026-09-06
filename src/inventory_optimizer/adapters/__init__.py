"""Boundary adapters (Section 7.1: ``adapters`` owns "JSON and optional dataframe conversion",
and must not own "Domain rules or formulation logic").

``csv_io`` uses the standard library only, so the CSV path works with no optional extras
installed. ``dataframe`` is the sole module in this package permitted to import ``pandas``, and
imports it lazily -- the same containment ``solvers/highs.py`` applies to ``highspy``, and what
keeps ``ARC-003``'s "independently installable" guarantee true.

JSON conversion is deliberately *not* a module here: Pydantic v2 already is this package's JSON
transport (``model_dump_json``/``model_validate_json``, used by ``cli.py`` in both directions), so
a wrapper would add indirection without capability. Recorded in
``specs/0008-tabular-result-output/spec.md``'s Non-Goals rather than skipped silently.
"""

from __future__ import annotations

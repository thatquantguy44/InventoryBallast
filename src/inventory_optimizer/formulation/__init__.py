"""Variable indexes and mathematical program assembly (Section 7.1).

Must not own business I/O or reporting. Phase 0A/T07 delivers the generic indexing and sparse-
accumulation infrastructure (``indexes.py``, ``variables.py``, ``rows.py``, ``sparse_builder.py``,
``compiled.py``); the formulation-specific compilers that decide *which* variables/rows/objective
terms a request needs (``lp.py``, and later ``mip.py``/``qp.py``) are T08/T15/T18.
"""

from inventory_optimizer.formulation.compiled import CompiledProblem, ScalingMetadata
from inventory_optimizer.formulation.indexes import RowIndex, RowKey, VariableIndex, VariableKey
from inventory_optimizer.formulation.rows import RowIndexBuilder
from inventory_optimizer.formulation.sparse_builder import SparseBuilder
from inventory_optimizer.formulation.variables import build_variable_index

__all__ = [
    "CompiledProblem",
    "RowIndex",
    "RowIndexBuilder",
    "RowKey",
    "ScalingMetadata",
    "SparseBuilder",
    "VariableIndex",
    "VariableKey",
    "build_variable_index",
]

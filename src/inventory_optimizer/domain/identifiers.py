"""Opaque identifier aliases.

Section 9.1: "IDs are opaque strings; tickers are labels, not join keys." These aliases exist so
call sites document intent; they carry no join or lookup semantics beyond equality.
"""

from __future__ import annotations

InventoryId = str
InventoryPoolId = str
SecurityId = str
RouteId = str
BorrowerId = str
DemandGroupId = str
RequestId = str
CorrelationId = str
IdempotencyKey = str
LimitId = str
PolicyId = str

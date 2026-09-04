"""Platform invocation context (T34; Section 17.5).

The same facade supports in-process, worker, and service deployment shapes; deployment shape must
not change model semantics. This contract carries only opaque references and primitives so it
serializes without importing any platform identity/session object -- ``qr_haven`` (or any other
platform) never appears as an import in this module or anywhere else in the core package.

The optimizer treats ``authorization_reference`` as an input assertion from the platform: it does
not implement user RBAC and never reads platform databases, global process state, or user
sessions directly (Section 17.5).
"""

from __future__ import annotations

from pydantic import AwareDatetime, BaseModel, ConfigDict

from inventory_optimizer.domain.enums import ProblemFamily


class PlatformInvocationContext(BaseModel):
    """Frozen, opaque invocation envelope. See Section 17.5 for the full contract."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str
    correlation_id: str
    idempotency_key: str
    problem_family: ProblemFamily
    as_of: AwareDatetime
    authorization_reference: str
    schema_version: str
    platform_tenant_id: str | None = None
    actor_reference: str | None = None

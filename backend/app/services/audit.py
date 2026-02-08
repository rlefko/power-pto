from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from app.models.audit import AuditLog

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlmodel import SQLModel

    from app.models.enums import AuditAction, AuditEntityType


def model_to_audit_dict(model: SQLModel) -> dict[str, Any]:
    """Serialize a SQLModel instance to a JSON-safe dict for audit logging."""
    data: dict[str, Any] = {}
    for key, value in model.model_dump().items():
        if isinstance(value, uuid.UUID):
            data[key] = str(value)
        elif isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
        else:
            data[key] = value
    return data


async def write_audit_log(
    session: AsyncSession,
    *,
    company_id: uuid.UUID,
    actor_id: uuid.UUID,
    entity_type: AuditEntityType,
    entity_id: uuid.UUID,
    action: AuditAction,
    before_json: dict[str, Any] | None = None,
    after_json: dict[str, Any] | None = None,
) -> AuditLog:
    """Write an immutable audit log entry within the caller's transaction."""
    entry = AuditLog(
        company_id=company_id,
        actor_id=actor_id,
        entity_type=entity_type.value,
        entity_id=entity_id,
        action=action.value,
        before_json=before_json,
        after_json=after_json,
    )
    session.add(entry)
    return entry

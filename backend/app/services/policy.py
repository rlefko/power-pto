# ruff: noqa: TC003
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlmodel import col

from app.exceptions import AppError
from app.models.enums import AccrualMethod, AuditAction, AuditEntityType, PolicyType
from app.models.policy import TimeOffPolicy, TimeOffPolicyVersion
from app.schemas.policy import (
    PolicyListResponse,
    PolicyResponse,
    PolicySettings,
    PolicyVersionListResponse,
    PolicyVersionResponse,
)
from app.services.audit import model_to_audit_dict, write_audit_log

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.auth import AuthContext
    from app.schemas.policy import CreatePolicyRequest, UpdatePolicyRequest

_settings_adapter: TypeAdapter[PolicySettings] = TypeAdapter(PolicySettings)


def _build_version_response(version: TimeOffPolicyVersion) -> PolicyVersionResponse:
    """Build a PolicyVersionResponse from a DB model."""
    settings = _settings_adapter.validate_python(version.settings_json or {})
    return PolicyVersionResponse(
        id=version.id,
        policy_id=version.policy_id,
        version=version.version,
        effective_from=version.effective_from,
        effective_to=version.effective_to,
        type=PolicyType(version.type),
        accrual_method=AccrualMethod(version.accrual_method) if version.accrual_method else None,
        settings=settings,
        created_by=version.created_by,
        change_reason=version.change_reason,
        created_at=version.created_at,
    )


def _build_policy_response(
    policy: TimeOffPolicy,
    current_version: TimeOffPolicyVersion | None,
) -> PolicyResponse:
    """Build a PolicyResponse from DB models."""
    return PolicyResponse(
        id=policy.id,
        company_id=policy.company_id,
        key=policy.key,
        category=policy.category,
        created_at=policy.created_at,
        current_version=_build_version_response(current_version) if current_version else None,
    )


async def create_policy(
    session: AsyncSession,
    auth: AuthContext,
    payload: CreatePolicyRequest,
) -> PolicyResponse:
    """Create a new policy with its initial version (version 1)."""
    existing = await session.execute(
        select(TimeOffPolicy).where(
            col(TimeOffPolicy.company_id) == auth.company_id,
            col(TimeOffPolicy.key) == payload.key,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise AppError("Policy with this key already exists for this company", status_code=409)

    settings = payload.version.settings
    policy_type = settings.type
    accrual_method = getattr(settings, "accrual_method", None)

    policy = TimeOffPolicy(
        company_id=auth.company_id,
        key=payload.key,
        category=payload.category.value,
    )
    session.add(policy)
    await session.flush()

    version = TimeOffPolicyVersion(
        policy_id=policy.id,
        version=1,
        effective_from=payload.version.effective_from,
        type=policy_type,
        accrual_method=accrual_method,
        settings_json=settings.model_dump(mode="json"),
        created_by=auth.user_id,
        change_reason=payload.version.change_reason,
    )
    session.add(version)
    await session.flush()

    # Audit: policy created
    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.POLICY,
        entity_id=policy.id,
        action=AuditAction.CREATE,
        after_json=model_to_audit_dict(policy),
    )
    # Audit: policy version created
    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.POLICY_VERSION,
        entity_id=version.id,
        action=AuditAction.CREATE,
        after_json=model_to_audit_dict(version),
    )

    await session.commit()
    await session.refresh(policy)
    await session.refresh(version)

    return _build_policy_response(policy, version)


async def get_policy(
    session: AsyncSession,
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
) -> PolicyResponse:
    """Fetch a single policy with its current (latest) version."""
    result = await session.execute(
        select(TimeOffPolicy).where(
            col(TimeOffPolicy.id) == policy_id,
            col(TimeOffPolicy.company_id) == company_id,
        )
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        raise AppError("Policy not found", status_code=404)

    current_version = await _get_current_version(session, policy_id)
    return _build_policy_response(policy, current_version)


async def list_policies(
    session: AsyncSession,
    company_id: uuid.UUID,
    offset: int = 0,
    limit: int = 50,
) -> PolicyListResponse:
    """List all policies for a company with their current versions."""
    count_result = await session.execute(
        select(func.count()).select_from(TimeOffPolicy).where(col(TimeOffPolicy.company_id) == company_id)
    )
    total = count_result.scalar_one()

    policies_result = await session.execute(
        select(TimeOffPolicy)
        .where(col(TimeOffPolicy.company_id) == company_id)
        .order_by(col(TimeOffPolicy.created_at))
        .offset(offset)
        .limit(limit)
    )
    policies = list(policies_result.scalars().all())

    items: list[PolicyResponse] = []
    for policy in policies:
        current_version = await _get_current_version(session, policy.id)
        items.append(_build_policy_response(policy, current_version))

    return PolicyListResponse(items=items, total=total)


async def update_policy(
    session: AsyncSession,
    auth: AuthContext,
    policy_id: uuid.UUID,
    payload: UpdatePolicyRequest,
) -> PolicyResponse:
    """Update a policy by creating a new version and end-dating the current one."""
    result = await session.execute(
        select(TimeOffPolicy).where(
            col(TimeOffPolicy.id) == policy_id,
            col(TimeOffPolicy.company_id) == auth.company_id,
        )
    )
    policy = result.scalar_one_or_none()
    if policy is None:
        raise AppError("Policy not found", status_code=404)

    current_version = await _get_current_version(session, policy_id)
    if current_version is None:
        raise AppError("Policy has no current version", status_code=404)

    if payload.version.effective_from < current_version.effective_from:
        raise AppError(
            "New version effective_from must not precede current version's effective_from",
            status_code=400,
        )

    # Capture state before end-dating for audit
    before_version_dict = model_to_audit_dict(current_version)

    # End-date current version
    current_version.effective_to = payload.version.effective_from

    # Derive type and accrual_method from new settings
    settings = payload.version.settings
    policy_type = settings.type
    accrual_method = getattr(settings, "accrual_method", None)

    # Create new version
    new_version = TimeOffPolicyVersion(
        policy_id=policy.id,
        version=current_version.version + 1,
        effective_from=payload.version.effective_from,
        type=policy_type,
        accrual_method=accrual_method,
        settings_json=settings.model_dump(mode="json"),
        created_by=auth.user_id,
        change_reason=payload.version.change_reason,
    )
    session.add(new_version)
    await session.flush()

    # Audit: previous version end-dated
    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.POLICY_VERSION,
        entity_id=current_version.id,
        action=AuditAction.UPDATE,
        before_json=before_version_dict,
        after_json=model_to_audit_dict(current_version),
    )
    # Audit: new version created
    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.POLICY_VERSION,
        entity_id=new_version.id,
        action=AuditAction.CREATE,
        after_json=model_to_audit_dict(new_version),
    )

    await session.commit()
    await session.refresh(policy)
    await session.refresh(new_version)

    return _build_policy_response(policy, new_version)


async def list_policy_versions(
    session: AsyncSession,
    company_id: uuid.UUID,
    policy_id: uuid.UUID,
    offset: int = 0,
    limit: int = 50,
) -> PolicyVersionListResponse:
    """List all versions of a policy ordered by version number descending."""
    # Verify policy exists and belongs to company
    policy_result = await session.execute(
        select(TimeOffPolicy).where(
            col(TimeOffPolicy.id) == policy_id,
            col(TimeOffPolicy.company_id) == company_id,
        )
    )
    if policy_result.scalar_one_or_none() is None:
        raise AppError("Policy not found", status_code=404)

    count_result = await session.execute(
        select(func.count()).select_from(TimeOffPolicyVersion).where(col(TimeOffPolicyVersion.policy_id) == policy_id)
    )
    total = count_result.scalar_one()

    versions_result = await session.execute(
        select(TimeOffPolicyVersion)
        .where(col(TimeOffPolicyVersion.policy_id) == policy_id)
        .order_by(col(TimeOffPolicyVersion.version).desc())
        .offset(offset)
        .limit(limit)
    )
    versions = list(versions_result.scalars().all())

    return PolicyVersionListResponse(
        items=[_build_version_response(v) for v in versions],
        total=total,
    )


async def _get_current_version(
    session: AsyncSession,
    policy_id: uuid.UUID,
) -> TimeOffPolicyVersion | None:
    """Get the current (latest) version of a policy."""
    result = await session.execute(
        select(TimeOffPolicyVersion)
        .where(
            col(TimeOffPolicyVersion.policy_id) == policy_id,
            col(TimeOffPolicyVersion.effective_to).is_(None),
        )
        .order_by(col(TimeOffPolicyVersion.version).desc())
        .limit(1)
    )
    return result.scalar_one_or_none()

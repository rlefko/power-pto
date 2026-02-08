# ruff: noqa: TC003
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pydantic import TypeAdapter
from sqlalchemy import func, select
from sqlmodel import col

from app.exceptions import AppError
from app.models.enums import AccrualMethod, PolicyType
from app.models.policy import TimeOffPolicy, TimeOffPolicyVersion
from app.schemas.policy import (
    PolicyListResponse,
    PolicyResponse,
    PolicySettings,
    PolicyVersionResponse,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.auth import AuthContext
    from app.schemas.policy import CreatePolicyRequest

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

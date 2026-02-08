from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import extract, func, select
from sqlmodel import col

from app.exceptions import AppError
from app.models.enums import AuditAction, AuditEntityType
from app.models.holiday import CompanyHoliday
from app.schemas.holiday import HolidayListResponse, HolidayResponse
from app.services.audit import model_to_audit_dict, write_audit_log

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.schemas.auth import AuthContext
    from app.schemas.holiday import CreateHolidayRequest


def _build_holiday_response(holiday: CompanyHoliday) -> HolidayResponse:
    return HolidayResponse(
        id=holiday.id,
        company_id=holiday.company_id,
        date=holiday.date,
        name=holiday.name,
    )


async def create_holiday(
    session: AsyncSession,
    auth: AuthContext,
    payload: CreateHolidayRequest,
) -> HolidayResponse:
    """Create a company holiday."""
    holiday = CompanyHoliday(
        company_id=auth.company_id,
        date=payload.date,
        name=payload.name,
    )
    session.add(holiday)

    try:
        await session.flush()
    except Exception:
        await session.rollback()
        raise AppError("Holiday already exists for this date", status_code=409) from None

    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.HOLIDAY,
        entity_id=holiday.id,
        action=AuditAction.CREATE,
        after_json=model_to_audit_dict(holiday),
    )

    await session.commit()
    await session.refresh(holiday)
    return _build_holiday_response(holiday)


async def list_holidays(
    session: AsyncSession,
    company_id: uuid.UUID,
    year: int | None = None,
    offset: int = 0,
    limit: int = 50,
) -> HolidayListResponse:
    """List company holidays with optional year filter."""
    base_filter = [col(CompanyHoliday.company_id) == company_id]

    if year is not None:
        base_filter.append(extract("year", col(CompanyHoliday.date)) == year)

    count_result = await session.execute(select(func.count()).select_from(CompanyHoliday).where(*base_filter))
    total = count_result.scalar_one()

    result = await session.execute(
        select(CompanyHoliday).where(*base_filter).order_by(col(CompanyHoliday.date)).offset(offset).limit(limit)
    )
    holidays = list(result.scalars().all())

    return HolidayListResponse(
        items=[_build_holiday_response(h) for h in holidays],
        total=total,
    )


async def get_holiday(
    session: AsyncSession,
    company_id: uuid.UUID,
    holiday_id: uuid.UUID,
) -> CompanyHoliday:
    """Get a single holiday or raise 404."""
    result = await session.execute(
        select(CompanyHoliday).where(
            col(CompanyHoliday.id) == holiday_id,
            col(CompanyHoliday.company_id) == company_id,
        )
    )
    holiday = result.scalar_one_or_none()
    if holiday is None:
        raise AppError("Holiday not found", status_code=404)
    return holiday


async def delete_holiday(
    session: AsyncSession,
    auth: AuthContext,
    holiday_id: uuid.UUID,
) -> None:
    """Delete a company holiday."""
    holiday = await get_holiday(session, auth.company_id, holiday_id)

    await write_audit_log(
        session,
        company_id=auth.company_id,
        actor_id=auth.user_id,
        entity_type=AuditEntityType.HOLIDAY,
        entity_id=holiday.id,
        action=AuditAction.DELETE,
        before_json=model_to_audit_dict(holiday),
    )

    await session.delete(holiday)
    await session.commit()

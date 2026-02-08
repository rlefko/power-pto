# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlmodel import col

from app.exceptions import AppError
from app.models.holiday import CompanyHoliday
from app.services.employee import get_employee_service

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# Default work schedule constants.
_DEFAULT_WORKDAY_MINUTES = 480
_DEFAULT_TIMEZONE = "UTC"
_WORK_START_HOUR = 9
_WORK_START_MINUTE = 0


async def _fetch_holiday_dates(
    session: AsyncSession,
    company_id: uuid.UUID,
    start_date: date,
    end_date: date,
) -> set[date]:
    """Fetch company holidays in the given date range."""
    result = await session.execute(
        select(col(CompanyHoliday.date)).where(
            col(CompanyHoliday.company_id) == company_id,
            col(CompanyHoliday.date) >= start_date,
            col(CompanyHoliday.date) <= end_date,
        )
    )
    return {row[0] for row in result.all()}


def _compute_day_minutes(
    current_date: date,
    local_start: datetime,
    local_end: datetime,
    workday_minutes: int,
    tz: ZoneInfo,
) -> int:
    """Compute the overlap minutes between the request and a single workday."""
    day_work_start = datetime(
        current_date.year,
        current_date.month,
        current_date.day,
        _WORK_START_HOUR,
        _WORK_START_MINUTE,
        tzinfo=tz,
    )
    day_work_end = day_work_start + timedelta(minutes=workday_minutes)

    overlap_start = max(local_start, day_work_start)
    overlap_end = min(local_end, day_work_end)

    if overlap_start >= overlap_end:
        return 0

    return int((overlap_end - overlap_start).total_seconds()) // 60


async def calculate_requested_minutes(
    session: AsyncSession,
    company_id: uuid.UUID,
    employee_id: uuid.UUID,
    start_at: datetime,
    end_at: datetime,
) -> int:
    """Calculate working minutes between start_at and end_at.

    Uses the employee's schedule (workday_minutes, timezone) from the
    Employee Service, falling back to defaults (480 min, UTC) when the
    employee record is not found.

    Excludes weekends (Sat/Sun) and company holidays.
    Clips request boundaries to the workday window (default 09:00 start).
    """
    # 1. Resolve employee schedule.
    employee_service = get_employee_service()
    employee = await employee_service.get_employee(company_id, employee_id)

    workday_minutes = employee.workday_minutes if employee else _DEFAULT_WORKDAY_MINUTES
    tz_name = employee.timezone if employee else _DEFAULT_TIMEZONE
    tz = ZoneInfo(tz_name)

    # 2. Convert to employee timezone.
    local_start = start_at.astimezone(tz)
    local_end = end_at.astimezone(tz)

    # 3. Fetch holidays in range.
    start_date = local_start.date()
    end_date = local_end.date()
    holiday_dates = await _fetch_holiday_dates(session, company_id, start_date, end_date)

    # 4. Iterate calendar days and accumulate work minutes.
    total_minutes = 0
    current_date = start_date
    one_day = timedelta(days=1)

    while current_date <= end_date:
        # Skip weekends.
        if current_date.weekday() >= 5:
            current_date += one_day
            continue

        # Skip holidays.
        if current_date in holiday_dates:
            current_date += one_day
            continue

        total_minutes += _compute_day_minutes(current_date, local_start, local_end, workday_minutes, tz)
        current_date += one_day

    if total_minutes <= 0:
        raise AppError("Request covers no working time after excluding weekends and holidays", status_code=400)

    return total_minutes

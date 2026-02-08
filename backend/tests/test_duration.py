"""Tests for the request duration calculator (schedule + holiday awareness)."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import pytest

from app.exceptions import AppError
from app.models.holiday import CompanyHoliday
from app.services.duration import calculate_requested_minutes, localize_request_times
from app.services.employee import EmployeeInfo, InMemoryEmployeeService, set_employee_service

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.ext.asyncio import AsyncSession

COMPANY_ID = uuid.uuid4()
EMPLOYEE_ID = uuid.uuid4()

# Use a fixed timezone for deterministic tests.
_TZ = ZoneInfo("America/New_York")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _seed_employee_service() -> Iterator[None]:
    """Seed the in-memory employee service for every test."""
    svc = InMemoryEmployeeService()
    svc.seed(
        EmployeeInfo(
            id=EMPLOYEE_ID,
            company_id=COMPANY_ID,
            first_name="Test",
            last_name="User",
            email="test@example.com",
            pay_type="SALARY",
            workday_minutes=480,
            timezone="America/New_York",
        )
    )
    set_employee_service(svc)
    yield
    set_employee_service(InMemoryEmployeeService())


async def _add_holiday(session: AsyncSession, dt: date, name: str = "Holiday") -> None:
    """Insert a company holiday."""
    session.add(CompanyHoliday(company_id=COMPANY_ID, date=dt, name=name))
    await session.flush()


def _dt(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """Create a timezone-aware datetime in America/New_York."""
    return datetime(year, month, day, hour, minute, tzinfo=_TZ)


# ---------------------------------------------------------------------------
# Full-day tests
# ---------------------------------------------------------------------------


async def test_single_full_workday(db_session: AsyncSession) -> None:
    """Monday 9am-5pm = 480 minutes."""
    # 2025-01-06 is a Monday.
    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 6, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 480


async def test_two_consecutive_workdays(db_session: AsyncSession) -> None:
    """Monday 9am through Tuesday 5pm = 960 minutes."""
    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 7, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 960


async def test_full_work_week(db_session: AsyncSession) -> None:
    """Monday 9am through Friday 5pm = 5 * 480 = 2400 minutes."""
    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 10, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 2400


async def test_two_work_weeks(db_session: AsyncSession) -> None:
    """Two full work weeks = 10 * 480 = 4800 minutes."""
    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 17, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 4800


# ---------------------------------------------------------------------------
# Weekend exclusion
# ---------------------------------------------------------------------------


async def test_weekend_days_excluded(db_session: AsyncSession) -> None:
    """Friday through Monday: only Friday and Monday count (960 min)."""
    # 2025-01-10 = Friday, 2025-01-13 = Monday
    start = _dt(2025, 1, 10, 9, 0)
    end = _dt(2025, 1, 13, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 960


async def test_weekend_only_raises_error(db_session: AsyncSession) -> None:
    """Request spanning only Saturday and Sunday yields zero working time."""
    # 2025-01-11 = Saturday, 2025-01-12 = Sunday
    start = _dt(2025, 1, 11, 9, 0)
    end = _dt(2025, 1, 12, 17, 0)

    with pytest.raises(AppError, match="no working time"):
        await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)


# ---------------------------------------------------------------------------
# Partial day tests
# ---------------------------------------------------------------------------


async def test_partial_day_afternoon(db_session: AsyncSession) -> None:
    """Monday 12pm-5pm = 300 minutes."""
    start = _dt(2025, 1, 6, 12, 0)
    end = _dt(2025, 1, 6, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 300


async def test_partial_day_morning(db_session: AsyncSession) -> None:
    """Monday 9am-12pm = 180 minutes."""
    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 6, 12, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 180


async def test_request_clipped_to_work_hours(db_session: AsyncSession) -> None:
    """Request 7am-10am is clipped to 9am-10am = 60 minutes."""
    start = _dt(2025, 1, 6, 7, 0)
    end = _dt(2025, 1, 6, 10, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 60


async def test_request_outside_work_hours_raises_error(db_session: AsyncSession) -> None:
    """Request entirely outside work hours (6pm-8pm) = 0 working time."""
    start = _dt(2025, 1, 6, 18, 0)
    end = _dt(2025, 1, 6, 20, 0)

    with pytest.raises(AppError, match="no working time"):
        await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)


async def test_multi_day_partial_first_and_last(db_session: AsyncSession) -> None:
    """Monday 2pm through Wednesday 11am = Mon(3h) + Tue(8h) + Wed(2h) = 780 min."""
    start = _dt(2025, 1, 6, 14, 0)
    end = _dt(2025, 1, 8, 11, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 780


# ---------------------------------------------------------------------------
# Holiday exclusion
# ---------------------------------------------------------------------------


async def test_holiday_excluded_single_day(db_session: AsyncSession) -> None:
    """A workday that is a holiday yields zero working time."""
    await _add_holiday(db_session, date(2025, 1, 6), "Test Holiday")

    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 6, 17, 0)

    with pytest.raises(AppError, match="no working time"):
        await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)


async def test_holiday_excluded_from_range(db_session: AsyncSession) -> None:
    """5-day week with 1 holiday = 4 * 480 = 1920 minutes."""
    await _add_holiday(db_session, date(2025, 1, 8), "Mid-Week Holiday")

    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 10, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 1920


async def test_multiple_holidays_excluded(db_session: AsyncSession) -> None:
    """5-day week with 2 holidays = 3 * 480 = 1440 minutes."""
    await _add_holiday(db_session, date(2025, 1, 7), "Holiday 1")
    await _add_holiday(db_session, date(2025, 1, 9), "Holiday 2")

    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 10, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 1440


# ---------------------------------------------------------------------------
# Custom workday minutes
# ---------------------------------------------------------------------------


async def test_custom_workday_six_hour_day(db_session: AsyncSession) -> None:
    """Employee with 360 min (6h) workday: 9am-3pm = 360 per day."""
    svc = InMemoryEmployeeService()
    svc.seed(
        EmployeeInfo(
            id=EMPLOYEE_ID,
            company_id=COMPANY_ID,
            first_name="Short",
            last_name="Day",
            email="short@example.com",
            pay_type="HOURLY",
            workday_minutes=360,
            timezone="America/New_York",
        )
    )
    set_employee_service(svc)

    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 6, 17, 0)

    # Even though request goes to 5pm, workday ends at 3pm.
    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 360


async def test_custom_workday_two_days(db_session: AsyncSession) -> None:
    """Two days with 6h workday = 720 minutes."""
    svc = InMemoryEmployeeService()
    svc.seed(
        EmployeeInfo(
            id=EMPLOYEE_ID,
            company_id=COMPANY_ID,
            first_name="Short",
            last_name="Day",
            email="short@example.com",
            pay_type="HOURLY",
            workday_minutes=360,
            timezone="America/New_York",
        )
    )
    set_employee_service(svc)

    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 7, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 720


# ---------------------------------------------------------------------------
# Employee not found (defaults)
# ---------------------------------------------------------------------------


async def test_employee_not_found_uses_defaults(db_session: AsyncSession) -> None:
    """Unknown employee uses default 480 min workday / UTC timezone."""
    unknown = uuid.uuid4()
    # 2025-01-06 is a Monday.  UTC 9am-5pm.
    start = datetime(2025, 1, 6, 9, 0, tzinfo=UTC)
    end = datetime(2025, 1, 6, 17, 0, tzinfo=UTC)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, unknown, start, end)
    assert result == 480


# ---------------------------------------------------------------------------
# DST edge cases
# ---------------------------------------------------------------------------


async def test_spring_forward_day(db_session: AsyncSession) -> None:
    """Request on spring-forward day (Mar 9, 2025 in America/New_York).

    The day still has a full 8h workday; DST shift happens at 2am.
    """
    start = _dt(2025, 3, 10, 9, 0)  # Monday after spring forward
    end = _dt(2025, 3, 10, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 480


async def test_fall_back_day(db_session: AsyncSession) -> None:
    """Request on fall-back day (Nov 2, 2025 in America/New_York).

    The day still has a full 8h workday; DST shift happens at 2am.
    """
    start = _dt(2025, 11, 3, 9, 0)  # Monday after fall back
    end = _dt(2025, 11, 3, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 480


# ---------------------------------------------------------------------------
# Naive datetime handling (frontend datetime-local input)
# ---------------------------------------------------------------------------


async def test_naive_datetime_treated_as_employee_timezone(db_session: AsyncSession) -> None:
    """Naive datetimes (no tzinfo) are interpreted in the employee's timezone.

    The frontend datetime-local input sends naive strings like "2025-01-06T09:00".
    These should be treated as 9am in the employee's timezone (America/New_York),
    not the server's local time or UTC.
    """
    # Naive datetime — no tzinfo attached.
    start = datetime(2025, 1, 6, 9, 0)
    end = datetime(2025, 1, 6, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 480


async def test_naive_datetime_multi_day(db_session: AsyncSession) -> None:
    """Naive datetimes over multiple days produce the same result as aware ones."""
    start = datetime(2025, 1, 6, 9, 0)
    end = datetime(2025, 1, 7, 17, 0)

    result = await calculate_requested_minutes(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)
    assert result == 960


async def test_localize_request_times_naive(db_session: AsyncSession) -> None:
    """Naive datetimes are localized to the employee's timezone."""
    start = datetime(2025, 1, 6, 9, 0)
    end = datetime(2025, 1, 6, 17, 0)

    loc_start, loc_end = await localize_request_times(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)

    assert loc_start.tzinfo == _TZ
    assert loc_end.tzinfo == _TZ
    assert loc_start.hour == 9
    assert loc_end.hour == 17


async def test_localize_request_times_aware_unchanged(db_session: AsyncSession) -> None:
    """Already timezone-aware datetimes are returned unchanged."""
    start = _dt(2025, 1, 6, 9, 0)
    end = _dt(2025, 1, 6, 17, 0)

    loc_start, loc_end = await localize_request_times(db_session, COMPANY_ID, EMPLOYEE_ID, start, end)

    assert loc_start == start
    assert loc_end == end

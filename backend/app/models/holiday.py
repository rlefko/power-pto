# ruff: noqa: TC003
from __future__ import annotations

import datetime
import uuid

import sqlalchemy as sa
from sqlmodel import Field

from app.models.base import UUIDBase


class CompanyHoliday(UUIDBase, table=True):
    """A company-specific holiday that excludes days from time-off deductions."""

    __tablename__ = "company_holiday"
    __table_args__ = (sa.UniqueConstraint("company_id", "date", name="uq_holiday_company_date"),)

    company_id: uuid.UUID = Field(index=True)
    date: datetime.date
    name: str = Field(max_length=255)

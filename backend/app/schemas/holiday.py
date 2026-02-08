# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


class CreateHolidayRequest(BaseModel):
    """Request body for creating a company holiday."""

    date: date
    name: str = Field(min_length=1, max_length=255)


class HolidayResponse(BaseModel):
    """Response schema for a company holiday."""

    id: uuid.UUID
    company_id: uuid.UUID
    date: date
    name: str


class HolidayListResponse(BaseModel):
    """Paginated list of company holidays."""

    items: list[HolidayResponse]
    total: int

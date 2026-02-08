# ruff: noqa: TC003
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, Discriminator, Field, Tag, model_validator

from app.models.enums import (
    AccrualFrequency,
    AccrualMethod,
    AccrualTiming,
    DisplayUnit,
    PolicyCategory,
    PolicyType,
    ProrationMethod,
)

# ---------------------------------------------------------------------------
# Settings sub-schemas
# ---------------------------------------------------------------------------


class TenureTier(BaseModel):
    """Accrual rate override based on employee tenure."""

    min_months: int = Field(ge=0)
    accrual_rate_minutes: int = Field(gt=0, description="Accrual rate in minutes per period at this tier")


class CarryoverSettings(BaseModel):
    """Year-end carryover configuration."""

    enabled: bool = False
    cap_minutes: int | None = Field(default=None, ge=0)
    expires_after_days: int | None = Field(default=None, gt=0)


class ExpirationSettings(BaseModel):
    """Balance expiration configuration."""

    enabled: bool = False
    expires_after_days: int | None = Field(default=None, gt=0)
    expires_on_month: int | None = Field(default=None, ge=1, le=12)
    expires_on_day: int | None = Field(default=None, ge=1, le=31)

    @model_validator(mode="after")
    def _validate_expiration(self) -> Self:
        if self.enabled and self.expires_after_days is None and self.expires_on_month is None:
            msg = "Enabled expiration requires either expires_after_days or expires_on_month/day"
            raise ValueError(msg)
        if self.expires_on_month is not None and self.expires_on_day is None:
            msg = "expires_on_day is required when expires_on_month is set"
            raise ValueError(msg)
        if self.expires_on_day is not None and self.expires_on_month is None:
            msg = "expires_on_month is required when expires_on_day is set"
            raise ValueError(msg)
        return self


class AccrualRatio(BaseModel):
    """Hours-worked accrual ratio: accrue X minutes per Y minutes worked."""

    accrue_minutes: int = Field(gt=0)
    per_worked_minutes: int = Field(gt=0)


# ---------------------------------------------------------------------------
# Per-type policy settings (discriminated union)
# ---------------------------------------------------------------------------


class UnlimitedSettings(BaseModel):
    """Settings for unlimited time-off policies."""

    type: Literal["UNLIMITED"] = "UNLIMITED"
    unit: DisplayUnit = DisplayUnit.DAYS


class TimeAccrualSettings(BaseModel):
    """Settings for time-based accrual policies."""

    type: Literal["ACCRUAL"] = "ACCRUAL"
    accrual_method: Literal["TIME"] = "TIME"
    unit: DisplayUnit = DisplayUnit.DAYS
    accrual_frequency: AccrualFrequency
    accrual_timing: AccrualTiming = AccrualTiming.START_OF_PERIOD
    rate_minutes_per_year: int | None = Field(default=None, gt=0)
    rate_minutes_per_month: int | None = Field(default=None, gt=0)
    rate_minutes_per_day: int | None = Field(default=None, gt=0)
    proration: ProrationMethod = ProrationMethod.DAYS_ACTIVE
    allow_negative: bool = False
    negative_limit_minutes: int | None = Field(default=None, ge=0)
    bank_cap_minutes: int | None = Field(default=None, ge=0)
    tenure_tiers: list[TenureTier] = []
    carryover: CarryoverSettings = Field(default_factory=CarryoverSettings)
    expiration: ExpirationSettings = Field(default_factory=ExpirationSettings)

    @model_validator(mode="after")
    def _validate_rate(self) -> Self:
        rate_fields = {
            AccrualFrequency.YEARLY: self.rate_minutes_per_year,
            AccrualFrequency.MONTHLY: self.rate_minutes_per_month,
            AccrualFrequency.DAILY: self.rate_minutes_per_day,
        }
        provided = {k for k, v in rate_fields.items() if v is not None}
        if len(provided) == 0:
            msg = "At least one rate field must be set"
            raise ValueError(msg)
        if len(provided) > 1:
            msg = "Only one rate field should be set"
            raise ValueError(msg)
        expected = self.accrual_frequency
        if expected not in provided:
            msg = f"rate_minutes_per_{expected.value.lower()} must be set for {expected.value} frequency"
            raise ValueError(msg)
        return self


class HoursWorkedAccrualSettings(BaseModel):
    """Settings for hours-worked accrual policies."""

    type: Literal["ACCRUAL"] = "ACCRUAL"
    accrual_method: Literal["HOURS_WORKED"] = "HOURS_WORKED"
    unit: DisplayUnit = DisplayUnit.HOURS
    accrual_ratio: AccrualRatio
    allow_negative: bool = False
    negative_limit_minutes: int | None = Field(default=None, ge=0)
    bank_cap_minutes: int | None = Field(default=None, ge=0)
    tenure_tiers: list[TenureTier] = []
    carryover: CarryoverSettings = Field(default_factory=CarryoverSettings)
    expiration: ExpirationSettings = Field(default_factory=ExpirationSettings)


def _settings_discriminator(v: Any) -> str:
    """Discriminate policy settings by type + accrual_method."""
    if isinstance(v, dict):
        t = v.get("type", "")
        m = v.get("accrual_method")
    else:
        t = getattr(v, "type", "")
        m = getattr(v, "accrual_method", None)
    if t == "UNLIMITED":
        return "unlimited"
    if t == "ACCRUAL" and m == "TIME":
        return "time"
    if t == "ACCRUAL" and m == "HOURS_WORKED":
        return "hours_worked"
    return "unknown"


PolicySettings = Annotated[
    Annotated[UnlimitedSettings, Tag("unlimited")]
    | Annotated[TimeAccrualSettings, Tag("time")]
    | Annotated[HoursWorkedAccrualSettings, Tag("hours_worked")],
    Discriminator(_settings_discriminator),
]

# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------


class PolicyVersionInput(BaseModel):
    """Input for creating a policy version (used in both create and update)."""

    effective_from: date
    settings: PolicySettings
    change_reason: str | None = None


class CreatePolicyRequest(BaseModel):
    """Request body for creating a new policy."""

    key: str = Field(min_length=1, max_length=255)
    category: PolicyCategory
    version: PolicyVersionInput


class UpdatePolicyRequest(BaseModel):
    """Request body for updating a policy (creates a new version)."""

    version: PolicyVersionInput


class PolicyVersionResponse(BaseModel):
    """Response schema for a policy version."""

    id: uuid.UUID
    policy_id: uuid.UUID
    version: int
    effective_from: date
    effective_to: date | None
    type: PolicyType
    accrual_method: AccrualMethod | None
    settings: PolicySettings
    created_by: uuid.UUID
    change_reason: str | None
    created_at: datetime


class PolicyResponse(BaseModel):
    """Response schema for a policy with its current version."""

    id: uuid.UUID
    company_id: uuid.UUID
    key: str
    category: PolicyCategory
    created_at: datetime
    current_version: PolicyVersionResponse | None


class PolicyListResponse(BaseModel):
    """Paginated list of policies."""

    items: list[PolicyResponse]
    total: int


class PolicyVersionListResponse(BaseModel):
    """Paginated list of policy versions."""

    items: list[PolicyVersionResponse]
    total: int

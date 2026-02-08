"""Unit tests for Pydantic policy settings and API schemas."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import TypeAdapter, ValidationError

from app.models.enums import AccrualFrequency, AccrualTiming, DisplayUnit, PolicyCategory, ProrationMethod
from app.schemas.policy import (
    AccrualRatio,
    CarryoverSettings,
    CreatePolicyRequest,
    ExpirationSettings,
    HoursWorkedAccrualSettings,
    PolicySettings,
    PolicyVersionInput,
    TenureTier,
    TimeAccrualSettings,
    UnlimitedSettings,
    UpdatePolicyRequest,
)

_adapter: TypeAdapter[PolicySettings] = TypeAdapter(PolicySettings)

# ---------------------------------------------------------------------------
# UnlimitedSettings
# ---------------------------------------------------------------------------


def test_unlimited_settings_valid() -> None:
    s = UnlimitedSettings()
    assert s.type == "UNLIMITED"
    assert s.unit == DisplayUnit.DAYS


def test_unlimited_settings_custom_unit() -> None:
    s = UnlimitedSettings(unit=DisplayUnit.HOURS)
    assert s.unit == DisplayUnit.HOURS


# ---------------------------------------------------------------------------
# TimeAccrualSettings
# ---------------------------------------------------------------------------


def test_time_accrual_settings_valid_yearly() -> None:
    s = TimeAccrualSettings(
        accrual_frequency=AccrualFrequency.YEARLY,
        rate_minutes_per_year=9600,
    )
    assert s.type == "ACCRUAL"
    assert s.accrual_method == "TIME"
    assert s.rate_minutes_per_year == 9600
    assert s.accrual_timing == AccrualTiming.START_OF_PERIOD
    assert s.proration == ProrationMethod.DAYS_ACTIVE


def test_time_accrual_settings_valid_monthly() -> None:
    s = TimeAccrualSettings(
        accrual_frequency=AccrualFrequency.MONTHLY,
        rate_minutes_per_month=800,
    )
    assert s.rate_minutes_per_month == 800


def test_time_accrual_settings_valid_daily() -> None:
    s = TimeAccrualSettings(
        accrual_frequency=AccrualFrequency.DAILY,
        rate_minutes_per_day=40,
    )
    assert s.rate_minutes_per_day == 40


def test_time_accrual_settings_requires_matching_rate_field() -> None:
    with pytest.raises(ValidationError, match="rate_minutes_per_yearly"):
        TimeAccrualSettings(
            accrual_frequency=AccrualFrequency.YEARLY,
            rate_minutes_per_month=800,
        )


def test_time_accrual_settings_rejects_no_rate() -> None:
    with pytest.raises(ValidationError, match="At least one rate field must be set"):
        TimeAccrualSettings(
            accrual_frequency=AccrualFrequency.YEARLY,
        )


def test_time_accrual_settings_rejects_multiple_rate_fields() -> None:
    with pytest.raises(ValidationError, match="Only one rate field should be set"):
        TimeAccrualSettings(
            accrual_frequency=AccrualFrequency.YEARLY,
            rate_minutes_per_year=9600,
            rate_minutes_per_month=800,
        )


def test_time_accrual_settings_full_config() -> None:
    s = TimeAccrualSettings(
        accrual_frequency=AccrualFrequency.MONTHLY,
        accrual_timing=AccrualTiming.END_OF_PERIOD,
        rate_minutes_per_month=800,
        proration=ProrationMethod.NONE,
        allow_negative=True,
        negative_limit_minutes=480,
        bank_cap_minutes=14400,
        tenure_tiers=[TenureTier(min_months=12, accrual_rate_minutes=960)],
        carryover=CarryoverSettings(enabled=True, cap_minutes=4800),
        expiration=ExpirationSettings(enabled=True, expires_after_days=90),
    )
    assert s.allow_negative is True
    assert s.negative_limit_minutes == 480
    assert s.bank_cap_minutes == 14400
    assert len(s.tenure_tiers) == 1
    assert s.carryover.enabled is True
    assert s.expiration.enabled is True


# ---------------------------------------------------------------------------
# HoursWorkedAccrualSettings
# ---------------------------------------------------------------------------


def test_hours_worked_settings_valid() -> None:
    s = HoursWorkedAccrualSettings(
        accrual_ratio=AccrualRatio(accrue_minutes=60, per_worked_minutes=1440),
    )
    assert s.type == "ACCRUAL"
    assert s.accrual_method == "HOURS_WORKED"
    assert s.accrual_ratio.accrue_minutes == 60
    assert s.accrual_ratio.per_worked_minutes == 1440


def test_hours_worked_settings_with_all_fields() -> None:
    s = HoursWorkedAccrualSettings(
        accrual_ratio=AccrualRatio(accrue_minutes=60, per_worked_minutes=1440),
        allow_negative=True,
        negative_limit_minutes=240,
        bank_cap_minutes=7200,
        tenure_tiers=[TenureTier(min_months=0, accrual_rate_minutes=30)],
        carryover=CarryoverSettings(enabled=True, cap_minutes=2400, expires_after_days=60),
        expiration=ExpirationSettings(enabled=True, expires_on_month=12, expires_on_day=31),
    )
    assert s.allow_negative is True
    assert s.bank_cap_minutes == 7200


# ---------------------------------------------------------------------------
# Discriminated union
# ---------------------------------------------------------------------------


def test_discriminated_union_unlimited() -> None:
    data = {"type": "UNLIMITED"}
    result = _adapter.validate_python(data)
    assert isinstance(result, UnlimitedSettings)


def test_discriminated_union_time_accrual() -> None:
    data = {
        "type": "ACCRUAL",
        "accrual_method": "TIME",
        "accrual_frequency": "MONTHLY",
        "rate_minutes_per_month": 800,
    }
    result = _adapter.validate_python(data)
    assert isinstance(result, TimeAccrualSettings)


def test_discriminated_union_hours_worked() -> None:
    data = {
        "type": "ACCRUAL",
        "accrual_method": "HOURS_WORKED",
        "accrual_ratio": {"accrue_minutes": 60, "per_worked_minutes": 1440},
    }
    result = _adapter.validate_python(data)
    assert isinstance(result, HoursWorkedAccrualSettings)


def test_discriminated_union_rejects_unknown_type() -> None:
    data = {"type": "INVALID"}
    with pytest.raises(ValidationError):
        _adapter.validate_python(data)


def test_discriminated_union_from_json() -> None:
    data = {"type": "UNLIMITED", "unit": "HOURS"}
    result = _adapter.validate_json('{"type": "UNLIMITED", "unit": "HOURS"}')
    assert isinstance(result, UnlimitedSettings)
    assert result.unit == DisplayUnit.HOURS
    result2 = _adapter.validate_python(data)
    assert isinstance(result2, UnlimitedSettings)


# ---------------------------------------------------------------------------
# Sub-schema validation
# ---------------------------------------------------------------------------


def test_tenure_tier_valid() -> None:
    t = TenureTier(min_months=12, accrual_rate_minutes=960)
    assert t.min_months == 12


def test_tenure_tier_rejects_negative_months() -> None:
    with pytest.raises(ValidationError):
        TenureTier(min_months=-1, accrual_rate_minutes=960)


def test_tenure_tier_rejects_zero_rate() -> None:
    with pytest.raises(ValidationError):
        TenureTier(min_months=0, accrual_rate_minutes=0)


def test_carryover_defaults() -> None:
    c = CarryoverSettings()
    assert c.enabled is False
    assert c.cap_minutes is None
    assert c.expires_after_days is None


def test_expiration_defaults() -> None:
    e = ExpirationSettings()
    assert e.enabled is False
    assert e.expires_after_days is None


def test_expiration_enabled_requires_config() -> None:
    with pytest.raises(ValidationError, match="expires_after_days or expires_on_month"):
        ExpirationSettings(enabled=True)


def test_expiration_month_requires_day() -> None:
    with pytest.raises(ValidationError, match="expires_on_day is required"):
        ExpirationSettings(expires_on_month=12)


def test_expiration_day_requires_month() -> None:
    with pytest.raises(ValidationError, match="expires_on_month is required"):
        ExpirationSettings(expires_on_day=31)


def test_accrual_ratio_rejects_zero() -> None:
    with pytest.raises(ValidationError):
        AccrualRatio(accrue_minutes=0, per_worked_minutes=1440)


# ---------------------------------------------------------------------------
# API request schemas
# ---------------------------------------------------------------------------


def test_create_policy_request_unlimited() -> None:
    req = CreatePolicyRequest(
        key="unlimited-vacation",
        category=PolicyCategory.VACATION,
        version=PolicyVersionInput(
            effective_from=date(2025, 1, 1),
            settings=UnlimitedSettings(),
        ),
    )
    assert req.key == "unlimited-vacation"
    assert isinstance(req.version.settings, UnlimitedSettings)


def test_create_policy_request_accrual_time() -> None:
    req = CreatePolicyRequest(
        key="vacation-ft",
        category=PolicyCategory.VACATION,
        version=PolicyVersionInput(
            effective_from=date(2025, 1, 1),
            settings=TimeAccrualSettings(
                accrual_frequency=AccrualFrequency.MONTHLY,
                rate_minutes_per_month=800,
            ),
            change_reason="Initial policy creation",
        ),
    )
    assert isinstance(req.version.settings, TimeAccrualSettings)
    assert req.version.change_reason == "Initial policy creation"


def test_create_policy_request_accrual_hours_worked() -> None:
    req = CreatePolicyRequest(
        key="sick-hourly",
        category=PolicyCategory.SICK,
        version=PolicyVersionInput(
            effective_from=date(2025, 1, 1),
            settings=HoursWorkedAccrualSettings(
                accrual_ratio=AccrualRatio(accrue_minutes=60, per_worked_minutes=1440),
            ),
        ),
    )
    assert isinstance(req.version.settings, HoursWorkedAccrualSettings)


def test_create_policy_request_rejects_empty_key() -> None:
    with pytest.raises(ValidationError):
        CreatePolicyRequest(
            key="",
            category=PolicyCategory.VACATION,
            version=PolicyVersionInput(
                effective_from=date(2025, 1, 1),
                settings=UnlimitedSettings(),
            ),
        )


def test_create_policy_request_rejects_invalid_category() -> None:
    with pytest.raises(ValidationError):
        CreatePolicyRequest(
            key="test",
            category="INVALID",  # ty: ignore[invalid-argument-type]
            version=PolicyVersionInput(
                effective_from=date(2025, 1, 1),
                settings=UnlimitedSettings(),
            ),
        )


def test_update_policy_request_valid() -> None:
    req = UpdatePolicyRequest(
        version=PolicyVersionInput(
            effective_from=date(2025, 7, 1),
            settings=TimeAccrualSettings(
                accrual_frequency=AccrualFrequency.YEARLY,
                rate_minutes_per_year=9600,
            ),
            change_reason="Increased accrual rate",
        ),
    )
    assert req.version.change_reason == "Increased accrual rate"


def test_policy_version_input_derives_type() -> None:
    v = PolicyVersionInput(
        effective_from=date(2025, 1, 1),
        settings=UnlimitedSettings(),
    )
    assert v.settings.type == "UNLIMITED"

    v2 = PolicyVersionInput(
        effective_from=date(2025, 1, 1),
        settings=TimeAccrualSettings(
            accrual_frequency=AccrualFrequency.MONTHLY,
            rate_minutes_per_month=800,
        ),
    )
    assert v2.settings.type == "ACCRUAL"
    assert isinstance(v2.settings, TimeAccrualSettings)
    assert v2.settings.accrual_method == "TIME"


def test_create_policy_request_roundtrip_json() -> None:
    """Ensure the schema can round-trip through JSON serialization."""
    req = CreatePolicyRequest(
        key="vacation-ft",
        category=PolicyCategory.VACATION,
        version=PolicyVersionInput(
            effective_from=date(2025, 1, 1),
            settings=TimeAccrualSettings(
                accrual_frequency=AccrualFrequency.MONTHLY,
                rate_minutes_per_month=800,
                bank_cap_minutes=14400,
            ),
        ),
    )
    json_str = req.model_dump_json()
    restored = CreatePolicyRequest.model_validate_json(json_str)
    assert isinstance(restored.version.settings, TimeAccrualSettings)
    assert isinstance(restored.version.settings, TimeAccrualSettings)
    assert restored.version.settings.rate_minutes_per_month == 800


def test_discriminated_union_roundtrip_via_dict() -> None:
    """Ensure settings can round-trip through dict serialization (for settings_json storage)."""
    original = TimeAccrualSettings(
        accrual_frequency=AccrualFrequency.YEARLY,
        rate_minutes_per_year=9600,
        bank_cap_minutes=14400,
    )
    as_dict = original.model_dump(mode="json")
    restored = _adapter.validate_python(as_dict)
    assert isinstance(restored, TimeAccrualSettings)
    assert restored.rate_minutes_per_year == 9600


def test_version_input_no_extra_fields() -> None:
    """PolicyVersionInput should only accept known fields."""
    v = PolicyVersionInput(
        effective_from=date(2025, 1, 1),
        settings=UnlimitedSettings(),
        change_reason="test",
    )
    assert v.change_reason == "test"

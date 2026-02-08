from __future__ import annotations

import enum


class PolicyCategory(enum.StrEnum):
    """Category of a time-off policy."""

    VACATION = "VACATION"
    SICK = "SICK"
    PERSONAL = "PERSONAL"
    BEREAVEMENT = "BEREAVEMENT"
    PARENTAL = "PARENTAL"
    OTHER = "OTHER"


class PolicyType(enum.StrEnum):
    """Whether a policy is unlimited or accrual-based."""

    UNLIMITED = "UNLIMITED"
    ACCRUAL = "ACCRUAL"


class AccrualMethod(enum.StrEnum):
    """How accrual-based policies accumulate time."""

    TIME = "TIME"
    HOURS_WORKED = "HOURS_WORKED"


class RequestStatus(enum.StrEnum):
    """State machine for time-off requests."""

    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    CANCELLED = "CANCELLED"


class LedgerEntryType(enum.StrEnum):
    """Type of ledger entry affecting balance."""

    ACCRUAL = "ACCRUAL"
    HOLD = "HOLD"
    HOLD_RELEASE = "HOLD_RELEASE"
    USAGE = "USAGE"
    ADJUSTMENT = "ADJUSTMENT"
    EXPIRATION = "EXPIRATION"
    CARRYOVER = "CARRYOVER"


class LedgerSourceType(enum.StrEnum):
    """Origin of a ledger entry."""

    REQUEST = "REQUEST"
    PAYROLL = "PAYROLL"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


class AuditEntityType(enum.StrEnum):
    """Entity type recorded in the audit log."""

    POLICY = "POLICY"
    POLICY_VERSION = "POLICY_VERSION"
    REQUEST = "REQUEST"
    ASSIGNMENT = "ASSIGNMENT"
    HOLIDAY = "HOLIDAY"
    ADJUSTMENT = "ADJUSTMENT"


class AccrualFrequency(enum.StrEnum):
    """How often time-based accruals are posted."""

    DAILY = "DAILY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


class AccrualTiming(enum.StrEnum):
    """When within a period accruals are posted."""

    START_OF_PERIOD = "START_OF_PERIOD"
    END_OF_PERIOD = "END_OF_PERIOD"


class DisplayUnit(enum.StrEnum):
    """Display unit for policy balances."""

    MINUTES = "MINUTES"
    HOURS = "HOURS"
    DAYS = "DAYS"


class ProrationMethod(enum.StrEnum):
    """How partial-period accruals are calculated."""

    DAYS_ACTIVE = "DAYS_ACTIVE"
    NONE = "NONE"


class AuditAction(enum.StrEnum):
    """Action recorded in the audit log."""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    APPROVE = "APPROVE"
    DENY = "DENY"
    CANCEL = "CANCEL"
    SUBMIT = "SUBMIT"

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from app.models import (
    AuditLog,
    CompanyHoliday,
    SQLModel,
    TimeOffBalanceSnapshot,
    TimeOffLedgerEntry,
    TimeOffPolicy,
    TimeOffPolicyAssignment,
    TimeOffPolicyVersion,
    TimeOffRequest,
)
from app.models.enums import RequestStatus

EXPECTED_TABLES = {
    "audit_log",
    "company_holiday",
    "time_off_balance_snapshot",
    "time_off_ledger_entry",
    "time_off_policy",
    "time_off_policy_assignment",
    "time_off_policy_version",
    "time_off_request",
}


def test_all_tables_registered() -> None:
    table_names = set(SQLModel.metadata.tables.keys())
    assert EXPECTED_TABLES.issubset(table_names)


def test_time_off_policy_instantiation() -> None:
    policy = TimeOffPolicy(
        company_id=uuid.uuid4(),
        key="vacation-2025",
        category="VACATION",
    )
    assert policy.key == "vacation-2025"
    assert policy.id is not None


def test_time_off_policy_version_instantiation() -> None:
    version = TimeOffPolicyVersion(
        policy_id=uuid.uuid4(),
        version=1,
        effective_from=date(2025, 1, 1),
        type="ACCRUAL",
        created_by=uuid.uuid4(),
    )
    assert version.version == 1
    assert version.effective_to is None
    assert version.accrual_method is None


def test_time_off_policy_assignment_instantiation() -> None:
    assignment = TimeOffPolicyAssignment(
        company_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        policy_id=uuid.uuid4(),
        effective_from=date(2025, 1, 1),
        created_by=uuid.uuid4(),
    )
    assert assignment.effective_to is None


def test_time_off_request_defaults() -> None:
    request = TimeOffRequest(
        company_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        policy_id=uuid.uuid4(),
        start_at=datetime(2025, 7, 1, tzinfo=UTC),
        end_at=datetime(2025, 7, 2, tzinfo=UTC),
        requested_minutes=480,
    )
    assert request.status == RequestStatus.DRAFT
    assert request.reason is None
    assert request.decided_by is None


def test_time_off_ledger_entry_instantiation() -> None:
    entry = TimeOffLedgerEntry(
        company_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        policy_id=uuid.uuid4(),
        policy_version_id=uuid.uuid4(),
        entry_type="ACCRUAL",
        amount_minutes=480,
        effective_at=datetime(2025, 7, 1, tzinfo=UTC),
        source_type="SYSTEM",
        source_id="accrual:2025-07",
    )
    assert entry.amount_minutes == 480
    assert entry.metadata_json is None


def test_time_off_balance_snapshot_defaults() -> None:
    snapshot = TimeOffBalanceSnapshot(
        company_id=uuid.uuid4(),
        employee_id=uuid.uuid4(),
        policy_id=uuid.uuid4(),
    )
    assert snapshot.accrued_minutes == 0
    assert snapshot.used_minutes == 0
    assert snapshot.held_minutes == 0
    assert snapshot.available_minutes == 0
    assert snapshot.version == 1


def test_company_holiday_instantiation() -> None:
    holiday = CompanyHoliday(
        company_id=uuid.uuid4(),
        date=date(2025, 12, 25),
        name="Christmas Day",
    )
    assert holiday.name == "Christmas Day"


def test_audit_log_instantiation() -> None:
    log = AuditLog(
        company_id=uuid.uuid4(),
        actor_id=uuid.uuid4(),
        entity_type="REQUEST",
        entity_id=uuid.uuid4(),
        action="CREATE",
    )
    assert log.before_json is None
    assert log.after_json is None

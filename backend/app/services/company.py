# ruff: noqa: TC003
from __future__ import annotations

import uuid
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


class CompanyInfo(BaseModel):
    """Company metadata from the Company Service."""

    id: uuid.UUID
    name: str
    timezone: str  # e.g. "America/New_York"
    default_workday_minutes: int  # e.g. 480 for 8-hour day


@runtime_checkable
class CompanyService(Protocol):
    """Interface for the Company Service."""

    async def get_company(self, company_id: uuid.UUID) -> CompanyInfo | None:
        """Fetch company metadata. Returns None if not found."""
        ...


class InMemoryCompanyService:
    """In-memory stub implementation for development."""

    def __init__(self) -> None:
        self._companies: dict[uuid.UUID, CompanyInfo] = {}

    def seed(self, company: CompanyInfo) -> None:
        """Seed a company for testing."""
        self._companies[company.id] = company

    async def get_company(self, company_id: uuid.UUID) -> CompanyInfo | None:
        """Fetch company metadata. Returns None if not found."""
        return self._companies.get(company_id)


_company_service: CompanyService = InMemoryCompanyService()


def get_company_service() -> CompanyService:
    """FastAPI dependency for the Company Service."""
    return _company_service


def set_company_service(service: CompanyService) -> None:
    """Override the service (for testing or production wiring)."""
    global _company_service
    _company_service = service

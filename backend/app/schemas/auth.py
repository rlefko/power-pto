# ruff: noqa: TC003
from __future__ import annotations

import uuid

from pydantic import BaseModel


class AuthContext(BaseModel):
    """Dev auth context extracted from request headers."""

    company_id: uuid.UUID
    user_id: uuid.UUID
    role: str = "employee"

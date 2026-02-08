# ruff: noqa: B008, TC003
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, Header, Path, status

from app.exceptions import AppError
from app.schemas.auth import AuthContext


async def get_auth_context(
    x_company_id: uuid.UUID = Header(),
    x_user_id: uuid.UUID = Header(),
    x_role: str = Header(default="employee"),
) -> AuthContext:
    """Extract dev auth context from request headers."""
    return AuthContext(company_id=x_company_id, user_id=x_user_id, role=x_role)


AuthDep = Annotated[AuthContext, Depends(get_auth_context)]


async def require_admin(
    auth: AuthDep,
) -> AuthContext:
    """Require admin role for the request."""
    if auth.role != "admin":
        raise AppError("Admin access required", status_code=status.HTTP_403_FORBIDDEN)
    return auth


AdminDep = Annotated[AuthContext, Depends(require_admin)]


async def validate_company_scope(
    company_id: uuid.UUID = Path(),
    auth: AuthContext = Depends(get_auth_context),
) -> AuthContext:
    """Ensure the path company_id matches the auth header company_id."""
    if company_id != auth.company_id:
        raise AppError("Company ID mismatch", status_code=status.HTTP_403_FORBIDDEN)
    return auth

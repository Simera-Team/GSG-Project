
from typing import Annotated

import jwt

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.domain.entities.user import User
from app.domain.enums.user_role import UserRole
from app.infrastructure.persistence.db.session import get_db
from app.infrastructure.persistence.repositories.user_repository import UserRepository


oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token"   # form login used by Swagger Authorize
)


def get_current_user_id(
    token: Annotated[str, Depends(oauth2_scheme)]
) -> int:

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired access token",
        headers={"WWW-Authenticate": "Bearer"}
    )

    try:
        payload = decode_access_token(token)

        if payload.get("type") != "access":
            raise credentials_exception

        user_id = payload.get("sub")

        if not isinstance(user_id, str):
            raise credentials_exception

        parsed_user_id = int(user_id)

        if parsed_user_id <= 0:
            raise credentials_exception

        return parsed_user_id

    except (jwt.InvalidTokenError, ValueError, TypeError):
        raise credentials_exception


# ==========================================
# Role checks (FR-003, NFR-016)
# ==========================================
# The token carries only the user id, so the role is read from the database
# on every request: a changed or removed role takes effect immediately.

def get_current_user(
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    user = UserRepository(db).get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_roles(*roles: UserRole):
    allowed = {r.value for r in roles}

    def checker(user: Annotated[User, Depends(get_current_user)]) -> User:
        role = user.role.value if isinstance(user.role, UserRole) else str(user.role)
        if role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action needs one of these roles: {', '.join(sorted(allowed))}",
            )
        return user

    return checker


# Reviewers and administrators can use the review queue (an administrator has
# every reviewer ability, requirements §2.10).
require_reviewer = require_roles(UserRole.REVIEWER, UserRole.ADMINISTRATOR)

require_admin = require_roles(UserRole.ADMINISTRATOR)

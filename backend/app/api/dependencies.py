from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_session
from app.models import User, UserRole
from app.security import decode_access_token

DatabaseSession = Annotated[Session, Depends(get_session)]
bearer_scheme = HTTPBearer(auto_error=False)


def authentication_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    session: DatabaseSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
) -> User:
    if credentials is None:
        raise authentication_error()

    user_id = decode_access_token(credentials.credentials)

    if user_id is None:
        raise authentication_error()

    user = session.get(User, user_id)

    if user is None:
        raise authentication_error()

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_moderator(user: CurrentUser) -> User:
    if user.role is not UserRole.MODERATOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Moderator role required",
        )

    return user


ModeratorUser = Annotated[User, Depends(require_moderator)]
